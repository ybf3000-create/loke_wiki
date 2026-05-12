# scripts/scrape_abilities.py
# 爬取所有精灵的"特性"数据，补充到数据库
# 数据来源: https://wiki.biligame.com/rocom/

import sys, re, time, random
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.core.database import init_db, get_connection, update_spirit_ability

# ======================== 配置 ========================
BASE_URL = "https://wiki.biligame.com/rocom"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
REQUEST_DELAY = 0.5  # 秒

session = requests.Session()
session.headers.update(HEADERS)


def fetch_html(url: str) -> str:
    """获取页面HTML"""
    logger.info(f"请求: {url}")
    resp = session.get(url, timeout=30)
    resp.encoding = "utf-8"
    time.sleep(REQUEST_DELAY + random.random() * 0.5)
    return resp.text


def fmt_url(path: str) -> str:
    if path.startswith("http"):
        return path
    if path.startswith("/rocom/"):
        return f"https://wiki.biligame.com{path}"
    return f"{BASE_URL}{path}"


def scrape_ability_from_detail(name: str, url: str) -> tuple[str, str]:
    """爬取单个精灵详情页的"特性"数据

    Returns:
        (ability_name, ability_effect) 或 ("", "")
    """
    try:
        html = fetch_html(url)
    except Exception as e:
        logger.error(f"  获取页面失败: {e}")
        return "", ""

    soup = BeautifulSoup(html, "lxml")

    ability = ""
    ability_effect = ""

    # 解析特性（已确认CSS选择器有效）
    # HTML结构:
    #   <p class="rocom_sprite_info_characteristic_title">最好的伙伴</p>
    #   <p class="rocom_sprite_info_characteristic_text">造成克制伤害后...</p>
    trait_title = soup.select_one(".rocom_sprite_info_characteristic_title")
    if trait_title:
        ability = trait_title.get_text(strip=True)

    trait_text = soup.select_one(".rocom_sprite_info_characteristic_text")
    if trait_text:
        ability_effect = trait_text.get_text(strip=True)

    if ability:
        logger.info(f"  ✅ 特性: {ability} — {ability_effect[:40] if ability_effect else '无效果描述'}...")
    else:
        logger.info(f"  ⚠️ 未找到特性数据")

    return ability, ability_effect


def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>")
    logger.add(str(PROJECT_ROOT / "logs" / "scrape_abilities_{time:YYYY-MM-DD}.log"),
               level="DEBUG", rotation="1 day", retention="3 days", encoding="utf-8")

    logger.info("=" * 60)
    logger.info("洛克王国世界 BWIKI 精灵特性爬虫")
    logger.info("=" * 60)

    # 确保数据库初始化
    init_db()

    # 获取所有精灵名称
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM spirits ORDER BY id"
        ).fetchall()
        spirit_names = [r["name"] for r in rows]
    finally:
        conn.close()

    logger.info(f"共需处理 {len(spirit_names)} 个精灵")

    # 逐精灵爬取
    success = 0
    skip = 0
    for i, name in enumerate(spirit_names):
        logger.info(f"[{i+1}/{len(spirit_names)}] {name}")

        # 构造标准 URL
        name_encoded = requests.utils.quote(name)
        url = fmt_url(f"/{name_encoded}")

        ability, effect = scrape_ability_from_detail(name, url)

        if ability:
            ok = update_spirit_ability(name, ability, effect)
            if ok:
                success += 1
                logger.info(f"  💾 写入成功")
            else:
                logger.warning(f"  ⚠️ 写入失败（未找到精灵匹配）")
        else:
            skip += 1
            logger.info(f"  ⏭️ 跳过（无特性）")

    logger.info("=" * 60)
    logger.info(f"特性爬取完成！成功: {success}, 跳过(无特性): {skip}, 总数: {len(spirit_names)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
