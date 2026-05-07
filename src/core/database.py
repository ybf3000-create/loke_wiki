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
                image_path  TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
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
        # 属性克制表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS type_effectiveness (
                attacker    TEXT NOT NULL,
                defender    TEXT NOT NULL,
                multiplier  REAL NOT NULL,
                PRIMARY KEY (attacker, defender)
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
        logger.info("数据库初始化完成")
    conn.close()


# ======================== 查询函数 ========================

def query_spirit(name: str) -> dict | None:
    """根据精灵名称查询完整信息"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM spirits WHERE name = ? OR name LIKE ?",
            (name, f"%{name}%")
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
    """查询技能详情"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM skills WHERE name = ? OR name LIKE ?",
            (name, f"%{name}%")
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def query_type_effectiveness(attacker: str, defender: str) -> float | None:
    """查询属性克制倍率"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT multiplier FROM type_effectiveness WHERE attacker = ? AND defender = ?",
            (attacker, defender)
        ).fetchone()
        return row["multiplier"] if row else None
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
