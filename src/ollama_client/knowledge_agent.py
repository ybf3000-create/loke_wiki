# src/ollama_client/knowledge_agent.py
# 知识库查询代理 - 解析用户意图并查询 SQLite / Chroma

import re
from loguru import logger
from src.core.database import (
    query_spirit, query_spirit_list, query_skill,
    query_type_effectiveness, query_item, full_text_search,
    query_egg_by_name, query_egg_by_spirit, query_all_eggs, query_egg_fuzzy,
)
from src.core.vector_store import search as vector_search


# ====================== 意图分类与解析 ======================

INTENT_PATTERNS = {
    "spirit_detail": [
        r"(?:查询|查|找|看看|给我看看|告诉我)\s*(.*?)(?:的\s*(?:信息|属性|资料|介绍|详情|技能|种族|进化|蛋组)?)",
        r"(.*?)(?:的\s*(?:属性|种族值|蛋组|进化方式|技能|配招))",
    ],
    "spirit_list": [
        r"(?:查询|查|找|有什么|列举|列出|哪些)\s*(.*?)(?:系|属性)\s*(?:精灵|宠物)?",
    ],
    "skill_detail": [
        r"(?:技能|招式)\s*(.*?)(?:的\s*(?:效果|描述|威力|命中)?)",
        r"(.*?)(?:技能|招式)(?:的\s*(?:效果|描述|威力|命中)?)",
    ],
    "type_effect": [
        r"(.*?)对(.*?)(?:的\s*(?:克制|效果|倍率))",
        r"(.*?)克制(.*?)",
    ],
    "item_detail": [
        r"(?:查询|查|找)\s*(?:道具|物品)\s*(.*?)",
        r"(.*?)(?:道具|物品)(?:的\s*(?:效果|描述)?)",
    ],
    "search": [
        r"(?:搜索|查找|搜一下)\s*(.*)",
        r"找找\s*(.*)",
    ],
    "egg_query": [
        r"(.*?)的蛋",
        r"(.*?)(?:蛋)(?:能孵出|孵化|出|是什么|有什么)",
        r"(?:查|找|看看)\s*(.*?)(?:蛋|孵化)",
        r"(?:蛋|孵化)\s*(.*?)(?:的\s*(?:精灵|宠物))?",
        r"什么.*?蛋.*?孵化",
    ],
}


def classify_intent(text: str) -> tuple[str, list[str]]:
    """返回 (intent_type, matched_groups)"""
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, text)
            if m:
                groups = [g for g in m.groups() if g]
                logger.debug(f"意图匹配: {intent}, 参数: {groups}")
                return intent, groups
    return "general", [text]


# ====================== 知识库查询执行 ======================

def execute_knowledge_query(text: str) -> dict:
    """
    根据用户输入执行知识库查询
    返回: {"type": str, "data": any, "reply": str}
    """
    intent, args = classify_intent(text)

    if intent == "spirit_detail":
        name = args[0] if args else text
        spirit = query_spirit(name.strip())
        if spirit:
            reply = _format_spirit_reply(spirit)
            return {"type": "spirit_detail", "data": spirit, "reply": reply}
        # 尝试向量检索
        vec = vector_search(f"精灵 {name}", n_results=1)
        if vec:
            return {"type": "vector", "data": vec[0], "reply": vec[0]["text"]}
        return {"type": "not_found", "data": None, "reply": "找不到相关信息，小智的知识库暂时没有收录这个哦~"}

    elif intent == "spirit_list":
        type_name = args[0] if args else ""
        spirits = query_spirit_list(type1=type_name.strip())
        if spirits:
            names = "\n".join(
                f"  • {s['name']} ({s.get('type1', '')} {'+'+s['type2'] if s.get('type2') and s['type2'] != s['type1'] else ''})"
                for s in spirits
            )
            reply = f"✨ {type_name}系精灵列表：\n{names}"
            return {"type": "spirit_list", "data": spirits, "reply": reply}
        return {"type": "not_found", "data": None, "reply": f"找不到 {type_name} 系精灵的信息~"}

    elif intent == "skill_detail":
        name = args[0] if args else text
        skill = query_skill(name.strip())
        if skill:
            reply = _format_skill_reply(skill)
            return {"type": "skill_detail", "data": skill, "reply": reply}
        vec = vector_search(f"技能 {name}", n_results=1)
        if vec:
            return {"type": "vector", "data": vec[0], "reply": vec[0]["text"]}
        return {"type": "not_found", "data": None, "reply": "找不到这个技能的信息~"}

    elif intent == "type_effect":
        attacker = args[0].strip() if len(args) > 0 else ""
        defender = args[1].strip() if len(args) > 1 else ""
        if not attacker or not defender:
            return {"type": "error", "data": None, "reply": "请告诉我攻击属性和防御属性，例如：火系克制草系"}
        multiplier = query_type_effectiveness(attacker, defender)
        if multiplier is not None:
            desc = {0: "完全无效", 0.5: "效果不佳(×0.5)", 1.0: "正常(×1)", 2.0: "克制(×2)"}
            reply = f"🔮 {attacker} 对 {defender}：{desc.get(multiplier, f'×{multiplier}')}"
            return {"type": "type_effect", "data": {"attacker": attacker, "defender": defender, "multiplier": multiplier}, "reply": reply}
        return {"type": "not_found", "data": None, "reply": f"没有找到 {attacker} 对 {defender} 的克制数据~"}

    elif intent == "item_detail":
        name = args[0] if args else text
        item = query_item(name.strip())
        if item:
            reply = _format_item_reply(item)
            return {"type": "item_detail", "data": item, "reply": reply}
        return {"type": "not_found", "data": None, "reply": "找不到这个道具的信息~"}

    elif intent == "egg_query":
        keyword = args[0] if args else text
        # 去噪：去掉"的蛋""蛋""的"等
        keyword = keyword.replace('的蛋','').replace('的','').replace('蛋','').strip()
        # 按蛋名查
        egg = query_egg_by_name(keyword.strip())
        if egg:
            reply = f"🥚 {egg['spirit_name']}的蛋"
            if egg.get('image_path'):
                # 蛋图片文件名: Egg_miaomiao.png
                img_name = f"Egg_{egg['egg_name']}"
                reply += f"\n[IMG:{img_name}]"
            return {"type": "egg_detail", "data": egg, "reply": reply}
        # 按精灵名查
        eggs = query_egg_by_spirit(keyword.strip())
        if eggs:
            lines = [f"🥚 {e['spirit_name']}的蛋" for e in eggs]
            reply = "找到以下蛋：\n" + "\n".join(lines)
            return {"type": "egg_list", "data": eggs, "reply": reply}
        # 如果是进化形态没有蛋，提示基础形态
        from src.core.database import query_spirit
        spirit = query_spirit(keyword.strip())
        if spirit:
            # 模糊搜索蛋表，找最接近的蛋
            fuzzy = query_egg_fuzzy(keyword.strip())
            if fuzzy:
                # 去重，只保留3个最相关的
                seen = set()
                suggestions = []
                for f in fuzzy:
                    if f['spirit_name'] not in seen:
                        seen.add(f['spirit_name'])
                        suggestions.append(f['spirit_name'])
                    if len(suggestions) >= 3:
                        break
                reply = f"⚠️ {keyword}是进化形态，没有专属蛋哦~\n试试查这些基础形态的蛋：{'、'.join(suggestions)}"
            else:
                reply = f"⚠️ {keyword}是进化形态，没有专属蛋哦~\n试试查它的基础形态的蛋！"
            return {"type": "not_found", "data": None, "reply": reply}
        # 列出所有蛋
        if "所有" in text or "全部" in text or "列表" in text:
            all_eggs = query_all_eggs(30)
            lines = [f"🥚 {e['spirit_name']}" for e in all_eggs]
            reply = f"精灵蛋列表（共{len(all_eggs)}种）：\n" + "\n".join(lines)
            return {"type": "egg_list", "data": all_eggs, "reply": reply}
        return {"type": "not_found", "data": None, "reply": "找不到这个蛋的信息~"}

    elif intent == "search":
        keyword = args[0] if args else text
        results = full_text_search(keyword.strip())
        if results:
            lines = [f"  • {r['name']} ({'精灵' if r['type']=='spirit' else '技能' if r['type']=='skill' else '道具'})" for r in results]
            reply = f"🔍 搜索「{keyword}」找到以下内容：\n" + "\n".join(lines)
            return {"type": "search", "data": results, "reply": reply}
        return {"type": "not_found", "data": None, "reply": "搜索不到相关内容~"}

    else:
        # general - 先查SQLite，再查向量库
        spirit = query_spirit(text)
        if spirit:
            reply = _format_spirit_reply(spirit)
            return {"type": "spirit_detail", "data": spirit, "reply": reply}
        skill = query_skill(text)
        if skill:
            reply = _format_skill_reply(skill)
            return {"type": "skill_detail", "data": skill, "reply": reply}
        results = full_text_search(text)
        if results:
            lines = [f"  • {r['name']} ({'精灵' if r['type']=='spirit' else '技能' if r['type']=='skill' else '道具'})" for r in results]
            reply = "🔍 找到以下相关内容：\n" + "\n".join(lines)
            return {"type": "search", "data": results, "reply": reply}
        vec = vector_search(text, n_results=3)
        if vec:
            reply = "🤔 我找到了以下相关资料：\n" + "\n---\n".join(v["text"] for v in vec)
            return {"type": "vector", "data": vec, "reply": reply}
        return {"type": "not_found", "data": None, "reply": "小智的知识库暂时没有收录这个哦~"}


# ====================== 格式化回复 ======================

def _format_spirit_reply(spirit: dict) -> str:
    lines = [f"📋 {spirit['name']}"]
    if spirit.get("number"):
        lines[0] += f" (#{spirit['number']})"
    types = [t for t in [spirit.get("type1", ""), spirit.get("type2", "")] if t]
    if types:
        lines.append(f"属性：{' + '.join(types)}")
    if spirit.get("egg_group"):
        lines.append(f"蛋组：{spirit['egg_group']}")
    if spirit.get("description"):
        lines.append(f"描述：{spirit['description']}")
    if spirit.get("evolution_chain"):
        lines.append(f"进化链：{spirit['evolution_chain']}")
    if spirit.get("skills"):
        lines.append("\n技能：")
        for s in spirit["skills"]:
            method = f"(Lv.{s['learn_level']})" if s.get("learn_level") else f"({s.get('learn_method', '')})"
            lines.append(f"  • {s['name']} {method}")
    if spirit.get("image_path"):
        lines.append(f"\n[IMG:{spirit['name']}]")
    return "\n".join(lines)


def _format_skill_reply(skill: dict) -> str:
    lines = [f"⚔️ {skill['name']}"]
    if skill.get("skill_type"):
        lines.append(f"类型：{skill['skill_type']}")
    if skill.get("power"):
        lines.append(f"威力：{skill['power']}")
    if skill.get("accuracy"):
        lines.append(f"命中：{skill['accuracy']}")
    if skill.get("pp"):
        lines.append(f"PP值：{skill['pp']}")
    if skill.get("description"):
        lines.append(f"效果：{skill['description']}")
    if skill.get("effect"):
        lines.append(f"附加效果：{skill['effect']}")
    return "\n".join(lines)


def _format_item_reply(item: dict) -> str:
    lines = [f"🎁 {item['name']}"]
    if item.get("category"):
        lines.append(f"分类：{item['category']}")
    if item.get("description"):
        lines.append(f"描述：{item['description']}")
    if item.get("effect"):
        lines.append(f"效果：{item['effect']}")
    if item.get("image_path"):
        lines.append(f"\n[IMG:{item['name']}]")
    return "\n".join(lines)
