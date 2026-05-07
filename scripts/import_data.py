# scripts/import_data.py
# 洛克王国知识库数据导入脚本（骨架，可扩展）

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import json
import csv
import pandas as pd
from loguru import logger
from src.core.database import init_db, get_connection
from src.core.vector_store import add_documents


def import_spirits_from_csv(csv_path: str):
    """从 CSV 导入精灵数据到 SQLite"""
    conn = get_connection()
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    count = 0
    with conn:
        for _, row in df.iterrows():
            conn.execute("""
                INSERT OR REPLACE INTO spirits
                (name, number, type1, type2, description, egg_group, evolution_chain, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("name", ""),
                row.get("number", ""),
                row.get("type1", ""),
                row.get("type2", ""),
                row.get("description", ""),
                row.get("egg_group", ""),
                row.get("evolution_chain", ""),
                row.get("image_path", ""),
            ))
            count += 1
    conn.close()
    logger.info(f"导入 {count} 条精灵数据")


def import_skills_from_csv(csv_path: str):
    """从 CSV 导入技能数据到 SQLite"""
    conn = get_connection()
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    count = 0
    with conn:
        for _, row in df.iterrows():
            conn.execute("""
                INSERT OR REPLACE INTO skills
                (name, skill_type, power, accuracy, pp, description, effect)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                row.get("name", ""),
                row.get("skill_type", ""),
                int(row.get("power", 0)) if pd.notna(row.get("power")) else None,
                int(row.get("accuracy", 0)) if pd.notna(row.get("accuracy")) else None,
                int(row.get("pp", 0)) if pd.notna(row.get("pp")) else None,
                row.get("description", ""),
                row.get("effect", ""),
            ))
            count += 1
    conn.close()
    logger.info(f"导入 {count} 条技能数据")


def build_vector_docs_from_csv(qa_csv_path: str):
    """从 Q&A CSV 构建向量文档并导入 Chroma"""
    df = pd.read_csv(qa_csv_path, encoding="utf-8-sig")
    docs = []
    for _, row in df.iterrows():
        q = row.get("question", "")
        a = row.get("answer", "")
        if not q or not a:
            continue
        docs.append({
            "id": f"qa_{row.name}",
            "text": f"问：{q}\n答：{a}",
            "metadata": {
                "question": q,
                "category": row.get("category", "general"),
            }
        })
    if docs:
        add_documents(docs)
        logger.info(f"向量库导入 {len(docs)} 条 Q&A 数据")


def main():
    init_db()

    import_dir = Path(__file__).parent.parent / "data" / "import"
    print(f"数据目录: {import_dir}")
    print("\n请确认是否有以下数据文件：")
    print("  - spirits.csv    精灵数据")
    print("  - skills.csv     技能数据")
    print("  - qa_pairs.csv   问答对数据")
    print("\n将对应 CSV 文件放入 data/import/ 后重新运行本脚本。")
    print("按 Enter 退出...")
    input()


if __name__ == "__main__":
    main()
