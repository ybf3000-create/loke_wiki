# scripts/build_pinyin_index.py
# 构建精灵+技能拼音索引表（用于语音输入同音字容错）
# 运行一次即可，后续新增数据后需重新运行

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from src.core.database import (
    init_db, get_connection,
    rebuild_pinyin_index, rebuild_skill_pinyin_index,
)


def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>")

    logger.info("=" * 50)
    logger.info("构建精灵 + 技能拼音索引")
    logger.info("=" * 50)

    # 确保表存在
    init_db()

    # 精灵拼音
    spirit_count = rebuild_pinyin_index()
    logger.info(f"✅ 精灵拼音索引构建完成，共 {spirit_count} 只")

    # 技能拼音
    skill_count = rebuild_skill_pinyin_index()
    logger.info(f"✅ 技能拼音索引构建完成，共 {skill_count} 个")

    # 展示几条示例
    conn = get_connection()
    try:
        logger.info("精灵示例：")
        rows = conn.execute(
            "SELECT spirit_name, pinyin_nos, pinyin_initials FROM spirit_pinyin LIMIT 5"
        ).fetchall()
        for r in rows:
            logger.info(f"  {r['spirit_name']} → {r['pinyin_nos']} ({r['pinyin_initials']})")

        logger.info("技能示例：")
        rows = conn.execute(
            "SELECT skill_name, pinyin_nos, pinyin_initials FROM skill_pinyin LIMIT 5"
        ).fetchall()
        for r in rows:
            logger.info(f"  {r['skill_name']} → {r['pinyin_nos']} ({r['pinyin_initials']})")
    finally:
        conn.close()

    logger.info("=" * 50)
    logger.info(f"全部完成！精灵: {spirit_count}, 技能: {skill_count}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
