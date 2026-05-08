# src/ui/tray_manager.py
# 系统托盘管理（右下角图标 + 右键菜单）

import os
import subprocess
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction, QPixmap
from PyQt6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QMessageBox,
)
from loguru import logger

from config.settings import AI_RULES_PATH, IMAGES_DIR, AI_LAST_MODEL_PATH
from config.settings import load_last_model, save_last_model, load_tts_engine, save_tts_engine, load_moss_provider, save_moss_provider


class TrayManager:
    def __init__(self, parent_window):
        self.parent = parent_window
        self.tray = None
        self._init_tray()

    def _init_tray(self):
        # 图标
        icon_path = self._find_icon()
        icon = QIcon(icon_path) if icon_path else QIcon()

        self.tray = QSystemTrayIcon(icon, self.parent)
        self.tray.setToolTip("洛克王国小智")

        # 右键菜单
        menu = QMenu()

        # --- 显示/隐藏 ---
        self.show_action = QAction("📱 显示/隐藏窗口")
        self.show_action.triggered.connect(self._toggle_window)
        menu.addAction(self.show_action)

        menu.addSeparator()

        # --- 编辑AI规则 ---
        edit_rules_action = QAction("📝 编辑AI规则")
        edit_rules_action.triggered.connect(self._edit_ai_rules)
        menu.addAction(edit_rules_action)

        # --- 切换AI模型 ---
        self.model_menu = menu.addMenu("🤖 切换AI模型")
        self._populate_model_menu()

        menu.addSeparator()

        # --- 语音开关 ---
        self.voice_input_action = QAction("🎤 语音输入")
        self.voice_input_action.setCheckable(True)
        self.voice_input_action.setChecked(False)
        self.voice_input_action.triggered.connect(self._toggle_voice_input)
        menu.addAction(self.voice_input_action)

        self.voice_output_action = QAction("🔊 语音朗读")
        self.voice_output_action.setCheckable(True)
        self.voice_output_action.setChecked(False)
        self.voice_output_action.triggered.connect(self._toggle_voice_output)
        menu.addAction(self.voice_output_action)

        # --- TTS引擎选择 ---
        self.tts_menu = menu.addMenu("🗣 TTS引擎")
        self._populate_tts_menu()

        menu.addSeparator()

        # --- 退出 ---
        exit_action = QAction("❌ 退出程序")
        exit_action.triggered.connect(self._quit_app)
        menu.addAction(exit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _find_icon(self) -> str:
        """寻找托盘图标（优先用水蓝蓝）"""
        candidates = [
            IMAGES_DIR / "水蓝蓝.png",
            IMAGES_DIR / "迪莫.png",
            IMAGES_DIR / "火花.png",
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        # 没找到图片，创建默认图标
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.green)
        pix_path = str(IMAGES_DIR / "_tray_icon.png")
        pix.save(pix_path)
        return pix_path

    def _populate_model_menu(self):
        """填充模型列表"""
        self.model_menu.clear()
        try:
            clients = getattr(self.parent, 'ollama_client', None)
            if clients and hasattr(clients, 'available_models'):
                current = clients.model
                for m in clients.available_models:
                    action = QAction(m)
                    action.setCheckable(True)
                    action.setChecked(m == current)
                    action.triggered.connect(lambda checked, name=m: self._switch_model(name))
                    self.model_menu.addAction(action)
        except Exception as e:
            logger.warning(f"模型列表加载失败: {e}")

    def _populate_tts_menu(self):
        """填充TTS引擎列表 + MOSS CPU/GPU选项"""
        self.tts_menu.clear()
        current = load_tts_engine()
        moss_provider = load_moss_provider()

        # 微软TTS
        ms_action = QAction("微软TTS (pyttsx3) - 默认")
        ms_action.setCheckable(True)
        ms_action.setChecked(current == "microsoft")
        ms_action.triggered.connect(lambda: self._switch_tts("microsoft"))
        self.tts_menu.addAction(ms_action)

        self.tts_menu.addSeparator()

        # MOSS-TTS-Nano + CPU/GPU子选项
        moss_action = QAction("MOSS-TTS-Nano")
        moss_action.setCheckable(True)
        moss_action.setChecked(current == "moss")
        moss_action.triggered.connect(lambda: self._switch_tts("moss"))
        self.tts_menu.addAction(moss_action)

        # MOSS 执行后端 (CPU/GPU)
        cpu_action = QAction("    ⚙ CPU模式 (onnxruntime)")
        cpu_action.setCheckable(True)
        cpu_action.setChecked(moss_provider == "cpu")
        cpu_action.triggered.connect(lambda: self._switch_moss_provider("cpu"))
        self.tts_menu.addAction(cpu_action)

        gpu_action = QAction("    ⚙ GPU模式 (CUDA, onnxruntime-gpu)")
        gpu_action.setCheckable(True)
        gpu_action.setChecked(moss_provider == "cuda")
        gpu_action.triggered.connect(lambda: self._switch_moss_provider("cuda"))
        self.tts_menu.addAction(gpu_action)

    def _switch_tts(self, engine_key: str):
        """切换TTS引擎"""
        save_tts_engine(engine_key)
        # 直接重建菜单刷新状态
        self._populate_tts_menu()
        # 通知语音模块
        if hasattr(self.parent, 'voice') and self.parent.voice:
            self.parent.voice.switch_tts(engine_key)
        logger.info(f"TTS引擎切换为: {engine_key}")

    def _switch_moss_provider(self, provider: str):
        """切换MOSS-TTS-Nano的执行后端 (CPU/GPU)"""
        save_moss_provider(provider)
        # 无声安装对应的onnxruntime
        import subprocess, sys
        from pathlib import Path
        pkg = "onnxruntime-gpu" if provider == "cuda" else "onnxruntime"
        python_exe = Path(sys.executable)
        try:
            __import__("onnxruntime" if provider != "cuda" else "", fromlist=["__version__"])
        except ImportError:
            subprocess.run(
                [str(python_exe), "-m", "pip", "install", pkg, "-q"],
                capture_output=True, timeout=120
            )
        self._populate_tts_menu()
        logger.info(f"MOSS后端切换为: {provider}")

    def _toggle_window(self):
        """显示/隐藏主窗口"""
        if self.parent.isVisible():
            self.parent.hide()
        else:
            self.parent.show()
            self.parent.raise_()
            self.parent.activateWindow()

    def _on_tray_activated(self, reason):
        """点击托盘图标显示窗口"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_window()

    def _edit_ai_rules(self):
        """用系统文本编辑器打开AI规则文件"""
        if not AI_RULES_PATH.exists():
            AI_RULES_PATH.write_text(
                "【小智AI行为规则 - 编辑此文件修改小智的行为】\n"
                "修改后保存，重启程序生效。\n\n"
                "1. 查询精灵时，名字必须完全匹配才能查到\n"
                "2. 查蛋时进化链上任意形态都回答基础形态的蛋\n"
                "3. 不知道就说不知道，不要瞎编\n",
                encoding="utf-8"
            )
        try:
            if os.name == 'nt':  # Windows
                os.startfile(str(AI_RULES_PATH))
            else:
                subprocess.run(['xdg-open', str(AI_RULES_PATH)], check=False)
        except Exception as e:
            logger.error(f"打开规则文件失败: {e}")
            QMessageBox.warning(self.parent, "提示", f"无法打开规则文件，请手动编辑:\n{AI_RULES_PATH}")

    def _switch_model(self, model_name: str):
        """切换AI模型"""
        try:
            clients = getattr(self.parent, 'ollama_client', None)
            if clients:
                clients.change_model(model_name)
                # 更新菜单勾选状态
                for action in self.model_menu.actions():
                    action.setChecked(action.text() == model_name)
                # 刷新顶部栏的模型选择
                if hasattr(self.parent, '_refresh_model_combo'):
                    self.parent._refresh_model_combo()
                logger.info(f"模型已切换为: {model_name}")
        except Exception as e:
            logger.error(f"模型切换失败: {e}")

    def _toggle_voice_input(self, checked):
        """切换语音输入"""
        if hasattr(self.parent, 'voice_input_btn'):
            self.parent.voice_input_btn.setChecked(checked)
        if hasattr(self.parent, '_on_voice_input_toggle'):
            self.parent._on_voice_input_toggle(checked)

    def _toggle_voice_output(self, checked):
        """切换语音朗读"""
        if hasattr(self.parent, 'voice_output_btn'):
            self.parent.voice_output_btn.setChecked(checked)
        if hasattr(self.parent, '_on_voice_output_toggle'):
            self.parent._on_voice_output_toggle(checked)

    def _quit_app(self):
        """退出程序"""
        reply = QMessageBox.question(
            self.parent, "退出", "确定退出洛克王国小智吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            QApplication.quit()

    def update_model_menu(self):
        """刷新模型菜单（外部调用）"""
        self._populate_model_menu()
