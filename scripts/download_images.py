# scripts/download_images.py
# 下载精灵立绘 + 精灵蛋图片

import sys, os, time, re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup
from loguru import logger
from config.settings import IMAGES_DIR

# ======================== 配置 ========================
BASE_URL = "https://wiki.biligame.com/rocom"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
REQUEST_DELAY = 0.3
session = requests.Session()
session.headers.update(HEADERS)


def fetch_html(url: str) -> str:
    resp = session.get(url, timeout=30)
    resp.encoding = "utf-8"
    time.sleep(REQUEST_DELAY)
    return resp.text


def download_image(url: str, filepath: Path) -> bool:
    """下载图片到指定路径"""
    if filepath.exists() and filepath.stat().st_size > 1024:
        return True  # 已存在
    try:
        resp = session.get(url, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 500:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(resp.content)
            return True
    except Exception as e:
        logger.warning(f"下载失败 {url}: {e}")
    return False


# ======================== 1. 下载精灵立绘 ========================

def download_spirit_images(max_count: int = None) -> int:
    """从精灵图鉴页面提取并下载所有精灵的立绘"""
    logger.info("===== 下载精灵立绘 =====")
    html = fetch_html(f"{BASE_URL}/%E7%B2%BE%E7%81%B5%E5%9B%BE%E9%89%B4")
    soup = BeautifulSoup(html, "lxml")

    downloaded = 0
    for card in soup.select("div.rocom_prop_img.new_page_link"):
        # 精灵名
        name_el = card.select_one("p.rocom_prop_name.block_2 a")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)

        # 立绘图片URL（rocom_prop_icon 是大立绘）
        icon_el = card.select_one("img.rocom_prop_icon")
        if not icon_el:
            continue
        src = icon_el.get("src", "")
        srcset = icon_el.get("srcset", "")
        # 取最大图：srcset中有2x的图（分辨率最高）
        best_url = src
        if srcset:
            parts = srcset.split(",")
            for p in parts:
                p = p.strip()
                if "2x" in p or "360px" in p:
                    best_url = p.split(" ")[0]
                    break

        if best_url.startswith("//"):
            best_url = "https:" + best_url
        elif best_url.startswith("/"):
            best_url = f"https://wiki.biligame.com{best_url}"

        # 保存为 {精灵名}.png
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', name)
        filepath = IMAGES_DIR / f"{safe_name}.png"

        if download_image(best_url, filepath):
            downloaded += 1
            if downloaded % 25 == 0:
                logger.info(f"  已下载 {downloaded} 张精灵立绘")
        else:
            logger.debug(f"  {name}: 下载失败")

        if max_count and downloaded >= max_count:
            break

    logger.info(f"精灵立绘下载完成: {downloaded} 张")
    return downloaded


# ======================== 2. 下载精灵蛋图片 ========================

def download_egg_images() -> list[dict]:
    """从精灵蛋图鉴页面提取并下载精灵蛋图片"""
    logger.info("===== 下载精灵蛋图片 =====")
    html = fetch_html(f"{BASE_URL}/%E7%B2%BE%E7%81%B5%E8%9B%8B%E5%9B%BE%E9%89%B4")
    soup = BeautifulSoup(html, "lxml")

    eggs = []
    downloaded = 0

    # 从img标签提取蛋数据（alt格式: "Egg miaomiao.png"）
    for img in soup.select("img[src*='patchwiki']"):
        alt = img.get("alt", "").strip()
        if not alt.startswith("Egg") or "图标" in alt or "格式" in alt:
            continue
        # 提取蛋名: "Egg miaomiao.png" -> "喵喵的蛋"
        egg_file = alt  # 如 "Egg miaomiao.png"
        src = img.get("src", "")
        if src.startswith("//"):
            src = "https:" + src

        # 从文件名推断中文蛋名
        # Egg_miaomiao.png -> 从精灵名映射
        egg_name = alt.replace(".png", "").strip()

        safe_name = re.sub(r'[<>:"/\\|?*\s]', '_', egg_name)
        egg_dir = IMAGES_DIR / "eggs"
        filepath = egg_dir / f"{safe_name}.png"

        if download_image(src, filepath):
            downloaded += 1

        eggs.append({
            "egg_name": egg_name,
            "filepath": str(filepath.relative_to(IMAGES_DIR.parent)),
            "image_path": str(filepath),
        })

    logger.info(f"精灵蛋图片下载完成: {downloaded} 张, 共{len(eggs)}条")
    return eggs


# ======================== 3. 保存蛋数据到SQLite ========================

def save_eggs_to_db(eggs: list[dict]):
    """将蛋数据保存到数据库"""
    from src.core.database import get_connection
    conn = get_connection()

    # 创建蛋表
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

    with conn:
        for egg in eggs:
            en = egg["egg_name"]  # 如 "Egg miaomiao.png"
            # 转为友好的蛋名显示名: "Egg miaomiao.png" -> "喵喵的蛋"
            # 从文件名提取精灵名
            display_name = en.replace("Egg_", "").replace(".png", "")
            # 去掉数字/后缀，转为中文名
            spirit_name = display_name
            # 去后缀: miaomiao -> 喵喵（如果精灵表中有匹配）

            conn.execute("""
                INSERT OR REPLACE INTO eggs
                (egg_name, spirit_name, image_path, category)
                VALUES (?, ?, ?, ?)
            """, (
                display_name,
                spirit_name,
                egg["image_path"],
                "普通",
            ))

    conn.close()
    logger.info(f"蛋数据已保存: {len(eggs)} 条")


# ======================== 4. 启动入口 ========================

def update_spirit_image_paths():
    """更新数据库中精灵的图片路径"""
    from src.core.database import get_connection
    conn = get_connection()
    with conn:
        for img_file in IMAGES_DIR.glob("*.png"):
            name = img_file.stem  # 不带扩展名的文件名
            conn.execute(
                "UPDATE spirits SET image_path = ? WHERE name = ?",
                (str(img_file), name)
            )
    conn.close()
    logger.info("精灵图片路径已更新到数据库")


def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO",
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>")

    # 1. 下载精灵立绘
    spirit_count = download_spirit_images()
    if spirit_count > 0:
        update_spirit_image_paths()

    # 2. 下载精灵蛋图片
    eggs = download_egg_images()
    if eggs:
        save_eggs_to_db(eggs)

    logger.info("=" * 50)
    logger.info(f"全部完成! 精灵立绘: {spirit_count}张, 蛋图片: {len(eggs)}张")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
