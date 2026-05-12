# src/ollama_client/agent_loop.py
# AI Agent 循环：tool calling + 自主决策

import json
from loguru import logger

from config.settings import (
    build_system_prompt, load_ai_rules, load_last_model,
    OLLAMA_HOST,
)
from src.ollama_client.tool_definitions import get_tools, get_executor
from src.core.database import get_db_stats

# 最大 tool calling 轮数（防止 AI 死循环）
MAX_TOOL_ROUNDS = 5


def _build_system_prompt_for_agent() -> str:
    """构建 AI agent 专用的 System Prompt，包含行为边界 + 知识库结构"""
    stats = get_db_stats()
    types_str = "、".join(stats.get("spirit_types", []))
    
    kb_desc = f"""
【知识库结构】
你是洛克王国的知识库查询助手，连接着一个本地知识库，包含以下数据：

📊 知识库概览：
- 精灵：{stats['spirits']} 只（每个精灵有属性、描述、进化链）
- 技能：{stats['skills']} 个（每个技能有类型、威力、精度、效果）
- 精灵-技能关联：{stats['spirit_skills']} 条（记录每只精灵能学什么技能）
- 属性克制：{stats['type_effectiveness']} 条（18种属性两两克制关系）
- 道具：{stats['items']} 种
- 蛋：{stats['eggs']} 种

🔰 游戏属性：{types_str}

📋 精灵主要字段：name(名称), number(编号), type1(主属性), type2(副属性), ability(特性), ability_effect(特性效果), description(描述), egg_group(蛋组), evolution_chain(进化链)
📋 技能主要字段：name(名称), skill_type(类型), power(威力), accuracy(精度), pp(PP值), description(描述/效果)
📋 精灵-技能关联：spirit_id, skill_id, learn_level(学习等级), learn_method(学习方法)
📋 属性克制：attacker(攻击方), defender(防御方), multiplier(倍率, 如2.0=克制)
📋 蛋：egg_name(蛋名), spirit_name(对应精灵)

【可用工具】
你可以使用以下工具来查询知识库（按使用频率排序）：
1. in_scope_check — 先确认问题是否属于洛克王国范围
2. query_spirit — 查精灵详情（包含属性和技能列表）
3. query_skill — 查技能详情
4. query_spirits_by_skill — 查谁会某个技能（支持 type_filter 按属性过滤，如"哪些火系精灵能学虫鸣"）
5. query_spirit_list — 按属性查精灵列表
6. query_type_effectiveness — 查单属性克制（如'火打草'）
7. query_type_effectiveness_dual — 查双属性组合被谁克制（如'虫+翼被谁2/4倍克制'）
8. query_item — 查道具
9. query_egg — 查蛋
10. full_text_search — 全文搜索
11. vector_search — 语义搜索（模糊匹配）
12. get_db_stats — 查看知识库统计

【工具调用约束】
- 相同参数的同一工具最多调用一次，禁止重复调用用于“确认”。
- 只要工具返回了非空有效结果，必须直接整理并回答用户。
- 如果已有结果足够回答问题，不要继续调用工具。
"""
    
    # 合并用户自定义规则
    rules_text = load_ai_rules()
    if rules_text.strip():
        kb_desc += f"\n\n【用户自定义行为规则】\n{rules_text.strip()}"
    
    return kb_desc


def _execute_tool(tool_name: str, arguments: dict) -> str:
    """执行一个 tool 并返回结果字符串"""
    executor = get_executor(tool_name)
    try:
        result = executor(arguments)
        return result
    except Exception as e:
        logger.exception(f"Tool {tool_name} 执行失败: {e}")
        return json.dumps({
            "error": f"执行 {tool_name} 时出错: {e}",
            "tool": tool_name,
            "arguments": arguments,
        }, ensure_ascii=False)


def _tool_call_signature(tc) -> str:
    """生成 tool 调用签名（name + 参数规范化），用于去重"""
    name = tc.function.name
    args = tc.function.arguments
    # 参数是 dict 时做稳定序列化，避免键顺序导致签名波动
    if isinstance(args, dict):
        args_str = json.dumps(args, ensure_ascii=False, sort_keys=True)
    else:
        args_str = str(args)
    return f"{name}:{args_str}"


def _force_finalize_answer(ollama_client, messages: list, reason: str) -> str:
    """强制模型基于已有结果直接回答（不再调用 tools）"""
    guide = {
        "role": "assistant",
        "content": (
            f"[系统提示] {reason}。同参数工具结果已经提供，"
            "请不要再次调用工具，直接基于现有查询结果给出完整、明确的最终回答。"
        )
    }
    msgs = messages + [guide]
    try:
        final = ollama_client._client.chat(
            model=ollama_client.model,
            messages=msgs,
            options={"num_ctx": 8192},
        )
        if final.message and final.message.content:
            return final.message.content
    except Exception as e:
        logger.error(f"强制收尾回答失败: {e}")
    return "小智已拿到查询结果，但整理回答时中断了，请再问一次，我会直接给最终结论。"


def run_agent_loop(user_message: str, ollama_client=None) -> str:
    """AI Agent 主循环
    
    1. 接收用户消息
    2. 让 AI 决定是直接回复还是调 tool
    3. 如果调 tool → 执行 → 结果发回 AI → 回到 2
    4. 最大 MAX_TOOL_ROUNDS 轮
    5. 返回最终回复
    
    Args:
        user_message: 用户输入
        ollama_client: OllamaClient 实例（可选，不传则新建）
    
    Returns:
        最终回复文本
    """
    if ollama_client is None:
        from src.ollama_client.ollama_client import OllamaClient
        ollama_client = OllamaClient()
    
    tools = get_tools()
    system_prompt = _build_system_prompt_for_agent()
    
    # 初始化消息列表
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    
    # 记录最近一次 tool 调用的签名，用于检测重复（基于 name+arguments）
    last_tool_signature = None
    # 记录已执行过的同参调用，防止跨轮重复执行
    executed_signatures = set()

    for round_num in range(MAX_TOOL_ROUNDS + 1):
        logger.info(f"Agent 第 {round_num + 1} 轮调用")
        
        try:
            response = ollama_client._client.chat(
                model=ollama_client.model,
                messages=messages,
                tools=tools,
                options={"num_ctx": 8192},
            )
        except Exception as e:
            logger.exception(f"Ollama 调用失败: {e}")
            # 如果第一轮就失败，返回错误信息
            if round_num == 0:
                return f"⚠️ AI 调用失败: {e}"
            # 否则返回之前的内容
            break
        
        message = response.message
        
        # 检查是否有 tool_calls
        has_tool_calls = hasattr(message, "tool_calls") and message.tool_calls
        
        if not has_tool_calls:
            # AI 选择直接回复
            if message.content:
                return message.content
            else:
                # 空回复，可能是错误
                return "小智暂时无法回答这个问题~"
        
        # 先构建当前轮 tool 签名（在写入消息前判重，避免半截 tool_call 历史）
        current_call_signatures = [_tool_call_signature(tc) for tc in message.tool_calls]
        current_signature = "|".join(current_call_signatures)

        # 情况1：与上一轮完全同参重复请求 -> 强制收尾回答，不再继续 tool loop
        if last_tool_signature and current_signature == last_tool_signature and round_num > 0:
            logger.warning(f"AI 重复请求相同的 tool (签名: {current_signature[:120]})，改为强制收尾回答")
            return _force_finalize_answer(
                ollama_client,
                messages,
                "检测到重复的同参数工具调用"
            )

        # 情况2：当前轮存在已执行过的同参调用 -> 强制收尾回答
        duplicated_executed = [s for s in current_call_signatures if s in executed_signatures]
        if duplicated_executed:
            logger.warning(f"AI 请求了已执行过的同参工具: {duplicated_executed[:2]}，改为强制收尾回答")
            return _force_finalize_answer(
                ollama_client,
                messages,
                "检测到已执行过的同参数工具再次请求"
            )

        # AI 请求调 tool（通过判重后才写入 assistant/tool_call 消息）
        assistant_msg = {"role": "assistant", "content": message.content}
        # 转换 tool_calls 为可序列化的格式
        tool_calls_data = []
        for tc in message.tool_calls:
            tc_dict = {
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            }
            tool_calls_data.append(tc_dict)
        
        # 兼容 ollama Python 库不同版本的 tool_calls 格式
        if hasattr(message.tool_calls[0], "function"):
            assistant_msg["tool_calls"] = [
                {
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in message.tool_calls
            ]
        else:
            assistant_msg["tool_calls"] = message.tool_calls
        
        messages.append(assistant_msg)

        # 逐个执行 tool
        for tc in message.tool_calls:
            tool_name = tc.function.name
            arguments = tc.function.arguments
            tc_sig = _tool_call_signature(tc)

            logger.info(f"  → 调 tool: {tool_name}({arguments})")

            result = _execute_tool(tool_name, arguments)

            logger.info(f"  ← 结果: {result[:200]}...")

            # 添加 tool 结果到消息
            messages.append({
                "role": "tool",
                "content": result,
                "name": tool_name,
            })

            # 标记该同参调用已执行
            executed_signatures.add(tc_sig)

        last_tool_signature = current_signature
    
    # 超出最大轮数，尝试获取最后一条回复
    try:
        final = ollama_client._client.chat(
            model=ollama_client.model,
            messages=messages,
            options={"num_ctx": 8192},
        )
        if final.message and final.message.content:
            return final.message.content
    except Exception as e:
        logger.error(f"获取最终回复失败: {e}")
    
    return "小智暂时无法回答这个问题，请换个问法试试~"
