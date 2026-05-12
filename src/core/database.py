# src/core/database.py
# SQLite 知识库管理模块

import sqlite3
import json
from pathlib import Path
from loguru import logger
from config.settings import DB_PATH


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表结构"""
    conn = get_connection()
    with conn:
        # 精灵表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spirits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                number      TEXT,
                type1       TEXT,
                type2       TEXT,
                description TEXT,
                egg_group   TEXT,
                evolution_chain TEXT,
                ability     TEXT DEFAULT '',
                ability_effect TEXT DEFAULT '',
                image_path  TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 迁移：给已有数据添加 ability 列（如果不存在）
        for col in ['ability', 'ability_effect']:
            try:
                conn.execute(f"ALTER TABLE spirits ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass  # 列已存在
        # 技能表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                skill_type  TEXT,
                power       INTEGER,
                accuracy    INTEGER,
                pp          INTEGER,
                description TEXT,
                effect      TEXT
            )
        """)
        # 精灵-技能关联表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spirit_skills (
                spirit_id   INTEGER REFERENCES spirits(id),
                skill_id    INTEGER REFERENCES skills(id),
                learn_level INTEGER,
                learn_method TEXT,
                PRIMARY KEY (spirit_id, skill_id, learn_method)
            )
        """)
        # 属性克制表（统一表：支持单属性和双属性）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS type_effectiveness (
                atk_type1   TEXT NOT NULL,
                atk_type2   TEXT NOT NULL DEFAULT '无',
                def_type1   TEXT NOT NULL,
                def_type2   TEXT NOT NULL DEFAULT '无',
                multiplier  REAL NOT NULL,
                source      TEXT DEFAULT 'wiki_world_2026-05-09',
                updated_at  TEXT,
                PRIMARY KEY (atk_type1, atk_type2, def_type1, def_type2)
            )
        """)
        # 道具表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                category    TEXT,
                description TEXT,
                effect      TEXT,
                image_path  TEXT
            )
        """)
        # 精灵蛋表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eggs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                egg_name    TEXT NOT NULL UNIQUE,
                spirit_name TEXT,
                image_path  TEXT,
                category    TEXT DEFAULT '普通',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # 精灵拼音索引表（用于语音输入同音字容错）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS spirit_pinyin (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                spirit_name     TEXT NOT NULL UNIQUE,
                pinyin_full     TEXT NOT NULL,   -- 全拼(带声调)，如 "di mo"
                pinyin_nos      TEXT NOT NULL,   -- 全拼(无声调)，如 "di mo"
                pinyin_initials TEXT NOT NULL,   -- 首字母，如 "dm"
                FOREIGN KEY (spirit_name) REFERENCES spirits(name)
            )
        """)
        # 技能拼音索引表（用于语音输入同音字容错）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS skill_pinyin (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name      TEXT NOT NULL UNIQUE,
                pinyin_full     TEXT NOT NULL,   -- 全拼(带声调)
                pinyin_nos      TEXT NOT NULL,   -- 全拼(无声调)
                pinyin_initials TEXT NOT NULL,   -- 首字母
                FOREIGN KEY (skill_name) REFERENCES skills(name)
            )
        """)
        logger.info("数据库初始化完成")
    conn.close()


# ======================== 查询函数 ========================

def query_spirit(name: str) -> dict | None:
    """根据精灵名称查询完整信息（含特性和技能），支持同音字容错"""
    conn = get_connection()
    try:
        # 先用 resolve_spirit_name 处理同音字/拼音匹配
        resolved = resolve_spirit_name(name)
        if not resolved:
            return None
        row = conn.execute(
            "SELECT * FROM spirits WHERE name = ?", (resolved,)
        ).fetchone()
        if row:
            data = dict(row)
            # 查询技能
            skills = conn.execute("""
                SELECT s.name, s.skill_type, s.power, s.accuracy, sk.learn_level, sk.learn_method
                FROM spirit_skills sk
                JOIN skills s ON sk.skill_id = s.id
                JOIN spirits sp ON sk.spirit_id = sp.id
                WHERE sp.name = ?
                ORDER BY sk.learn_method, sk.learn_level
            """, (data["name"],)).fetchall()
            data["skills"] = [dict(s) for s in skills]
            # 空值统一为"无"
            if not data.get("ability"):
                data["ability"] = "无"
            if not data.get("ability_effect"):
                data["ability_effect"] = "无"
            return data
        return None
    finally:
        conn.close()


def query_spirit_list(type1: str = None, type2: str = None) -> list:
    """按属性筛选精灵列表"""
    conn = get_connection()
    try:
        conditions, params = [], []
        if type1:
            conditions.append("(type1 = ? OR type2 = ?)")
            params.extend([type1, type1])
        if type2:
            conditions.append("(type1 = ? OR type2 = ?)")
            params.extend([type2, type2])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(f"SELECT name, type1, type2, number FROM spirits {where}", params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_skill(name: str) -> dict | None:
    """查询技能详情（支持同音字容错）"""
    conn = get_connection()
    try:
        resolved = resolve_skill_name(name)
        if not resolved:
            return None
        row = conn.execute(
            "SELECT * FROM skills WHERE name = ?", (resolved,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def query_type_effectiveness(attacker: str, defender: str) -> float | None:
    """查询属性克制倍率（兼容单属性和双属性防御）
    
    Args:
        attacker: 攻击属性，如 '火'
        defender: 防御属性，如 '草' 或 '虫+翼'（双属性用+连接）
    
    Returns:
        倍率或 None
    """
    conn = get_connection()
    try:
        # 处理双属性防御 (如 '虫+翼')
        if "+" in defender:
            parts = defender.split("+")
            if len(parts) != 2:
                return None
            d1, d2 = sorted(parts)  # 按字典序与入库顺序一致
            row = conn.execute(
                "SELECT multiplier FROM type_effectiveness WHERE atk_type1=? AND atk_type2='无' AND def_type1=? AND def_type2=?",
                (attacker, d1, d2)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT multiplier FROM type_effectiveness WHERE atk_type1=? AND atk_type2='无' AND def_type1=? AND def_type2='无'",
                (attacker, defender)
            ).fetchone()
        return row["multiplier"] if row else None
    finally:
        conn.close()


def query_type_effectiveness_dual(def_type1: str, def_type2: str) -> list[dict]:
    """查询某双属性防御组合下，所有攻击属性的倍率
    
    返回: [{"attacker": str, "multiplier": float}, ...]
    """
    d1, d2 = sorted([def_type1, def_type2])
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT atk_type1 AS attacker, multiplier FROM type_effectiveness WHERE atk_type2='无' AND def_type1=? AND def_type2=? ORDER BY multiplier DESC",
            (d1, d2)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_item(name: str) -> dict | None:
    """查询道具"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM items WHERE name = ? OR name LIKE ?",
            (name, f"%{name}%")
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def full_text_search(keyword: str, limit: int = 5) -> list:
    """跨表全文关键词搜索"""
    conn = get_connection()
    results = []
    try:
        spirits = conn.execute(
            "SELECT name, 'spirit' as type FROM spirits WHERE name LIKE ? OR description LIKE ? LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit)
        ).fetchall()
        skills = conn.execute(
            "SELECT name, 'skill' as type FROM skills WHERE name LIKE ? OR description LIKE ? LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", limit)
        ).fetchall()
        items = []
        try:
            items = conn.execute(
                "SELECT name, 'item' as type FROM items WHERE name LIKE ? OR description LIKE ? LIMIT ?",
                (f"%{keyword}%", f"%{keyword}%", limit)
            ).fetchall()
        except Exception:
            items = []  # items表可能不存在
        results = [dict(r) for r in (spirits + skills + items)]
    finally:
        conn.close()
    return results


def update_spirit_ability(name: str, ability: str, ability_effect: str) -> bool:
    """更新指定精灵的特性数据"""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE spirits SET ability=?, ability_effect=? WHERE name=?",
            (ability, ability_effect, name)
        )
        conn.commit()
        if cur.rowcount == 0:
            # 尝试模糊匹配
            cur = conn.execute(
                "UPDATE spirits SET ability=?, ability_effect=? WHERE name LIKE ?",
                (ability, ability_effect, f"%{name}%")
            )
            conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ======================== 拼音模糊匹配（语音输入容错） ========================

_SPIRIT_PINYIN_CACHE: dict[str, dict] | None = None


def _build_pinyin_cache(conn) -> dict:
    """从 spirit_pinyin 表加载拼音索引到内存缓存"""
    cache = {}
    rows = conn.execute(
        "SELECT spirit_name, pinyin_full, pinyin_nos, pinyin_initials FROM spirit_pinyin"
    ).fetchall()
    for r in rows:
        d = dict(r)
        cache[r["spirit_name"]] = d
        cache[r["pinyin_nos"]] = d   # 全拼(无音调)也可以直接查到
        cache[r["pinyin_initials"]] = d  # 首字母也可以直接查到
    return cache


def rebuild_pinyin_index():
    """重建所有精灵的拼音索引（数据迁移/重建用）"""
    from pypinyin import pinyin, Style
    conn = get_connection()
    try:
        conn.execute("DELETE FROM spirit_pinyin")
        rows = conn.execute("SELECT name FROM spirits").fetchall()
        count = 0
        for r in rows:
            name = r["name"]
            # 生成全拼（带声调）
            py_full = pinyin(name, style=Style.TONE3)
            full_str = " ".join([p[0] for p in py_full])
            # 全拼（无声调）
            py_no = pinyin(name, style=Style.NORMAL)
            no_str = " ".join([p[0] for p in py_no])
            # 首字母缩写
            py_init = pinyin(name, style=Style.FIRST_LETTER)
            init_str = "".join([p[0] for p in py_init])
            conn.execute(
                "INSERT OR REPLACE INTO spirit_pinyin (spirit_name, pinyin_full, pinyin_nos, pinyin_initials) VALUES (?, ?, ?, ?)",
                (name, full_str, no_str, init_str)
            )
            count += 1
        conn.commit()
        global _SPIRIT_PINYIN_CACHE
        _SPIRIT_PINYIN_CACHE = None  # 清空缓存
        return count
    finally:
        conn.close()


def rebuild_skill_pinyin_index():
    """重建所有技能的拼音索引"""
    from pypinyin import pinyin, Style
    conn = get_connection()
    try:
        conn.execute("DELETE FROM skill_pinyin")
        rows = conn.execute("SELECT name FROM skills").fetchall()
        count = 0
        for r in rows:
            name = r["name"]
            py_full = pinyin(name, style=Style.TONE3)
            full_str = " ".join([p[0] for p in py_full])
            py_no = pinyin(name, style=Style.NORMAL)
            no_str = " ".join([p[0] for p in py_no])
            py_init = pinyin(name, style=Style.FIRST_LETTER)
            init_str = "".join([p[0] for p in py_init])
            conn.execute(
                "INSERT OR REPLACE INTO skill_pinyin (skill_name, pinyin_full, pinyin_nos, pinyin_initials) VALUES (?, ?, ?, ?)",
                (name, full_str, no_str, init_str)
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


def resolve_skill_name(user_input: str) -> str | None:
    """通过逐级匹配解析技能名称，支持同音字容错

    匹配顺序：
    1. 精确匹配 → 2. LIKE模糊 → 3. 拼音全拼 → 4. 首字母 → 5. 直接拼音查表
    """
    from pypinyin import pinyin, Style

    user_input = user_input.strip()
    if not user_input:
        return None

    conn = get_connection()
    try:
        # --- 1) 精确匹配 ---
        row = conn.execute(
            "SELECT name FROM skills WHERE name = ?", (user_input,)
        ).fetchone()
        if row:
            return row["name"]

        # --- 2) LIKE 模糊匹配 ---
        row = conn.execute(
            "SELECT name FROM skills WHERE name LIKE ?", (f"%{user_input}%",)
        ).fetchone()
        if row:
            return row["name"]

        # --- 3) 拼音全拼匹配 ---
        user_py = pinyin(user_input, style=Style.NORMAL)
        user_py_str = " ".join([p[0] for p in user_py])
        if user_py_str:
            row = conn.execute(
                "SELECT skill_name FROM skill_pinyin WHERE pinyin_nos = ?",
                (user_py_str,)
            ).fetchone()
            if row:
                return row["skill_name"]

        # --- 4) 拼音首字母匹配 ---
        user_init = pinyin(user_input, style=Style.FIRST_LETTER)
        user_init_str = "".join([p[0] for p in user_init])
        if user_init_str:
            row = conn.execute(
                "SELECT skill_name FROM skill_pinyin WHERE pinyin_initials = ?",
                (user_init_str,)
            ).fetchone()
            if row:
                return row["skill_name"]

        # --- 5) 直接拼音查表：纯英文（含空格）输入时直接当拼音搜 ---
        if user_input.isascii() and all(c.isalpha() or c.isspace() for c in user_input):
            base_nospace = user_input.lower().strip().replace(" ", "")
            row = conn.execute(
                "SELECT skill_name FROM skill_pinyin WHERE REPLACE(pinyin_nos, ' ', '') = ?",
                (base_nospace,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT skill_name FROM skill_pinyin WHERE REPLACE(pinyin_nos, ' ', '') LIKE ?",
                    (f"{base_nospace}%",)
                ).fetchone()
            if row:
                return row["skill_name"]

        return None
    finally:
        conn.close()


def resolve_spirit_name(user_input: str) -> str | None:
    """通过逐级匹配解析精灵名称，支持同音字容错

    匹配顺序：
    1. 精确匹配 → 2. LIKE模糊匹配 → 3. 拼音全拼匹配 → 4. 拼音首字母匹配 → 5. 直接拼音查表
    """
    from pypinyin import pinyin, Style

    user_input = user_input.strip()
    if not user_input:
        return None

    conn = get_connection()
    try:
        # --- 1) 精确匹配 ---
        row = conn.execute(
            "SELECT name FROM spirits WHERE name = ?", (user_input,)
        ).fetchone()
        if row:
            return row["name"]

        # --- 2) LIKE 模糊匹配（保持原来的 %name% 逻辑） ---
        row = conn.execute(
            "SELECT name FROM spirits WHERE name LIKE ?", (f"%{user_input}%",)
        ).fetchone()
        if row:
            return row["name"]

        # --- 3) 拼音全拼匹配：将用户输入也转成拼音，与 spirit_pinyin 表对比 ---
        user_py = pinyin(user_input, style=Style.NORMAL)
        user_py_str = " ".join([p[0] for p in user_py])

        if user_py_str:
            row = conn.execute(
                "SELECT spirit_name FROM spirit_pinyin WHERE pinyin_nos = ?",
                (user_py_str,)
            ).fetchone()
            if row:
                return row["spirit_name"]

        # --- 4) 拼音首字母匹配 ---
        user_init = pinyin(user_input, style=Style.FIRST_LETTER)
        user_init_str = "".join([p[0] for p in user_init])
        if user_init_str:
            row = conn.execute(
                "SELECT spirit_name FROM spirit_pinyin WHERE pinyin_initials = ?",
                (user_init_str,)
            ).fetchone()
            if row:
                return row["spirit_name"]

        # --- 5) 直接拼音查表：纯英文（含空格）输入时直接当拼音搜 ---
        if user_input.isascii() and all(c.isalpha() or c.isspace() for c in user_input):
            base_nospace = user_input.lower().strip().replace(" ", "")
            row = conn.execute(
                "SELECT spirit_name FROM spirit_pinyin WHERE REPLACE(pinyin_nos, ' ', '') = ?",
                (base_nospace,)
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT spirit_name FROM spirit_pinyin WHERE REPLACE(pinyin_nos, ' ', '') LIKE ?",
                    (f"{base_nospace}%",)
                ).fetchone()
            if row:
                return row["spirit_name"]

        return None
    finally:
        conn.close()


# ======================== 蛋查询 ========================


def query_egg_by_name(egg_name: str) -> dict | None:
    """根据蛋名或精灵名查询蛋信息"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM eggs WHERE egg_name = ? OR egg_name LIKE ? OR spirit_name = ? OR spirit_name LIKE ?",
            (egg_name, f"%{egg_name}%", egg_name, f"%{egg_name}%")
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def query_egg_by_spirit(spirit_name: str) -> list[dict]:
    """根据精灵名查询它的蛋"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM eggs WHERE spirit_name LIKE ?",
            (f"%{spirit_name}%",)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_all_eggs(limit: int = 20) -> list[dict]:
    """列出所有蛋"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM eggs ORDER BY spirit_name LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_egg_fuzzy(text: str) -> list[dict]:
    """模糊搜索蛋：按关键词逐字拆解匹配精灵名"""
    conn = get_connection()
    try:
        # 先用整词搜
        rows = conn.execute(
            "SELECT * FROM eggs WHERE spirit_name LIKE ?",
            (f"%{text}%",)
        ).fetchall()
        if rows:
            return [dict(r) for r in rows]
        # 逐字拆解：取所有字符组合去匹配
        chars = list(text)
        candidates = set()
        # 按每个字搜
        for c in chars:
            if '\u4e00' <= c <= '\u9fff':  # 只搜中文字
                r = conn.execute(
                    "SELECT egg_name, spirit_name FROM eggs WHERE spirit_name LIKE ?",
                    (f"%{c}%",)
                ).fetchall()
                for row in r:
                    candidates.add((row[0], row[1]))
        if candidates:
            return [{"egg_name": e, "spirit_name": s} for e, s in candidates]
        return []
    finally:
        conn.close()


# ======================== AI Agent 工具函数 ========================

def query_spirits_by_skill(skill_name: str, type_filter: str = "") -> list[dict]:
    """查询能学某技能的所有精灵（技能名支持同音字容错）

    Args:
        skill_name: 技能名称（支持模糊匹配和同音字）
        type_filter: 可选，按属性过滤（如 '火' 只返回火系精灵）

    Returns:
        [{"spirit_name": str, "learn_level": int, "learn_method": str, "type1": str, "type2": str}, ...]
    """
    conn = get_connection()
    try:
        # 先用 resolve_skill_name 处理同音字/拼音匹配
        resolved = resolve_skill_name(skill_name)
        if not resolved:
            return []

        # 再找技能
        skill = conn.execute(
            "SELECT id, name FROM skills WHERE name = ?", (resolved,)
        ).fetchone()
        if not skill:
            return []
        skill_id = skill["id"]

        if type_filter:
            # 带属性过滤：JOIN spirits 表筛选 type1 或 type2
            rows = conn.execute("""
                SELECT s.name AS spirit_name, s.type1, s.type2,
                       sk.learn_level, sk.learn_method
                FROM spirit_skills sk
                JOIN spirits s ON s.id = sk.spirit_id
                WHERE sk.skill_id = ?
                  AND (s.type1 = ? OR s.type2 = ?)
                ORDER BY sk.learn_level
            """, (skill_id, type_filter, type_filter)).fetchall()
        else:
            rows = conn.execute("""
                SELECT s.name AS spirit_name, s.type1, s.type2,
                       sk.learn_level, sk.learn_method
                FROM spirit_skills sk
                JOIN spirits s ON s.id = sk.spirit_id
                WHERE sk.skill_id = ?
                ORDER BY sk.learn_level
            """, (skill_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_db_stats() -> dict:
    """返回知识库统计信息"""
    conn = get_connection()
    try:
        stats = {}
        stats["spirits"] = conn.execute("SELECT COUNT(*) as n FROM spirits").fetchone()["n"]
        stats["skills"] = conn.execute("SELECT COUNT(*) as n FROM skills").fetchone()["n"]
        stats["spirit_skills"] = conn.execute("SELECT COUNT(*) as n FROM spirit_skills").fetchone()["n"]
        stats["type_effectiveness"] = conn.execute("SELECT COUNT(*) as n FROM type_effectiveness").fetchone()["n"]
        stats["items"] = conn.execute("SELECT COUNT(*) as n FROM items").fetchone()["n"]
        stats["eggs"] = conn.execute("SELECT COUNT(*) as n FROM eggs").fetchone()["n"]
        stats["spirit_types"] = [r["type1"] for r in conn.execute(
            "SELECT DISTINCT type1 FROM spirits WHERE type1 IS NOT NULL ORDER BY type1"
        ).fetchall()]
        return stats
    finally:
        conn.close()


def in_scope_check(question: str) -> dict:
    """判断问题是否属于洛克王国知识库的范围
    
    Args:
        question: 用户的问题
    
    Returns:
        {"in_scope": bool, "reason": str, "suggestions": list[str]}
    """
    # 基本问候关键词
    greetings = ["你好", "你好吗", "hello", "hi", "嗨", "早上好", "晚上好",
                  "谢谢", "感谢", "再见", "拜拜", "bye", "你是谁", "你叫什么"]
    
    # 明确不是洛克王国的话题（其他游戏/动漫/现实）
    negative_keywords = [
        "魔兽世界", "wow", "魔兽", "原神", "genshin", "元神",
        "英雄联盟", "lol", "王者荣耀", "和平精英",
        "我的世界", "minecraft", "塞尔达",
        "宝可梦", "pokemon", "口袋妖怪", "神奇宝贝",
        "最终幻想", "ff14", "ff7",
        "明日方舟", "arknights", "崩坏", "星穹铁道",
        "碧蓝航线", "fgo", "fate",
        "dota", "csgo", "守望先锋", "overwatch",
        "动漫", "电视剧", "电影", "小说",
        "数学", "物理", "化学", "历史",
        "天气", "新闻", "股票",
        "python", "java", "代码", "编程",
    ]
    
    # 洛克王国相关关键词
    loke_keywords = [
        "洛克", "洛克王国", "王国", "精灵", "宠物", "技能", "招式", "道具", "物品",
        "克制", "属性", "蛋", "孵化", "进化", "火神", "水蓝蓝", "喵喵", "火花",
        "迪莫", "阿布", "雷霆", "冰系", "火系", "水系", "草系", "石系", "龙系",
        "翼系", "萌系", "毒系", "虫系", "机械", "普通", "幽灵", "土系",
        "小智", "知识库", "打不过", "怎么打",
    ]
    
    q = question.lower().strip()
    
    # 先扫负面关键词：如果包含其他游戏/动漫名，直接拒绝（除非是问候）
    for g in greetings:
        if g in q:
            return {"in_scope": True, "reason": "greeting", "suggestions": []}
    
    for nk in negative_keywords:
        if nk in q:
            return {"in_scope": False, "reason": "negative_keyword_match",
                    "suggestions": ["小智只知道洛克王国的事情哦~"]}
    
    # 检查洛克王国关键词
    for kw in loke_keywords:
        if kw in question:
            return {"in_scope": True, "reason": "keyword_match", "suggestions": []}
    
    # 检查精灵名和技能名（通过数据库模糊搜索）
    conn = get_connection()
    try:
        # 检查是否是精灵名
        spirit = conn.execute(
            "SELECT name FROM spirits WHERE name LIKE ? LIMIT 1",
            (f"%{question[:4]}%",)
        ).fetchone()
        if spirit:
            return {"in_scope": True, "reason": "spirit_match", "suggestions": []}
        
        # 检查是否是技能名
        skill = conn.execute(
            "SELECT name FROM skills WHERE name LIKE ? LIMIT 1",
            (f"%{question[:4]}%",)
        ).fetchone()
        if skill:
            return {"in_scope": True, "reason": "skill_match", "suggestions": []}
    finally:
        conn.close()
    
    return {"in_scope": False, "reason": "out_of_scope",
            "suggestions": ["试试问问洛克王国相关的问题~"]}
