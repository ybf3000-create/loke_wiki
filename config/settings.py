# config/settings.py
# 全局配置文件

import os
from pathlib import Path

# ======================== 路径配置 ========================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "db" / "loke_wiki.db"
CHROMA_DIR = DATA_DIR / "chroma"
IMAGES_DIR = DATA_DIR / "images"
IMPORT_DIR = DATA_DIR / "import"
LOGS_DIR = BASE_DIR / "logs"

# ======================== Ollama 配置 ========================
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "qwen2.5:7b-instruct-q4_K_M"   # 默认模型，可改为 qwen3:4b
OLLAMA_TIMEOUT = 120   # 秒

# 系统提示词（限制AI只查本地知识库）
SYSTEM_PROMPT = """你是洛克王国知识库查询助手「小智」。

【行为规则】
1. 收到用户查询后，仅基于本地知识库返回信息；
2. 仅返回知识库中存在的内容，找不到时固定回复"找不到相关信息，小智的知识库暂时没有收录这个哦~"；
3. 不进行额外推理、补充说明，不生成知识库之外的内容；
4. 如查询到精灵/道具信息，回复中用 [IMG:精灵名] 标记图片位置（前端会自动渲染）；
5. 不联网搜索，不修改原始数据。

【回复风格】
- 简洁、友好，适合游戏玩家阅读
- 使用中文，数据直接列出，不要废话
"""

# ======================== Chroma 嵌入模型 ========================
# 优先用本地模型，没有则用 Chroma 默认的 all-MiniLM-L6-v2
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"   # 支持中文

# ======================== UI 配置 ========================
APP_NAME = "洛克王国小智"
APP_VERSION = "1.0.0"
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 680
THEME_COLOR = "#07C160"      # 微信绿
BG_COLOR = "#EDEDED"
CHAT_BG = "#F5F5F5"
USER_BUBBLE = "#95EC69"
BOT_BUBBLE = "#FFFFFF"
FONT_FAMILY = "微软雅黑"

# ======================== 语音模块（可选）========================
VOICE_ENABLED = False           # 设为 True 启用语音
VOICE_WAKE_WORD = "小智"
VOICE_ASR_MODEL = "whisper"    # 预留，未来接入
