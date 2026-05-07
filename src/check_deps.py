# src/check_deps.py
# 依赖检查 + 缺失自动安装

import importlib
import subprocess
import sys
from pathlib import Path

PYTHON_EXE = Path(sys.executable)  # 当前 Python 解释器


def check_and_install(package_name: str, import_name: str = None) -> bool:
    """
    检查包是否已安装，未安装则询问用户是否要安装
    package_name: pip 包名 (如 "sounddevice")
    import_name: import 时的名字 (如 "sounddevice")，省略则同 package_name
    returns: True=可用, False=用户拒绝或安装失败
    """
    name = import_name or package_name
    try:
        importlib.import_module(name)
        return True  # 已安装
    except ImportError:
        pass

    # 未安装 -> 弹窗询问
    from PyQt6.QtWidgets import QMessageBox
    reply = QMessageBox.question(
        None,
        "缺少依赖",
        f"缺少库「{package_name}」\n\n"
        f"是否自动安装到当前环境？\n"
        f"路径: {PYTHON_EXE.parent}\\Lib\\site-packages\\",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply != QMessageBox.StandardButton.Yes:
        return False

    # 执行 pip install
    try:
        result = subprocess.run(
            [str(PYTHON_EXE), "-m", "pip", "install", package_name, "-q"],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            QMessageBox.information(None, "安装成功", f"「{package_name}」安装成功！")
            return True
        else:
            QMessageBox.warning(
                None, "安装失败",
                f"「{package_name}」安装失败\n\n{result.stderr[:300]}"
            )
            return False
    except Exception as e:
        QMessageBox.warning(None, "安装出错", str(e))
        return False


# ====================== 可选依赖列表 ======================

OPTIONAL_DEPS = [
    # (pip包名, import名, 说明)
    ("sounddevice", "sounddevice", "麦克风录音"),
    ("SpeechRecognition", "speech_recognition", "语音识别(ASR)"),
    ("pyttsx3", "pyttsx3", "文字转语音(TTS)"),
    ("sentence-transformers", "sentence_transformers", "中文向量嵌入(Chroma)"),
]


def check_all_optional(show_summary: bool = True) -> dict:
    """
    检查所有可选依赖的状态
    returns: {package_name: True/False}
    """
    from PyQt6.QtWidgets import QMessageBox

    results = {}
    missing = []
    for pkg_name, import_name, desc in OPTIONAL_DEPS:
        ok = check_and_install(pkg_name, import_name)
        results[pkg_name] = ok
        if not ok:
            missing.append(f"  ❌ {pkg_name} ({desc})")

    if show_summary and missing:
        QMessageBox.information(
            None, "依赖状态",
            "以下功能不可用（可后续手动安装）：\n" + "\n".join(missing)
        )
    return results
