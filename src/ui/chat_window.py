# src/ui/chat_window.py
# 仿微信聊天风格主窗口（PyQt6）

import os
import sys
from pathlib import Path
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QFont, QPixmap, QTextCursor, QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QScrollArea, QFrame,
    QSizePolicy, QToolButton, QListWidget, QListWidgetItem,
    QMessageBox, QComboBox, QLineEdit, QSplitter, QSlider, QListView,
)
from loguru import logger

from config.settings import (
    APP_NAME, WINDOW_WIDTH, WINDOW_HEIGHT, THEME_COLOR,
    BG_COLOR, USER_BUBBLE, BOT_BUBBLE, CHAT_BG, FONT_FAMILY,
    IMAGES_DIR, VOICE_ENABLED, MSG_REMIND_INTERVAL,
    AI_RULES_DOC_PATH,
)
from src.ollama_client import OllamaClient, test_connection
from src.ollama_client.knowledge_agent import execute_knowledge_query
from src.ollama_client.agent_loop import run_agent_loop
from src.ui.tray_manager import TrayManager
from src.voice.voice_module import VoiceModule
from src.check_deps import check_and_install


def _get_font(size=10, bold=False):
    return QFont(FONT_FAMILY if FONT_FAMILY in QFont().families() else "Microsoft YaHei", size, QFont.Weight.Bold if bold else QFont.Weight.Normal)


class ChatInputEdit(QTextEdit):
    """支持 Enter 发送、Shift+Enter 换行的输入框"""

    send_requested = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.send_requested.emit()
            return
        super().keyPressEvent(event)


# ======================== 气泡组件 ========================

class BubbleFrame(QFrame):
    """聊天气泡容器"""
    def __init__(self, text: str, is_user: bool = True, images_dir: str = None):
        super().__init__()
        self._images_dir = images_dir or str(IMAGES_DIR)
        self._is_user = is_user
        self._text = text
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        # 解析 [IMG:xxx] 标记
        parts = self._parse_img_tags(self._text)
        has_content = False

        for part_type, content in parts:
            if part_type == "text" and content.strip():
                has_content = True
                label = QLabel(content.strip())
                label.setWordWrap(True)
                label.setFont(_get_font(10))
                label.setStyleSheet(f"color: {'#000000' if self._is_user or not self._is_user else '#000000'}; background: transparent;")
                layout.addWidget(label)
            elif part_type == "image":
                has_content = True
                img_path = Path(self._images_dir) / f"{content}.png"
                if not img_path.exists():
                    img_path = Path(self._images_dir) / f"{content}.jpg"
                # 蛋图片在 eggs/ 子目录
                if not img_path.exists():
                    img_path = Path(self._images_dir) / "eggs" / f"{content}.png"
                if not img_path.exists():
                    img_path = Path(self._images_dir) / "eggs" / f"{content}.jpg"
                if img_path.exists():
                    pix = QPixmap(str(img_path))
                    if not pix.isNull():
                        pix = pix.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        img_label = QLabel()
                        img_label.setPixmap(pix)
                        img_label.setAlignment(Qt.AlignmentFlag.AlignLeft if not self._is_user else Qt.AlignmentFlag.AlignRight)
                        layout.addWidget(img_label)
                else:
                    label = QLabel(f"[图片: {content}]")
                    label.setStyleSheet("color: gray; background: transparent;")
                    layout.addWidget(label)

        if not has_content:
            label = QLabel("[空回复]")
            label.setStyleSheet("color: gray; background: transparent;")
            layout.addWidget(label)

        # 气泡背景色
        bg = USER_BUBBLE if self._is_user else BOT_BUBBLE
        self.setStyleSheet(f"""
            BubbleFrame {{
                background-color: {bg};
                border-radius: 12px;
                border: 1px solid {USER_BUBBLE if not self._is_user else '#DDDDDD'};
            }}
        """)
        # 对齐
        align = Qt.AlignmentFlag.AlignRight if self._is_user else Qt.AlignmentFlag.AlignLeft
        self.setLayout(layout)

    def _parse_img_tags(self, text: str) -> list[tuple[str, str]]:
        """解析 [IMG:xxx] 标签，返回 [(type, content), ...]"""
        import re
        parts = []
        last_end = 0
        for m in re.finditer(r'\[IMG:([^\]]+)\]', text):
            if m.start() > last_end:
                parts.append(("text", text[last_end:m.start()]))
            parts.append(("image", m.group(1)))
            last_end = m.end()
        if last_end < len(text):
            parts.append(("text", text[last_end:]))
        if not parts:
            parts.append(("text", text))
        return parts


# ======================== 工作线程 ========================

class QueryWorker(QThread):
    """后台查询线程"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, text: str, use_ollama: bool = False, ollama_client: OllamaClient = None):
        super().__init__()
        self.text = text
        self.use_ollama = use_ollama
        self.ollama_client = ollama_client

    def run(self):
        try:
            # 1. 查知识库（无论是否用 Ollama，都先查）
            kq = execute_knowledge_query(self.text)
        except Exception as e:
            logger.exception(f"知识库查询失败: {e}")
            kq = {"type": "error", "reply": f"⚠️ 知识库查询出错: {e}"}

        # 2. 尝试用 Ollama 润色（可选）
        if self.use_ollama and self.ollama_client and kq.get("type") not in ("not_found", "error"):
            try:
                context = kq["reply"]
                prompt = (
                    f"用户问：{self.text}\n\n知识库查询结果：\n{context}\n\n"
                    f"请用自然语言回复用户，引用知识库数据即可，不要额外发挥。"
                )
                reply = self.ollama_client.chat(prompt)
                kq["reply"] = reply
            except Exception as e:
                logger.warning(f"Ollama 润色失败，回退到知识库原始结果: {e}")

        self.finished.emit(kq)


class AgentWorker(QThread):
    """AI Agent 全权代理工作线程"""
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, text: str, ollama_client: OllamaClient = None):
        super().__init__()
        self.text = text
        self.ollama_client = ollama_client

    def run(self):
        try:
            reply = run_agent_loop(self.text, self.ollama_client)
            self.finished.emit({"type": "agent", "reply": reply or "小智暂时无法回答这个问题~"})
        except Exception as e:
            logger.exception(f"Agent 查询失败: {e}")
            self.error.emit(str(e))


# ======================== 主窗口 ========================

class ChatWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ollama_client = OllamaClient()
        self._msg_count = 0          # 消息计数器（防失忆）
        self.tray = None             # 托盘，稍后初始化
        self.voice = None            # 语音模块，稍后初始化
        self._init_ui()
        self._init_ollama()
        self._init_voice()
        self.tray = TrayManager(self)  # 必须在UI初始化之后

    def _init_voice(self):
        """初始化语音模块（自动检测并安装缺失依赖）"""
        # 检查并安装三个语音依赖
        for pkg, imp in [
            ("sounddevice", None),
            ("SpeechRecognition", "speech_recognition"),
            ("pyttsx3", None),
        ]:
            check_and_install(pkg, imp or pkg)
        try:
            self.voice = VoiceModule()
            ok = self.voice.initialize()
            if ok:
                logger.info("语音模块就绪")
            else:
                logger.warning("语音模块初始化失败")
        except Exception as e:
            logger.warning(f"语音模块不可用: {e}")
            self.voice = None

    def closeEvent(self, event):
        """关闭窗口时最小化到托盘"""
        event.ignore()
        self.hide()
        if self.tray and self.tray.tray:
            self.tray.tray.showMessage("洛克王国小智", "程序已最小化到托盘", QIcon(), 2000)

    def _init_ui(self):
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setStyleSheet(f"QMainWindow {{ background-color: {BG_COLOR}; }}")

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ====== 顶部栏 ======
        self._build_topbar(main_layout)

        # ====== 聊天区域 ======
        self._build_chat_area(main_layout)

        # ====== 输入区域 ======
        self._build_input_area(main_layout)

        # 应用样式
        self.setStyleSheet(self._app_style())

    def _build_topbar(self, parent_layout):
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"""
            background-color: {THEME_COLOR};
            border-bottom: 1px solid #06AD56;
        """)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("洛克王国小智")
        title.setFont(_get_font(16, True))
        title.setStyleSheet("color: white; background: transparent;")

        # 模型选择
        self.model_combo = QComboBox()
        self.model_combo.setView(QListView())
        self.model_combo.view().setStyleSheet("""
            QListView {
                background-color: #FFFFFF;
                color: #111111;
                border: 1px solid #D5D5D5;
                outline: 0;
                selection-background-color: #07C160;
                selection-color: #FFFFFF;
            }
            QListView::item {
                min-height: 26px;
                padding: 4px 8px;
                color: #111111;
                background-color: #FFFFFF;
            }
            QListView::item:selected,
            QListView::item:hover {
                color: #FFFFFF;
                background-color: #07C160;
            }
        """)
        self.model_combo.setFont(_get_font(9))
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                color: #111111;
                border: 1px solid rgba(255,255,255,0.75);
                border-radius: 4px;
                padding: 4px 24px 4px 8px;
                min-width: 220px;
            }
            QComboBox:hover {
                border: 1px solid #FFFFFF;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border-left: 1px solid #D5D5D5;
                background-color: #F5F5F5;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0;
                height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                color: #111111;
                selection-background-color: #07C160;
                selection-color: #FFFFFF;
                border: 1px solid #D5D5D5;
                outline: 0;
            }
            QComboBox QAbstractItemView::item {
                color: #111111;
                background-color: #FFFFFF;
                min-height: 26px;
                padding: 4px 8px;
            }
            QComboBox QAbstractItemView::item:selected,
            QComboBox QAbstractItemView::item:hover {
                color: #FFFFFF;
                background-color: #07C160;
            }
        """)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)

        # 连接状态
        self.status_label = QLabel("连接中...")
        self.status_label.setFont(_get_font(9))
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.8); background: transparent;")

        bar_layout.addWidget(title)
        bar_layout.addStretch()
        bar_layout.addWidget(self.model_combo)
        bar_layout.addSpacing(12)
        bar_layout.addWidget(self.status_label)
        bar_layout.addSpacing(12)

        # 退出按钮
        exit_btn = QPushButton("❌")
        exit_btn.setFixedSize(32, 32)
        exit_btn.setFont(_get_font(14))
        exit_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.3);
            }
        """)
        exit_btn.setToolTip("退出程序")
        exit_btn.clicked.connect(self._exit_app)
        bar_layout.addWidget(exit_btn)

        parent_layout.addWidget(bar)

    def _build_chat_area(self, parent_layout):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"QScrollArea {{ background-color: {CHAT_BG}; border: none; }}")

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(16, 12, 16, 12)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()

        scroll.setWidget(self.chat_container)
        self.scroll = scroll
        parent_layout.addWidget(scroll, stretch=1)

    def _build_input_area(self, parent_layout):
        input_panel = QFrame()
        input_panel.setStyleSheet("""
            background-color: #F7F7F7;
            border-top: 1px solid #D5D5D5;
        """)
        input_layout = QVBoxLayout(input_panel)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        # 功能按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.toggle_ollama_btn = QPushButton("🔌 AI模式")
        self.toggle_ollama_btn.setCheckable(True)
        self.toggle_ollama_btn.setChecked(True)
        self.toggle_ollama_btn.setFont(_get_font(9))
        self.toggle_ollama_btn.setStyleSheet(self._btn_style("#07C160"))
        self.toggle_ollama_btn.clicked.connect(self._toggle_ollama_mode)

        self.clear_btn = QPushButton("🗑 清空")
        self.clear_btn.setFont(_get_font(9))
        self.clear_btn.setStyleSheet(self._btn_style("#888888"))
        self.clear_btn.clicked.connect(self._clear_chat)

        btn_row.addWidget(self.toggle_ollama_btn)

        # 语音输入按钮（始终显示，可开关）
        self.voice_input_btn = QPushButton("🎤 语音输入")
        self.voice_input_btn.setCheckable(True)
        self.voice_input_btn.setFont(_get_font(9))
        self.voice_input_btn.setStyleSheet(self._btn_style("#888888"))
        self.voice_input_btn.clicked.connect(self._on_voice_input_toggle)
        btn_row.addWidget(self.voice_input_btn)

        # 语音朗读按钮
        self.voice_output_btn = QPushButton("🔊 语音朗读")
        self.voice_output_btn.setCheckable(True)
        self.voice_output_btn.setFont(_get_font(9))
        self.voice_output_btn.setStyleSheet(self._btn_style("#888888"))
        self.voice_output_btn.clicked.connect(self._on_voice_output_toggle)
        btn_row.addWidget(self.voice_output_btn)

        # AI规则说明按钮
        self.rules_doc_btn = QPushButton("📖 AI规则")
        self.rules_doc_btn.setFont(_get_font(9))
        self.rules_doc_btn.setStyleSheet(self._btn_style("#888888"))
        self.rules_doc_btn.clicked.connect(self._open_ai_rules_doc)
        btn_row.addWidget(self.rules_doc_btn)

        btn_row.addStretch()
        btn_row.addWidget(self.clear_btn)

        input_layout.addLayout(btn_row)

        # 输入框 + 发送按钮行
        edit_row = QHBoxLayout()
        edit_row.setSpacing(8)

        self.input_edit = ChatInputEdit()
        self.input_edit.setPlaceholderText("输入问题，如：查询火神技能、水系精灵有哪些、火系克制草系...")
        self.input_edit.setFont(_get_font(10))
        self.input_edit.setFixedHeight(48)
        self.input_edit.setStyleSheet("""
            QTextEdit {
                background: white;
                color: #333333;
                border: 1px solid #D5D5D5;
                border-radius: 8px;
                padding: 8px;
                font-size: 14px;
            }
        """)
        self.input_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.input_edit.send_requested.connect(self._on_send_click)

        send_btn = QPushButton("发送")
        send_btn.setFont(_get_font(11, True))
        send_btn.setFixedSize(72, 48)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEME_COLOR};
                color: white;
                border-radius: 8px;
                border: none;
                font-size: 15px;
            }}
            QPushButton:hover {{ background-color: #06AD56; }}
            QPushButton:pressed {{ background-color: #05994A; }}
        """)
        send_btn.clicked.connect(self._on_send_click)

        edit_row.addWidget(self.input_edit)
        edit_row.addWidget(send_btn)

        input_layout.addLayout(edit_row)
        parent_layout.addWidget(input_panel)

    # ======================== 样式 ========================

    def _app_style(self):
        return f"""
            QMainWindow {{ background-color: {BG_COLOR}; }}
            QLabel {{ font-family: {FONT_FAMILY}; }}
            QPushButton {{ font-family: {FONT_FAMILY}; }}
            QTextEdit {{ font-family: {FONT_FAMILY}; }}
        """

    def _btn_style(self, color: str) -> str:
        return f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border-radius: 12px;
                padding: 6px 14px;
                border: none;
            }}
            QPushButton:hover {{ opacity: 0.8; }}
            QPushButton:checked {{
                background-color: #555555;
            }}
        """

    # ======================== 业务逻辑 ========================

    def _init_ollama(self):
        ok, msg = test_connection()
        if ok:
            self.status_label.setText("已连接")
            self.status_label.setStyleSheet("color: white; background: transparent;")
        else:
            self.status_label.setText("Ollama 未连接")
            self.status_label.setStyleSheet("color: #FF6B6B; background: transparent;")

        # 填充模型列表
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for m in self.ollama_client.available_models:
            self.model_combo.addItem(m)
        idx = self.model_combo.findText(self.ollama_client.model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _toggle_ollama_mode(self, checked):
        if checked:
            self.toggle_ollama_btn.setText("🔌 AI模式")
        else:
            self.toggle_ollama_btn.setText("🔍 纯知识库")
        self._add_system_message(f"{'AI模式已开启' if checked else '已切换到纯知识库查询模式'}")

    def _on_model_changed(self, model_name):
        if not model_name:
            return
        try:
            self.ollama_client.change_model(model_name)
            self._add_system_message(f"模型已切换为: {model_name}")
            # 同步托盘菜单
            if self.tray:
                self.tray.update_model_menu()
        except ValueError as e:
            QMessageBox.warning(self, "切换失败", str(e))

    def _refresh_model_combo(self):
        """刷新顶部栏模型选择（从托盘切换后调用）"""
        self.model_combo.blockSignals(True)
        idx = self.model_combo.findText(self.ollama_client.model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        self.model_combo.blockSignals(False)

    def _on_voice_input_toggle(self, checked):
        """切换语音输入"""
        if not self.voice:
            self._add_system_message("⚠️ 语音模块未初始化，请先安装依赖")
            self.voice_input_btn.setChecked(False)
            return
        if checked:
            started = self.voice.start_continuous_listen(self._on_voice_input)
            if not started:
                self.voice_input_btn.setStyleSheet(self._btn_style("#888888"))
                self.voice_input_btn.setText("🎤 语音输入")
                self.voice_input_btn.setChecked(False)
                self._add_system_message(self.voice.last_error or "⚠️ 未找到可用麦克风，请检查系统输入设备")
                return
            self.voice_input_btn.setStyleSheet(self._btn_style("#07C160"))
            self.voice_input_btn.setText("🎤 聆听中...")
            self._add_system_message("🎤 语音输入已开启，请说话...")
        else:
            self.voice_input_btn.setStyleSheet(self._btn_style("#888888"))
            self.voice_input_btn.setText("🎤 语音输入")
            if self.voice:
                self.voice.stop()
            self._add_system_message("🎤 语音输入已关闭")

    def _on_voice_input(self, text: str):
        """收到语音输入的文字"""
        if text:
            self._send(text)

    def _on_voice_output_toggle(self, checked):
        """切换语音朗读"""
        if not self.voice or not getattr(self.voice, '_tts_engine', None):
            self._add_system_message("⚠️ 语音朗读未安装，请先: pip install pyttsx3")
            self.voice_output_btn.setChecked(False)
            return
        if checked:
            self.voice_output_btn.setStyleSheet(self._btn_style("#07C160"))
            self.voice_output_btn.setText("🔊 朗读中")
            self._add_system_message("🔊 语音朗读已开启")
        else:
            self.voice_output_btn.setStyleSheet(self._btn_style("#888888"))
            self.voice_output_btn.setText("🔊 语音朗读")
            self._add_system_message("🔊 语音朗读已关闭")

    def _on_send_click(self):
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        self.input_edit.clear()

        # 消息计数器 + 防失忆
        self._msg_count += 1
        if self._msg_count >= MSG_REMIND_INTERVAL:
            self._msg_count = 0
            self._add_system_message("🔄 系统规则刷新中...")
            if self.toggle_ollama_btn.isChecked():
                self.ollama_client.send_reminder()

        self._send(text)

    def _send(self, text: str):
        self._add_bubble(text, is_user=True)
        self._add_thinking_bubble()
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

        if self.toggle_ollama_btn.isChecked():
            # AI 模式：使用 AgentWorker（AI 全权代理）
            worker = AgentWorker(
                text=text,
                ollama_client=self.ollama_client,
            )
        else:
            # 纯知识库模式：使用 QueryWorker（传统流程）
            worker = QueryWorker(
                text=text,
                use_ollama=False,
                ollama_client=self.ollama_client,
            )
        worker.finished.connect(self._on_query_result)
        worker.error.connect(self._on_query_error)
        self._current_worker = worker
        worker.start()

    def _on_query_result(self, result: dict):
        self._remove_thinking_bubble()
        reply = result.get("reply", "小智出错了~")
        self._add_bubble(reply, is_user=False)
        # 语音朗读回复
        if self.voice_output_btn.isChecked() and self.voice:
            # 去掉 [IMG:] 标签再朗读
            import re
            clean = re.sub(r'\[IMG:[^\]]+\]', '', reply)
            self.voice.speak(clean)

    def _on_query_error(self, err_msg: str):
        self._remove_thinking_bubble()
        self._add_bubble(f"⚠️ 查询出错: {err_msg}", is_user=False)
        if self.voice_output_btn.isChecked() and self.voice:
            self.voice.speak("查询出错了")

    def _clear_chat(self):
        reply = QMessageBox.question(self, "清空对话", "确定要清空所有聊天记录吗？")
        if reply == QMessageBox.StandardButton.Yes:
            while self.chat_layout.count() > 1:
                item = self.chat_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

    def _exit_app(self):
        """退出程序（带确认）"""
        if self.tray:
            self.tray._quit_app()
        else:
            QApplication.quit()

    def _open_ai_rules_doc(self):
        """用系统文本编辑器打开AI规则说明文档"""
        if not AI_RULES_DOC_PATH.exists():
            QMessageBox.warning(self, "提示", f"规则说明文档不存在: {AI_RULES_DOC_PATH}")
            return
        try:
            if os.name == 'nt':  # Windows
                os.startfile(str(AI_RULES_DOC_PATH))
            else:
                import subprocess
                subprocess.run(['xdg-open', str(AI_RULES_DOC_PATH)], check=False)
        except Exception as e:
            logger.error(f"打开规则说明文档失败: {e}")
            QMessageBox.warning(self, "提示", f"无法打开说明文档:\n{AI_RULES_DOC_PATH}")

    # ======================== 气泡管理 ========================

    def _add_bubble(self, text: str, is_user: bool = True):
        bubble = BubbleFrame(text, is_user=is_user)
        align = Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft
        label = QLabel("你" if is_user else "小智")
        label.setFont(_get_font(9, True))
        label.setStyleSheet(f"color: {'#07C160' if is_user else '#888888'}; padding: {'0 8px 0 0' if is_user else '0 0 0 8px'}; background: transparent;")

        hbox = QHBoxLayout()
        if is_user:
            hbox.addStretch()
        hbox.addWidget(bubble)
        if not is_user:
            hbox.addStretch()

        wrapper = QWidget()
        wrapper.setLayout(hbox)
        wrapper.setStyleSheet("background: transparent;")

        # 插入到stretch之前
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, wrapper)

        # 自动滚动到底部
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))

    def _add_system_message(self, text: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFont(_get_font(9))
        label.setStyleSheet("color: #999999; padding: 4px; background: transparent;")
        wrapper = QWidget()
        wrapper.setLayout(QVBoxLayout())
        wrapper.layout().addWidget(label)
        wrapper.layout().setContentsMargins(0, 2, 0, 2)
        wrapper.setStyleSheet("background: transparent;")
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, wrapper)

    def _add_thinking_bubble(self):
        label = QLabel("小智正在查询...")
        label.setFont(_get_font(10))
        label.setStyleSheet(f"color: #888888; background-color: {BOT_BUBBLE}; border-radius: 8px; padding: 10px 16px;")
        wrapper = QWidget()
        hbox = QHBoxLayout(wrapper)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.addWidget(label)
        hbox.addStretch()
        wrapper.setStyleSheet("background: transparent;")
        self._thinking_wrapper = wrapper
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, wrapper)

    def _remove_thinking_bubble(self):
        if hasattr(self, '_thinking_wrapper') and self._thinking_wrapper:
            self._thinking_wrapper.deleteLater()
            self._thinking_wrapper = None


# ======================== 入口 ========================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = ChatWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
