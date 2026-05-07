import sys, os, time, sqlite3
os.chdir('G:/LuoKeHP/loke_wiki')
sys.path.insert(0, 'G:/LuoKeHP/loke_wiki')
from config.settings import DB_PATH

# ===== 重置数据库（含自增计数器）=====
conn = sqlite3.connect(str(DB_PATH))
conn.executescript('''
PRAGMA foreign_keys=OFF;
DROP TABLE IF EXISTS spirit_skills;
DROP TABLE IF EXISTS skills;
DROP TABLE IF EXISTS type_effectiveness;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS spirits;
CREATE TABLE IF NOT EXISTS spirits (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,number TEXT,type1 TEXT,type2 TEXT,description TEXT,egg_group TEXT,evolution_chain TEXT,image_path TEXT,created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS skills (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,skill_type TEXT,power INTEGER,accuracy INTEGER,pp INTEGER,description TEXT,effect TEXT);
CREATE TABLE IF NOT EXISTS spirit_skills (spirit_id INTEGER REFERENCES spirits(id),skill_id INTEGER REFERENCES skills(id),learn_level INTEGER,learn_method TEXT,PRIMARY KEY (spirit_id,skill_id,learn_method));
CREATE TABLE IF NOT EXISTS type_effectiveness (attacker TEXT NOT NULL,defender TEXT NOT NULL,multiplier REAL NOT NULL,PRIMARY KEY (attacker,defender));
DELETE FROM sqlite_sequence;
VACUUM;
PRAGMA foreign_keys=ON;
''')
conn.commit()
conn.close()
print('数据库重置完成')

# ===== 全量爬取 =====
from src.core.database import get_connection
from scripts.scrape_bwiki import scrape_spirit_list, scrape_spirit_detail, save_spirit_to_db, scrape_type_chart, save_type_chart, fetch_html

spirits = scrape_spirit_list()
print(f'共 {len(spirits)} 个精灵')

t0 = time.time()
success = 0
for i, spirit in enumerate(spirits):
    if (i+1) % 50 == 0:
        elapsed = time.time() - t0
        rate = (i+1)/elapsed
        eta = (len(spirits)-(i+1))/rate
        print(f'  [{i+1}/{len(spirits)}] {rate:.1f}/s ETA:{eta:.0f}s')
    try:
        detail = scrape_spirit_detail(spirit['name'], spirit['url'])
        if detail and detail.get('hp'):
            if spirit.get('types'):
                detail['type1'] = spirit['types'][0] if len(spirit['types']) > 0 else ''
                detail['type2'] = spirit['types'][1] if len(spirit['types']) > 1 else ''
            if not detail.get('number') and spirit.get('number'):
                detail['number'] = str(spirit['number'])
            save_spirit_to_db(detail)
            success += 1
    except Exception as e:
        print(f'  [{i+1}] {spirit["name"]} FAIL: {e}')

elapsed = time.time() - t0
print(f'\n爬取完成: {success}/{len(spirits)} 耗时{elapsed:.0f}s')

# 统计
conn = get_connection()
c = conn.execute('SELECT COUNT(*) FROM spirits').fetchone()[0]
s = conn.execute('SELECT COUNT(*) FROM skills').fetchone()[0]
l = conn.execute('SELECT COUNT(*) FROM spirit_skills').fetchone()[0]
print(f'DB: {c}精灵 {s}技能 {l}关联')

# 属性克制
print('导入属性克制表...')
type_entries = scrape_type_chart()
save_type_chart(type_entries)
t2 = conn.execute('SELECT COUNT(*) FROM type_effectiveness').fetchone()[0]
print(f'属性克制: {t2}条')

# 验证
sp = conn.execute("SELECT id FROM spirits WHERE name='火神'").fetchone()
if sp:
    cnt = conn.execute("SELECT COUNT(*) FROM spirit_skills WHERE spirit_id=?", (sp['id'],)).fetchone()[0]
    print(f'火神技能数: {cnt}')
conn.close()
