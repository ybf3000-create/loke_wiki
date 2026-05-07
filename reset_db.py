import sys
sys.path.insert(0, 'G:/LuoKeHP/loke_wiki')
from src.core.database import get_connection, init_db
import sqlite3
from config.settings import DB_PATH

# 重建表并重置自增ID
conn = sqlite3.connect(str(DB_PATH))
conn.executescript('''
PRAGMA foreign_keys=OFF;
DROP TABLE IF EXISTS spirit_skills;
DROP TABLE IF EXISTS skills;
DROP TABLE IF EXISTS type_effectiveness;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS spirits;

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
);
CREATE TABLE IF NOT EXISTS skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    skill_type  TEXT,
    power       INTEGER,
    accuracy    INTEGER,
    pp          INTEGER,
    description TEXT,
    effect      TEXT
);
CREATE TABLE IF NOT EXISTS spirit_skills (
    spirit_id   INTEGER REFERENCES spirits(id),
    skill_id    INTEGER REFERENCES skills(id),
    learn_level INTEGER,
    learn_method TEXT,
    PRIMARY KEY (spirit_id, skill_id, learn_method)
);
CREATE TABLE IF NOT EXISTS type_effectiveness (
    attacker    TEXT NOT NULL,
    defender    TEXT NOT NULL,
    multiplier  REAL NOT NULL,
    PRIMARY KEY (attacker, defender)
);
DELETE FROM sqlite_sequence;
VACUUM;
PRAGMA foreign_keys=ON;
''')
conn.commit()
conn.close()
print('数据库重建完成，自增计数器已重置')
