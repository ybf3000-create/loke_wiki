# src/ollama_client/tool_definitions.py
# 定义 Ollama 可调用的工具（tool calling）

from loguru import logger

from src.core.database import (
    query_spirit as _query_spirit,
    query_skill as _query_skill,
    query_spirits_by_skill as _query_spirits_by_skill,
    query_spirit_list as _query_spirit_list,
    query_type_effectiveness as _query_type_effectiveness,
    query_type_effectiveness_dual as _query_type_effectiveness_dual,
    query_item as _query_item,
    query_egg_by_name as _query_egg,
    full_text_search as _full_text_search,
    get_db_stats as _get_db_stats,
    in_scope_check as _in_scope_check,
)
from src.core.vector_store import search as _vector_search


# ======================== Ollama Tool Schemas ========================

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "in_scope_check",
            "description": "判断用户问题是否属于洛克王国知识库的范围。先调这个 tool 确认能不能答。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用户的问题原文"
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_spirit",
            "description": "查询一只洛克王国精灵的详细信息（含属性和技能列表）。当你需要知道某只精灵的属性、种族值、进化链或它能学的技能时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "精灵名称，如 '火神'、'水蓝蓝'、'喵喵'"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_skill",
            "description": "查询一个技能的详细信息（类型、威力、效果）。当用户问某个技能的效果或详情时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "技能名称，如 '烈焰冲锋'、'晒太阳'、'水泡'"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_spirits_by_skill",
            "description": "查询哪些精灵能学某个技能。当用户问'谁会XX技能'、'哪些精灵能学XX'、'哪些火系精灵能学XX'等组合条件时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "技能名称，如 '晒太阳'、'烈焰冲锋'、'虫鸣'"
                    },
                    "type_filter": {
                        "type": "string",
                        "description": "可选，按属性过滤精灵。如用户问'哪些火系精灵能学虫鸣'则传 '火'。不传则返回所有属性。"
                    }
                },
                "required": ["skill_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_spirit_list",
            "description": "按属性（系别）查询精灵列表。当用户问'有哪些火系精灵'、'水系精灵有哪些'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type_name": {
                        "type": "string",
                        "description": "属性名称，如 '火'、'水'、'草'、'龙' 等"
                    }
                },
                "required": ["type_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_type_effectiveness_dual",
            "description": "查询双属性防御组合被哪些攻击属性克制。当用户问'虫+翼被谁4倍克制'、'草+虫被谁克制'时调用。返回所有攻击属性的倍率列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "def_type1": {
                        "type": "string",
                        "description": "防御方属性1，如 '虫'"
                    },
                    "def_type2": {
                        "type": "string",
                        "description": "防御方属性2，如 '翼'"
                    }
                },
                "required": ["def_type1", "def_type2"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_type_effectiveness",
            "description": "查询两个属性之间的克制倍率。当用户问'火系克制什么'、'水系被什么克制'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "attacker": {
                        "type": "string",
                        "description": "攻击方属性，如 '火'"
                    },
                    "defender": {
                        "type": "string",
                        "description": "防御方属性，如 '草'"
                    }
                },
                "required": ["attacker", "defender"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_item",
            "description": "查询洛克王国道具的信息。当用户问某个道具或物品时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "道具名称"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_egg",
            "description": "查询洛克王国精灵蛋的信息。当用户问'XX的蛋'、'XX怎么孵化'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "egg_name": {
                        "type": "string",
                        "description": "精灵名称或蛋的名称，如 '喵喵'、'火花'"
                    }
                },
                "required": ["egg_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "full_text_search",
            "description": "全文搜索，在当前知识库中搜索包含关键词的任何内容。当你不确定用户问的是什么时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "vector_search",
            "description": "向量语义搜索，用自然语言模糊匹配知识库。当精确搜索找不到结果时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索用的自然语言描述"
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "返回结果数量（默认3）",
                        "default": 3
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_db_stats",
            "description": "获取知识库的统计信息和结构说明。当你想了解知识库里有什么时调用。",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
]


# ======================== Tool 结果格式化 ========================

def _to_str(obj) -> str:
    """对象转字符串（用于 in_scope_check 的 dict 结果）"""
    if obj is None:
        return "未找到相关信息"
    import json
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _fmt_spirit(data: dict | None) -> str:
    """格式化精灵查询结果为可读文本"""
    if not data:
        return "未找到该精灵"
    lines = [f"名称：{data.get('name', '未知')}"]
    if data.get('number'):
        lines.append(f"编号：{data['number']}")
    types = [t for t in [data.get('type1', ''), data.get('type2', '')] if t]
    if types:
        lines.append(f"属性：{' + '.join(types)}")
    if data.get('description'):
        lines.append(f"描述：{data['description']}")
    if data.get('ability') and data.get('ability') != '无':
        lines.append(f"特性：{data['ability']}")
        if data.get('ability_effect') and data.get('ability_effect') != '无':
            lines.append(f"特性效果：{data['ability_effect']}")
    if data.get('egg_group'):
        lines.append(f"蛋组：{data['egg_group']}")
    if data.get('evolution_chain'):
        lines.append(f"进化链：{data['evolution_chain']}")
    # 技能列表（最多显示200个）
    skills = data.get('skills', [])
    if skills:
        lines.append(f"\n技能（共{len(skills)}个）：")
        for s in skills[:200]:
            method = f"(Lv.{s['learn_level']})" if s.get('learn_level') else f"({s.get('learn_method', '')})"
            lines.append(f"  - {s['name']} {method}")
        if len(skills) > 200:
            lines.append(f"  ... 还有{len(skills)-50}个技能")
    if data.get('image_path'):
        lines.append(f"\n[IMG:{data['name']}]")
    return "\n".join(lines)


def _fmt_skill(data: dict | None) -> str:
    """格式化技能查询结果为可读文本"""
    if not data:
        return "未找到该技能"
    lines = [f"技能：{data.get('name', '未知')}"]
    if data.get('skill_type'):
        lines.append(f"类型：{data['skill_type']}")
    if data.get('power'):
        lines.append(f"威力：{data['power']}")
    if data.get('accuracy'):
        lines.append(f"命中：{data['accuracy']}")
    if data.get('pp'):
        lines.append(f"PP值：{data['pp']}")
    desc = data.get('description') or data.get('effect') or ''
    if desc:
        lines.append(f"效果：{desc}")
    return "\n".join(lines)


def _fmt_spirits_by_skill(spirits: list) -> str:
    """格式化技能→精灵查询结果为可读文本"""
    if not spirits:
        return "没有精灵能学这个技能"
    # 按学习方法分组
    by_method = {}
    for s in spirits:
        method = s.get('learn_method', 'unknown')
        by_method.setdefault(method, []).append(s)

    lines = [f"能学该技能的精灵共 {len(spirits)} 只："]
    for method, group in by_method.items():
        if method == 'level_up':
            # 按等级排序
            group.sort(key=lambda x: x.get('learn_level', 0))
            items = []
            for s in group:
                types = [t for t in [s.get('type1', ''), s.get('type2', '')] if t]
                type_str = f"[{'/'.join(types)}]" if types else ""
                items.append(f"{s['spirit_name']}{type_str}(Lv.{s['learn_level']})")
        else:
            items = []
            for s in group:
                types = [t for t in [s.get('type1', ''), s.get('type2', '')] if t]
                type_str = f"[{'/'.join(types)}]" if types else ""
                items.append(f"{s['spirit_name']}{type_str}")
        lines.append(f"\n[{method}]")
        # 显示所有精灵（上限200只）
        max_show = 200
        shown = items[:max_show]
        lines.extend(f"  {i+1}. {s}" for i, s in enumerate(shown))
        if len(items) > max_show:
            lines.append(f"  ... 还有{len(items)-max_show}只未显示（共{len(items)}只）")
    return "\n".join(lines)


def _fmt_spirit_list(spirits: list) -> str:
    """格式化精灵列表查询结果为可读文本"""
    if not spirits:
        return "未找到任何精灵"
    lines = [f"共 {len(spirits)} 只精灵："]
    for i, s in enumerate(spirits, 1):
        types = [t for t in [s.get('type1', ''), s.get('type2', '')] if t]
        type_str = f"({' + '.join(types)})" if types else ""
        lines.append(f"  {i}. {s['name']}{type_str}")
    return "\n".join(lines)


def _fmt_type_effectiveness(multiplier: float | None, attacker: str, defender: str) -> str:
    """格式化克制查询结果为可读文本"""
    if multiplier is None:
        return f"未找到 {attacker} 对 {defender} 的克制数据"
    desc = {0: "完全无效", 0.5: "效果不佳", 1.0: "效果一般", 2.0: "克制"}
    label = desc.get(multiplier, f"倍率 ×{multiplier}")
    return f"{attacker} → {defender}：{label}"


def _fmt_type_effectiveness_dual(results: list, def_type1: str, def_type2: str) -> str:
    """格式化双属性克制查询结果为可读文本"""
    if not results:
        return f"未找到 {def_type1}+{def_type2} 的克制数据"
    lines = [f"{def_type1}+{def_type2} 被以下攻击属性克制："]
    categories = {4: "🔥 4倍克制", 2: "💪 2倍克制", 1: "🤷 效果一般(1倍)", 0.5: "😰 效果不佳(0.5倍)", 0.25: "😱 双重抵抗(0.25倍)", 0: "🚫 完全免疫"}
    # 按倍率分组排序
    by_mult = {}
    for r in results:
        m = r["multiplier"]
        by_mult.setdefault(m, []).append(r["attacker"])
    for m in sorted(by_mult.keys(), reverse=True):
        label = categories.get(m, f"×{m}")
        atk_list = "、".join(by_mult[m])
        lines.append(f"\n{label} ({len(by_mult[m])}个): {atk_list}")
    return "\n".join(lines)


def _fmt_item(data: dict | None) -> str:
    """格式化道具查询结果为可读文本"""
    if not data:
        return "未找到该道具"
    lines = [f"道具：{data.get('name', '未知')}"]
    if data.get('category'):
        lines.append(f"分类：{data['category']}")
    if data.get('description'):
        lines.append(f"描述：{data['description']}")
    if data.get('effect'):
        lines.append(f"效果：{data['effect']}")
    if data.get('image_path'):
        lines.append(f"\n[IMG:{data['name']}]")
    return "\n".join(lines)


def _fmt_egg(data: dict | None) -> str:
    """格式化蛋查询结果为可读文本"""
    if not data:
        return "未找到该蛋"
    return f"蛋名：{data.get('egg_name', '未知')}\n对应精灵：{data.get('spirit_name', '未知')}"


def _fmt_fts(results: list) -> str:
    """格式化全文搜索结果为可读文本"""
    if not results:
        return "未搜索到相关内容"
    lines = [f"搜索结果（共{len(results)}条）："]
    for r in results:
        type_label = {'spirit': '精灵', 'skill': '技能', 'item': '道具'}.get(r.get('type', ''), r.get('type', ''))
        lines.append(f"  - {r['name']} ({type_label})")
    return "\n".join(lines)


def _fmt_vector(hits: list) -> str:
    """格式化向量搜索结果为可读文本"""
    if not hits:
        return "未找到相关结果"
    lines = [f"相关结果（共{len(hits)}条）："]
    for h in hits:
        text = h.get('text', '')
        score = h.get('distance', 0)
        lines.append(f"  - [{score:.2f}] {text[:100]}")
    return "\n".join(lines)


def _fmt_db_stats(stats: dict) -> str:
    """格式化知识库统计信息"""
    lines = [f"知识库统计："]
    lines.append(f"  精灵：{stats.get('spirits', 0)} 只")
    lines.append(f"  技能：{stats.get('skills', 0)} 个")
    lines.append(f"  精灵-技能关联：{stats.get('spirit_skills', 0)} 条")
    lines.append(f"  属性克制：{stats.get('type_effectiveness', 0)} 条")
    lines.append(f"  道具：{stats.get('items', 0)} 种")
    lines.append(f"  蛋：{stats.get('eggs', 0)} 种")
    types = stats.get('spirit_types', [])
    if types:
        lines.append(f"  属性种类：{'、'.join(types)}")
    return "\n".join(lines)


# ======================== Tool 执行映射 ========================

TOOL_EXECUTORS = {
    "in_scope_check": lambda args: _to_str(_in_scope_check(args.get("question", ""))),
    "query_spirit": lambda args: _fmt_spirit(_query_spirit(args.get("name", ""))),
    "query_skill": lambda args: _fmt_skill(_query_skill(args.get("name", ""))),
    "query_spirits_by_skill": lambda args: _fmt_spirits_by_skill(
        _query_spirits_by_skill(
            args.get("skill_name", ""),
            type_filter=args.get("type_filter", "")
        )
    ),
    "query_spirit_list": lambda args: _fmt_spirit_list(
        _query_spirit_list(args.get("type_name", ""))
    ),
    "query_type_effectiveness": lambda args: _fmt_type_effectiveness(
        _query_type_effectiveness(args.get("attacker", ""), args.get("defender", "")),
        args.get("attacker", ""), args.get("defender", "")
    ),
    "query_type_effectiveness_dual": lambda args: _fmt_type_effectiveness_dual(
        _query_type_effectiveness_dual(args.get("def_type1", ""), args.get("def_type2", "")),
        args.get("def_type1", ""), args.get("def_type2", "")
    ),
    "query_item": lambda args: _fmt_item(_query_item(args.get("name", ""))),
    "query_egg": lambda args: _fmt_egg(_query_egg(args.get("egg_name", ""))),
    "full_text_search": lambda args: _fmt_fts(_full_text_search(args.get("keyword", ""))),
    "vector_search": lambda args: _fmt_vector(_vector_search(
        args.get("query", ""), n_results=args.get("n_results", 3)
    )),
    "get_db_stats": lambda args: _fmt_db_stats(_get_db_stats()),
}


def get_tools() -> list[dict]:
    """返回所有 tool 定义列表（供 Ollama chat 使用）"""
    return TOOL_SCHEMAS


def get_executor(name: str):
    """根据 tool name 返回对应的执行函数
    
    Args:
        name: tool 名称（即 function name）
    
    Returns:
        可调用对象，接受 args dict 参数
    """
    executor = TOOL_EXECUTORS.get(name)
    if not executor:
        logger.error(f"未知 tool: {name}")
        return lambda args: f"错误：未知工具 {name}"
    return executor
