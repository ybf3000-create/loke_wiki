# -*- coding: utf-8 -*-
"""
洛克王国：世界手游 18 属性统一克制表导入脚本
将旧版 type_effectiveness（仅单属性）替换为统一四属性表，
同时包含：单属性vs单属性 + 单属性vs双属性

表结构：
  atk_type1 | atk_type2 | def_type1 | def_type2 | multiplier
  单属性时 type2 字段为 '无'
"""

import sqlite3
from itertools import combinations
from pathlib import Path
from datetime import datetime

# ==================== 配置 ====================
DB_PATH = Path("G:/LuoKeHP/loke_wiki/data/db/loke_wiki.db")

# 18 属性（按 wiki 截图中的行/列顺序）
TYPES = ["普通", "草", "火", "水", "光", "地", "冰", "龙",
         "电", "毒", "虫", "武", "翼", "萌", "幽", "恶", "机械", "幻"]

# wiki 截图中的 18x18 矩阵（行=防御方，列=攻击方）
# 逐行严格对照截图数据
MATRIX = [
    # 普  草  火  水  光  地  冰  龙  电  毒  虫  武  翼  萌  幽  恶  机  幻
    [1,   1,   1,   1,   1,   1,   1,   1,   1,   1,   1,   2,   1,   1, 0.5,  1,   1,   1],  # 普通
    [1,   1,   2, 0.5, 0.5, 0.5,   2,   1, 0.5,   2,   2,   1,   2,   1,   1,   1,   1,   1],  # 草
    [1, 0.5,   1,   2,   1,   2, 0.5,   1,   1,   1, 0.5,   1,   1, 0.5,   1,   1, 0.5,   1],  # 火
    [1,   2, 0.5,   1,   1,   1,   1,   1,   2,   1,   1,   1,   1,   1,   1,   1, 0.5,   1],  # 水
    [1,   2,   1,   1,   1,   1,   1,   1,   1,   1,   1,   1,   1,   1,   2, 0.5,   1, 0.5],  # 光
    [0.5, 2, 0.5,   2,   1,   1,   2,   1, 0.5, 0.5,   1,   2, 0.5,   1,   1,   1,   2,   1],  # 地
    [1,   1,   2, 0.5, 0.5,   2, 0.5,   1,   1,   1,   1,   2,   1,   1,   1,   1,   2,   1],  # 冰
    [1, 0.5, 0.5, 0.5,   1,   1,   2,   2, 0.5,   1,   1,   1, 0.5,   2,   1,   1,   1,   1],  # 龙
    [1,   1,   1,   1,   1,   2,   1,   2, 0.5,   1,   1,   1, 0.5,   1,   1,   1, 0.5,   1],  # 电
    [1, 0.5,   1,   1,   1,   2,   1,   1,   1, 0.5, 0.5, 0.5,   1, 0.5,   1,   2,   1,   2],  # 毒
    [1, 0.5,   2,   1,   1,   1,   1,   1,   1,   1,   1, 0.5,   2,   1,   1,   1,   1,   1],  # 虫
    [1,   1,   1,   1,   1, 0.5,   1,   1,   1,   1, 0.5,   1,   2,   2,   1, 0.5,   1,   2],  # 武
    [1, 0.5,   1,   1,   1,   1,   2,   1,   2,   1, 0.5, 0.5,   1,   1,   1,   1,   1,   1],  # 翼
    [1,   1,   1,   1,   1,   1,   1,   1,   1,   2, 0.5, 0.5,   1,   1,   1,   2,   2,   1],  # 萌
    [0.5, 1,   1,   1,   2,   1,   1,   1,   1, 0.5, 0.5, 0.5,   1,   1,   2,   2,   1,   1],  # 幽
    [1,   1,   1,   1,   2,   1,   1,   1,   1,   1,   2,   2,   1,   2, 0.5, 0.5,   1,   1],  # 恶
    [0.5,0.5,  2,   2,   1,   1, 0.5, 0.5,   1, 0.5, 0.5,   2, 0.5, 0.5,   1,   1, 0.5, 0.5],  # 机械
    [1,   1,   1,   1,   1,   1,   1,   1,   1,   1,   2, 0.5,   1,   1,   2,   1,   1, 0.5],  # 幻
]


def normalize_pair(t1: str, t2: str) -> tuple:
    """将双属性按字典序标准化，保证虫+翼 和 翼+虫 是同一组合"""
    if t1 == "无":
        return (t1, t2)
    if t2 == "无":
        return (t1, t2)
    if t1 == t2:
        return (t1, t2)
    return tuple(sorted([t1, t2]))


def get_single_multiplier(atk: str, df: str) -> float:
    """从矩阵查单属性倍率"""
    i = TYPES.index(df)
    j = TYPES.index(atk)
    return MATRIX[i][j]


def main():
    now = datetime.now().isoformat(timespec="seconds")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # ---- 1. 备份旧表 ----
    old_count = cur.execute("SELECT COUNT(*) FROM type_effectiveness").fetchone()[0]
    cur.execute("DROP TABLE IF EXISTS type_effectiveness_old_backup")
    cur.execute("ALTER TABLE type_effectiveness RENAME TO type_effectiveness_old_backup")
    print(f"✅ 旧表已备份为 type_effectiveness_old_backup ({old_count}行)")

    # ---- 2. 创建新表 ----
    cur.execute("""
        CREATE TABLE type_effectiveness (
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
    conn.commit()
    print("✅ 新表 type_effectiveness 已创建")

    # ---- 3. 导入单属性数据 (18*18 = 324行) ----
    rows_single = []
    for def_idx, def_type in enumerate(TYPES):
        for atk_idx, atk_type in enumerate(TYPES):
            mult = MATRIX[def_idx][atk_idx]
            rows_single.append((atk_type, "无", def_type, "无", mult, "wiki_world_2026-05-09", now))

    cur.executemany(
        "INSERT OR REPLACE INTO type_effectiveness(atk_type1, atk_type2, def_type1, def_type2, multiplier, source, updated_at) VALUES (?,?,?,?,?,?,?)",
        rows_single
    )
    conn.commit()
    print(f"✅ 单属性数据导入完成 (18*18={len(rows_single)}行)")

    # ---- 4. 生成双属性数据 ----
    # 4a. 单属性攻击 vs 双属性防御 (18 * C(18,2) = 18*153 = 2754行)
    rows_dual = []
    for def_t1, def_t2 in combinations(TYPES, 2):
        # 标准化双属性顺序
        d1, d2 = sorted([def_t1, def_t2])
        for atk_type in TYPES:
            m1 = get_single_multiplier(atk_type, d1)
            m2 = get_single_multiplier(atk_type, d2)
            total = m1 * m2
            rows_dual.append((atk_type, "无", d1, d2, total, "wiki_world_2026-05-09", now))

    # 4b. 同属性防御组合 (18行)
    for t in TYPES:
        m = get_single_multiplier(t, t)
        total = m * m
        rows_dual.append((t, "无", t, t, total, "wiki_world_2026-05-09", now))

    # 4c. 双属性攻击 vs 单属性防御 (C(18,2) * 18 = 2754行)
    # 注意：双属性攻击的倍率 = min(属性1倍率, 属性2倍率) × 某种规则
    # 按洛克王国规则：双属性攻击时取"克制效果最大的一方"作为主属性来计算
    # 但严格来说双系攻击的算法在不同版本有不同解释
    # 这里保守仅生成"单属性攻击vs双属性防御"和"单属性攻击vs单属性防御"
    # 双属性攻击vs单属性防御的相关规则后续可扩展

    cur.executemany(
        "INSERT OR REPLACE INTO type_effectiveness(atk_type1, atk_type2, def_type1, def_type2, multiplier, source, updated_at) VALUES (?,?,?,?,?,?,?)",
        rows_dual
    )
    conn.commit()
    total_dual = len(rows_dual)
    print(f"✅ 双属性数据导入完成 (单攻vs双防: 18*153=2754 + 同属性: 18 共{total_dual}行)")

    # ---- 5. 校验 ----
    grand_total = cur.execute("SELECT COUNT(*) FROM type_effectiveness").fetchone()[0]
    print(f"\n📊 总行数: {grand_total}")
    print(f"   - 单属性: {len(rows_single)}")
    print(f"   - 双属性: {total_dual}")

    # 校验: 花魁蜂后(虫+翼) 被谁4倍克制
    # 按用户规则：虫+翼 双属性防御下查单属性攻击×2 = 4
    print("\n🔍 校验: 虫+翼 4倍克制来源")
    four_x = []
    for atk in TYPES:
        cur.execute(
            "SELECT multiplier FROM type_effectiveness WHERE atk_type1=? AND atk_type2='无' AND def_type1='虫' AND def_type2='翼'",
            (atk,)
        )
        row = cur.fetchone()
        if row and row["multiplier"] == 4.0:
            four_x.append(atk)
    if four_x:
        print(f"   ✅ 4倍来源: {four_x}")
    else:
        print(f"   ⚠️ 无4倍来源")

    # 校验: 双属性2倍来源
    two_x = []
    for atk in TYPES:
        cur.execute(
            "SELECT multiplier FROM type_effectiveness WHERE atk_type1=? AND atk_type2='无' AND def_type1='虫' AND def_type2='翼'",
            (atk,)
        )
        row = cur.fetchone()
        if row and row["multiplier"] == 2.0:
            two_x.append(atk)
    print(f"   2倍来源: {two_x}")

    # 校验: 石系打虫
    cur.execute("SELECT multiplier FROM type_effectiveness WHERE atk_type1='石' AND atk_type2='无' AND def_type1='虫' AND def_type2='无'")
    row = cur.fetchone()
    print(f"\n🔍 校验: 石打虫 = {row['multiplier'] if row else 'NOT FOUND'}倍")

    # ---- 6. 打印双属性全表摘要 ----
    print("\n📋 双属性防御全表摘要（列出各倍率的组合数）:")
    # 统计每个双属性组合被哪些攻击属性打出不同倍率
    combos = list(combinations(TYPES, 2))
    summary = {}
    for d1, d2 in sorted([sorted([x, y]) for x, y in combos]):
        key = f"{d1}+{d2}"
        mults = {}
        for atk in TYPES:
            cur.execute(
                "SELECT multiplier FROM type_effectiveness WHERE atk_type1=? AND atk_type2='无' AND def_type1=? AND def_type2=?",
                (atk, d1, d2)
            )
            row = cur.fetchone()
            if row:
                m = row["multiplier"]
                mults[m] = mults.get(m, 0) + 1
        summary[key] = mults

    # 展示几个关键组合
    for key in ["虫+翼", "火+草", "水+土", "石+虫", "草+虫"]:
        if key in summary:
            print(f"  {key}: {summary[key]}")

    conn.close()
    print("\n🎉 导入完成!")


if __name__ == "__main__":
    main()
