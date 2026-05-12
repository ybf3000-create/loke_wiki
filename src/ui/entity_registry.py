# src/ui/entity_registry.py
# 实体名称注册表 - 预加载所有精灵/技能/属性名，用于聊天文本高亮匹配

from loguru import logger
from src.core.database import get_connection

# 洛克王国18种属性
ATTRIBUTE_TYPES = [
    "普通", "草", "火", "水", "光", "地", "冰", "龙", "电",
    "毒", "虫", "武", "翼", "萌", "幽", "恶", "机械", "幻",
]

# 名称 → 实体类型映射（运行时加载）
_ENTITY_MAP: dict[str, str] = {}  # {"迪莫": "spirit", "草": "type", "烈焰风暴": "skill"}
_NAME_LENGTHS: set[int] = set()  # 用于按长度降序匹配，避免短名误覆盖


def load_entity_registry():
    """从数据库加载所有实体名称到内存"""
    global _ENTITY_MAP, _NAME_LENGTHS
    _ENTITY_MAP.clear()

    conn = get_connection()
    try:
        # 精灵名称
        for row in conn.execute("SELECT name FROM spirits").fetchall():
            _ENTITY_MAP[row["name"]] = "spirit"
        # 技能名称
        for row in conn.execute("SELECT name FROM skills").fetchall():
            name = row["name"]
            # 技能名可能和精灵名/属性名重复，优先级: spirit > type > skill
            if name not in _ENTITY_MAP:
                _ENTITY_MAP[name] = "skill"
        # 属性名（最低优先级，不覆盖精灵和技能）
        for t in ATTRIBUTE_TYPES:
            if t not in _ENTITY_MAP:
                _ENTITY_MAP[t] = "type"
    finally:
        conn.close()

    _NAME_LENGTHS = {len(name) for name in _ENTITY_MAP}
    logger.info(f"实体注册表加载完成: 精灵 {sum(1 for v in _ENTITY_MAP.values() if v=='spirit')} + "
                f"技能 {sum(1 for v in _ENTITY_MAP.values() if v=='skill')} + "
                f"属性 {sum(1 for v in _ENTITY_MAP.values() if v=='type')} = {len(_ENTITY_MAP)} 条")


def get_entity_type(name: str) -> str | None:
    """返回实体类型: 'spirit' | 'skill' | 'type' | None"""
    return _ENTITY_MAP.get(name)


def has_entity(name: str) -> bool:
    return name in _ENTITY_MAP


def iter_matches(text: str) -> list[tuple[str, str, int, int]]:
    """扫描文本，返回所有匹配的实体

    Returns:
        [(实体名, 实体类型, start, end), ...]
    """
    if not _ENTITY_MAP:
        load_entity_registry()

    matches = []
    seen_spans = set()

    # 按名称长度降序排序（长名优先匹配，避免"火"覆盖"火焰冲锋"）
    sorted_names = sorted(_ENTITY_MAP.keys(), key=len, reverse=True)

    for name in sorted_names:
        start = 0
        while True:
            idx = text.find(name, start)
            if idx == -1:
                break
            span = (idx, idx + len(name))
            # 检查是否被已匹配的实体覆盖
            overlap = False
            for s, e in seen_spans:
                if not (span[1] <= s or span[0] >= e):
                    overlap = True
                    break
            if not overlap:
                matches.append((name, _ENTITY_MAP[name], idx, idx + len(name)))
                seen_spans.add(span)
            start = idx + 1

    # 按位置排序
    matches.sort(key=lambda m: m[2])
    return matches


def get_entity_color(entity_type: str) -> str:
    return {
        "spirit": "#2196F3",  # 蓝色
        "skill": "#9C27B0",   # 紫色
        "type": "#FF9800",    # 橙色
    }.get(entity_type, "#333333")


def render_html(text: str) -> str:
    """将文本中的实体渲染为可点击HTML"""
    matches = iter_matches(text)

    if not matches:
        # 转义HTML特殊字符
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        return text

    result = []
    last_end = 0

    for name, etype, start, end in matches:
        # 添加非实体文本
        if start > last_end:
            raw = text[last_end:start]
            raw = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
            result.append(raw)

        color = get_entity_color(etype)
        # 转义实体名中的HTML字符
        safe_name = name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        result.append(
            f'<a href="{etype}:{name}" '
            f'style="color:{color};text-decoration:none;font-weight:bold;'
            f'border-bottom:1px dashed {color};">{safe_name}</a>'
        )
        last_end = end

    if last_end < len(text):
        raw = text[last_end:]
        raw = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        result.append(raw)

    return "".join(result)
