# scripts/scrape_bwiki.py
# 洛克王国世界 BWIKI 数据爬虫
# 数据来源: https://wiki.biligame.com/rocom/

import sys, re, json, time, random
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.core.database import init_db, get_connection

# ======================== 配置 ========================
BASE_URL = "https://wiki.biligame.com/rocom"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
REQUEST_DELAY = 0.3  # 秒，请求间隔

# ======================== 工具函数 ========================

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
    # BWIKI链接已经是 /rocom/xxx 或 /xxx，BASE_URL = https://wiki.biligame.com/rocom
    if path.startswith("/rocom/"):
        return f"https://wiki.biligame.com{path}"
    return f"{BASE_URL}{path}"


# ======================== 1. 爬取精灵列表 ========================

def scrape_spirit_list() -> list[dict]:
    """
    从BWIKI精灵图鉴页提取所有精灵基本信息
    返回 [{"number": int, "name": str, "url": str, "types": [str,...], "has_shiny": bool}, ...]
    
    BWIKI页面结构: 每个精灵卡片是 div.rocom_prop_img.new_page_link
    """
    logger.info("===== 开始爬取精灵列表 =====")
    html = fetch_html(f"{BASE_URL}/%E7%B2%BE%E7%81%B5%E5%9B%BE%E9%89%B4")
    soup = BeautifulSoup(html, "lxml")

    # 属性名称映射（从图片alt属性解析）
    TYPE_ALT_MAP = {}
    for t in ["普通","草","火","水","光","地","冰","龙","电","毒","虫","武","翼","萌","幽","恶","机械","幻"]:
        TYPE_ALT_MAP[t] = t

    spirits = []
    # 每个精灵卡片
    for card in soup.select("div.rocom_prop_img.new_page_link"):
        # 名称
        name_el = card.select_one("p.rocom_prop_name.block_2 a")
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        url = fmt_url(href) if href else ""

        # 编号
        num_el = card.select_one("p.rocom_prop_name.block_1 a span")
        number = 0
        if num_el:
            m = re.search(r'(\d+)', num_el.get_text())
            if m:
                number = int(m.group(1))

        # 属性：从 rocom_pet_icon 图片的 alt 解析
        types = []
        for img in card.select("img.rocom_pet_icon"):
            alt = img.get("alt", "")
            # alt格式如 "图标 宠物 属性 光.png"
            for t in TYPE_ALT_MAP:
                if t in alt.replace("图标 宠物 属性 ", "").replace(".png", ""):
                    if t not in types:
                        types.append(t)

        spirits.append({
            "number": number,
            "name": name,
            "url": url,
            "types": types,
            "has_shiny": False,
        })

    logger.info(f"找到 {len(spirits)} 个精灵")
    return spirits


# ======================== 2. 爬取精灵详情 ========================

def scrape_spirit_detail(name: str, url: str) -> dict:
    """爬取单个BWIKI精灵详情页"""
    logger.info(f"爬取详情: {name}")
    try:
        html = fetch_html(url)
    except Exception as e:
        logger.error(f"获取 {name} 页面失败: {e}")
        return {}

    soup = BeautifulSoup(html, "lxml")
    data = {"name": name, "source_url": url}

    # --- 编号 ---
    # 搜索多种格式: "NO.007", "No. 1", "001" 在title/标题/文本中
    title_tag = soup.find("title")
    if title_tag:
        m = re.search(r'NO\.?\s*(\d+)', title_tag.get_text(), re.I)
        if m:
            data["number"] = m.group(1)
    if not data.get("number"):
        m = re.search(r'NO\.?\s*(\d+)', html[:2000], re.I)
        if m:
            data["number"] = m.group(1)
    if not data.get("number"):
        # 从页面文本找 "NO.007" 或 "编号007"
        m = re.search(r'(?:NO\.?|编号)[：:]*\s*(\d+)', html[:5000], re.I)
        if m:
            data["number"] = m.group(1)

    # --- 属性 (从详情页准确提取，排除技能区干扰) ---
    types = []
    # 只在精灵信息面板区域找属性
    info_areas = soup.select(".rocom_sprite_info_attributes, .rocom_sprite_info, .rocom_sprite_info_qualification, .rocom_sprite_info_basic")
    for area in info_areas:
        for img in area.select("img[alt*='属性']"):
            alt = img.get("alt", "")
            for t in ["普通","草","火","水","光","地","冰","龙","电","毒","虫","武","翼","萌","幽","恶","机械","幻"]:
                if f"属性 {t}" in alt and t not in types:
                    types.append(t)
    # fallback: 从页面前2000字找
    if not types:
        for match in re.finditer(r'属性[：:]\s*([\u4e00-\u9fff]+)', html[:2000]):
            for t in ["普通","草","火","水","光","地","冰","龙","电","毒","虫","武","翼","萌","幽","恶","机械","幻"]:
                if t in match.group(1) and t not in types:
                    types.append(t)
    data["type1"] = types[0] if len(types) > 0 else ""
    data["type2"] = types[1] if len(types) > 1 else ""

    # --- 种族值 ---
    stat_map = {"生命": "hp", "物攻": "atk", "魔攻": "spatk", "物防": "def", "魔防": "spdef", "速度": "spd"}
    for li in soup.select("li:has(.rocom_sprite_info_qualification_name)"):
        name_el = li.select_one(".rocom_sprite_info_qualification_name")
        val_el = li.select_one(".rocom_sprite_info_qualification_value")
        if name_el and val_el:
            cn = name_el.get_text(strip=True)
            val_text = val_el.get_text(strip=True)
            if cn in stat_map and val_text.isdigit():
                data[stat_map[cn]] = int(val_text)

    # 种族总和
    after_race = re.search(r'种族值\s*</p>\s*<p>\s*(\d+)', html)
    if after_race:
        data["total_stats"] = int(after_race.group(1))

    # --- 特性 ---
    trait_el = soup.select_one(".rocom_sprite_info_characteristic_title")
    if trait_el:
        data["trait"] = trait_el.get_text(strip=True)
    trait_text = soup.select_one(".rocom_sprite_info_characteristic_text")
    if trait_text:
        data["trait_effect"] = trait_text.get_text(strip=True)

    # --- 描述/背景 ---
    # 排除style标签内容
    for tag in soup.select("style, script"):
        tag.decompose()
    desc_section = soup.select_one(".rocom_sprite_info_backstory_content, .rocom_sprite_info_backstory")
    if desc_section:
        data["description"] = desc_section.get_text(strip=True)
    # 备用：找引号内的描述文本（至少10个字）
    if not data.get("description"):
        m = re.search(r'[""]([\u4e00-\u9fff，。！？、]{20,})[""]', html)
        if m:
            data["description"] = m.group(1)

    # --- 进化链 ---
    evo_container = soup.select_one(".rocom_sprite_info_evolution")
    if evo_container:
        evo_names = [a.get_text(strip=True) for a in evo_container.select("a")]
        if evo_names:
            data["evolution_chain"] = " → ".join(evo_names)

    # --- 技能 ---
    skills = []
    for skill_box in soup.select(".rocom_sprite_skill_box"):
        lv_el = skill_box.select_one(".rocom_sprite_skill_level")
        name_el = skill_box.select_one(".rocom_sprite_skillName")
        type_el = skill_box.select_one(".rocom_sprite_skillType")
        attr_el = skill_box.select_one(".rocom_sprite_skill_attr")
        power_el = skill_box.select_one(".rocom_sprite_skill_power")

        skill_name = name_el.get_text(strip=True) if name_el else ""
        if not skill_name:
            # 尝试从img的alt提取
            img = skill_box.select_one("img")
            if img:
                skill_name = img.get("alt", "")

        level_text = lv_el.get_text(strip=True) if lv_el else "1"
        lv_m = re.search(r'(\d+)', level_text)
        level = int(lv_m.group(1)) if lv_m else 1

        attr_text = ""
        if attr_el:
            attr_text = attr_el.get_text(strip=True)

        type_text = type_el.get_text(strip=True) if type_el else ""

        power_text = power_el.get_text(strip=True) if power_el else ""

        skills.append({
            "level": level,
            "name": skill_name,
            "type_attr": type_text,
            "energy": "",
            "power": power_text,
            "category": attr_text,
            "effect": "",
        })

    # 备用：从被隐藏的skill_content找完整效果
    if skills:
        content_els = soup.select(".rocom_sprite_skillContent")
        for i, content_el in enumerate(content_els):
            if i < len(skills):
                skills[i]["effect"] = content_el.get_text(strip=True)

    data["skills"] = skills

    return data


# ======================== 3. 保存到SQLite ========================

def save_spirit_to_db(data: dict):
    """将精灵数据保存到 SQLite"""
    conn = get_connection()
    conn.execute("PRAGMA foreign_keys=OFF")
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO spirits
            (name, number, type1, type2, description, evolution_chain, image_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("name", ""),
            data.get("number", ""),
            data.get("type1", ""),
            data.get("type2", ""),
            data.get("description", ""),
            data.get("evolution_chain", ""),
            "",
        ))
        # 获取spirit_id
        cur = conn.execute("SELECT id FROM spirits WHERE name = ?", (data["name"],))
        row = cur.fetchone()
        if row is None:
            logger.warning(f"精灵 {data['name']} 插入后未找到ID，跳过技能保存")
            conn.close()
            return
        spirit_id = row["id"]

        # 保存技能
        skill_count = 0
        for sk in data.get("skills", []):
            if not sk.get("name"):
                continue
            # 【修复】用INSERT OR IGNORE避免UNIQUE冲突时自增ID递增
            # 1) 先查是否存在
            cur2 = conn.execute("SELECT id FROM skills WHERE name = ?", (sk["name"],))
            existing = cur2.fetchone()
            if existing:
                skill_id = existing["id"]
            else:
                # 2) 不存在才插入
                conn.execute("""
                    INSERT INTO skills
                    (name, skill_type, power, description, effect)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    sk.get("name", ""),
                    sk.get("type_attr", ""),
                    int(sk["power"]) if sk.get("power") and sk["power"].isdigit() else None,
                    sk.get("effect", ""),
                    sk.get("effect", ""),
                ))
                cur3 = conn.execute("SELECT id FROM skills WHERE name = ?", (sk["name"],))
                skill_row3 = cur3.fetchone()
                skill_id = skill_row3["id"] if skill_row3 else None

            if skill_id:
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO spirit_skills
                        (spirit_id, skill_id, learn_level, learn_method)
                        VALUES (?, ?, ?, ?)
                    """, (
                        spirit_id,
                        skill_id,
                        sk.get("level", 0),
                        "level_up",
                    ))
                    skill_count += 1
                except Exception as e:
                    logger.warning(f"  技能关联失败 {sk['name']}: {e}")
        logger.debug(f"  保存 {skill_count} 个技能")
    conn.close()


# ======================== 4. 爬取属性克制 ========================

def scrape_type_chart() -> list[dict]:
    """从属性表页面爬取属性克制数据"""
    logger.info("===== 爬取属性克制表 =====")
    # 尝试多个可能的URL
    urls = [
        fmt_url("/%E5%85%8B%E5%88%B6%E8%AE%A1%E7%AE%97%E5%99%A8"),
        fmt_url("/%E5%B1%9E%E6%80%A7%E5%85%8B%E5%88%B6"),
    ]
    html = ""
    for u in urls:
        try:
            html = fetch_html(u)
            if "克制" in html:
                break
        except:
            continue

    results = []
    if not html:
        # 使用硬编码的洛克王国世界属性克制表
        logger.info("使用内置属性克制表（无法从页面抓取）")
        return get_builtin_type_chart()

    soup = BeautifulSoup(html, "lxml")
    # 尝试解析克制表
    table = soup.select_one("table.wikitable, table.sortable")
    if table:
        rows = table.select("tr")
        headers = [th.get_text(strip=True) for th in rows[0].select("th, td")] if rows else []
        for row in rows[1:]:
            cells = row.select("td, th")
            if len(cells) >= 2:
                attacker = cells[0].get_text(strip=True)
                for i, cell in enumerate(cells[1:], 1):
                    if i <= len(headers):
                        defender = headers[i]
                        val = cell.get_text(strip=True)
                        mult = {"2": 2.0, "1": 1.0, "0.5": 0.5, "0": 0.0, "×2": 2.0, "×1": 1.0, "×0.5": 0.5, "×0": 0.0}.get(val)
                        if mult is not None:
                            results.append({"attacker": attacker, "defender": defender, "multiplier": mult})

    if not results:
        results = get_builtin_type_chart()
    return results


def get_builtin_type_chart() -> list[dict]:
    """内置洛克王国世界属性克制表"""
    # 18种属性
    types = ["普通","草","火","水","光","地","冰","龙","电","毒","虫","武","翼","萌","幽","恶","机械","幻"]
    # 简化的克制矩阵 (2=克制, 0.5=抵抗, 0=免疫, 1=正常)
    chart = {
        "普通": {"机械": 0.5, "幽": 0},
        "草": {"火": 0.5, "水": 2, "草": 0.5, "冰": 0.5, "毒": 0.5, "地": 2, "虫": 0.5, "龙": 0.5, "翼": 0.5},
        "火": {"草": 2, "火": 0.5, "水": 0.5, "冰": 2, "虫": 2, "龙": 0.5, "机械": 2},
        "水": {"火": 2, "水": 0.5, "草": 0.5, "地": 2, "龙": 0.5},
        "光": {"草": 0.5, "火": 2, "水": 0.5, "光": 0.5, "冰": 2, "虫": 2, "幽": 2, "恶": 2},
        "地": {"火": 2, "水": 0.5, "草": 0.5, "冰": 0.5, "电": 2, "毒": 2, "虫": 0.5, "翼": 0.5, "机械": 2},
        "冰": {"草": 2, "火": 0.5, "水": 0.5, "冰": 0.5, "地": 2, "龙": 2, "翼": 2, "机械": 0.5},
        "龙": {"火": 0.5, "水": 0.5, "草": 0.5, "冰": 0.5, "电": 0.5, "龙": 2, "机械": 0.5},
        "电": {"水": 2, "草": 0.5, "电": 0.5, "地": 0, "翼": 2, "龙": 0.5, "机械": 0.5},
        "毒": {"草": 2, "毒": 0.5, "地": 0.5, "虫": 0.5, "萌": 2, "机械": 0.5},
        "虫": {"草": 2, "火": 0.5, "毒": 0.5, "翼": 0.5, "光": 0.5, "幽": 0.5, "恶": 0.5, "机械": 0.5},
        "武": {"普通": 2, "冰": 2, "毒": 0.5, "翼": 0.5, "幽": 0.5, "恶": 2, "机械": 2, "幻": 0.5},
        "翼": {"草": 2, "电": 0.5, "冰": 0.5, "虫": 2, "武": 2, "机械": 0.5},
        "萌": {"武": 2, "毒": 0.5, "幽": 2, "恶": 2, "机械": 0.5, "幻": 0.5},
        "幽": {"幽": 2, "恶": 0.5, "幻": 2},
        "恶": {"光": 0.5, "武": 0.5, "幽": 2, "恶": 0.5, "幻": 0.5},
        "机械": {"冰": 2, "电": 0.5, "虫": 0.5, "翼": 0.5, "萌": 2, "幽": 0.5, "恶": 0.5, "机械": 0.5, "幻": 0.5},
        "幻": {"武": 2, "毒": 2, "虫": 2, "恶": 2, "机械": 2},
    }
    results = []
    for attacker in types:
        for defender in types:
            mult = 1.0
            if attacker in chart and defender in chart[attacker]:
                mult = chart[attacker][defender]
            results.append({"attacker": attacker, "defender": defender, "multiplier": mult})
    return results


def save_type_chart(entries: list[dict]):
    """保存属性克制表到数据库"""
    conn = get_connection()
    with conn:
        for e in entries:
            conn.execute("""
                INSERT OR REPLACE INTO type_effectiveness
                (attacker, defender, multiplier)
                VALUES (?, ?, ?)
            """, (e["attacker"], e["defender"], e["multiplier"]))
    conn.close()
    logger.info(f"属性克制表已保存 ({len(entries)} 条)")


# ======================== 5. 主流程 ========================

def main():
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>")
    logger.add(str(PROJECT_ROOT / "logs" / "scrape_{time:YYYY-MM-DD}.log"),
               level="DEBUG", rotation="1 day", retention="3 days", encoding="utf-8")

    logger.info("=" * 60)
    logger.info("洛克王国世界 BWIKI 数据爬虫")
    logger.info("=" * 60)

    # 初始化数据库
    init_db()

    # 第一步：爬取精灵列表
    spirits = scrape_spirit_list()
    logger.info(f"共找到 {len(spirits)} 个精灵")

    if not spirits:
        logger.error("未找到任何精灵！请检查页面结构或网络连接。")
        return

    # 第二步：逐精灵爬取详情
    success = 0
    for i, spirit in enumerate(spirits):
        logger.info(f"[{i+1}/{len(spirits)}] 处理: {spirit['name']}")

        # 构建URL
        name_encoded = requests.utils.quote(spirit["name"])
        url = spirit.get("url") or fmt_url(f"/{name_encoded}")

        try:
            detail = scrape_spirit_detail(spirit["name"], url)
            if detail:
                # 【重要】用列表页数据覆盖详情页的类型（列表页属性更准确）
                if spirit.get("types"):
                    detail["type1"] = spirit["types"][0] if len(spirit["types"]) > 0 else ""
                    detail["type2"] = spirit["types"][1] if len(spirit["types"]) > 1 else ""
                # 补充编号（如果详情页没提取到，用列表页的）
                if not detail.get("number") and spirit.get("number"):
                    detail["number"] = str(spirit["number"])
                save_spirit_to_db(detail)
                success += 1
                logger.info(f"  ✅ 保存成功")
            else:
                logger.warning(f"  ⚠️ 爬取为空")
        except Exception as e:
            logger.error(f"  ❌ 失败: {e}")

    logger.info(f"精灵数据爬取完成: {success}/{len(spirits)}")

    # 第三步：爬取属性克制表
    type_entries = scrape_type_chart()
    save_type_chart(type_entries)

    logger.info("=" * 60)
    logger.info(f"全部完成！成功导入 {success} 个精灵，{len(type_entries)} 条属性克制数据。")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
