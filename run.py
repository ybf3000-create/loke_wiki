# run.py
# 洛克王国AI知识库查询系统 - 主入口

import sys
import os
from pathlib import Path

# 确保项目根目录在 Python 路径中
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from config.settings import LOGS_DIR, APP_NAME

# 配置日志
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>")
logger.add(
    LOGS_DIR / "app_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    rotation="1 day",
    retention="7 days",
    encoding="utf-8",
)


def main():
    logger.info(f"启动 {APP_NAME}...")

    # 初始化数据库
    from src.core.database import init_db
    init_db()

    # 加载AI规则
    from config.settings import load_ai_rules
    rules = load_ai_rules()
    if rules:
        logger.info(f"已加载用户AI规则 ({len(rules)}字符)")
    else:
        logger.info("未找到用户自定义AI规则，使用默认规则")

    # 测试 Ollama 连接
    from src.ollama_client import test_connection
    ok, msg = test_connection()
    if ok:
        logger.info(f"✅ {msg}")
    else:
        logger.warning(f"⚠️ {msg} — 将使用纯知识库模式（不调AI）")

    # 启动 GUI
    from src.ui import ChatWindow
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("QToolTip { font-family: 微软雅黑; }")

    win = ChatWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
