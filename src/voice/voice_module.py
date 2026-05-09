# src/voice/voice_module.py
# 语音交互模块（多TTS引擎支持）

import threading
import queue
import subprocess
import sys
import numpy as np
from pathlib import Path
from loguru import logger

from config.settings import VOICE_WAKE_WORD, load_tts_engine, load_moss_provider


class VoiceModule:
    """
    语音交互模块
    
    支持的TTS引擎:
    - microsoft: pyttsx3 (Windows离线, 默认)
    - moss: MOSS-TTS-Nano (需克隆仓库+下载模型)
    """

    def __init__(self, wake_word: str = VOICE_WAKE_WORD):
        self.wake_word = wake_word
        self.is_listening = False
        self.recognizer = None
        self._tts_engine = None  # pyttsx3实例
        self._tts_type = load_tts_engine()  # 当前TTS引擎类型
        self._audio_queue = queue.Queue()
        self._sample_rate = 16000
        self._input_device = None
        self.last_error = ""

    def initialize(self) -> bool:
        """初始化语音引擎"""
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.energy_threshold = 4000
            logger.info("SpeechRecognition 已加载")
        except ImportError:
            logger.error("请安装: pip install SpeechRecognition sounddevice")
            return False

        # 初始化当前TTS引擎
        self._init_tts()
        return True

    def _init_tts(self):
        """初始化TTS引擎（根据当前设置）"""
        if self._tts_type == "microsoft":
            self._init_microsoft_tts()
        elif self._tts_type == "moss":
            self._init_moss_tts()
        else:
            self._init_microsoft_tts()

    def _init_microsoft_tts(self):
        """初始化微软TTS (pyttsx3)"""
        try:
            import pyttsx3
            self._tts_engine = pyttsx3.init()
            # 找中文语音
            voices = self._tts_engine.getProperty('voices')
            for v in voices:
                if 'Chinese' in v.name or 'chinese' in v.id.lower():
                    self._tts_engine.setProperty('voice', v.id)
                    break
            self._tts_engine.setProperty('rate', 180)
            self._tts_engine.setProperty('volume', 0.9)
            logger.info("微软TTS (pyttsx3) 已加载")
        except ImportError:
            logger.error("请安装: pip install pyttsx3")
            self._tts_engine = None

    def _init_moss_tts(self):
        """初始化MOSS-TTS-Nano"""
        # 检查MOSS目录是否存在
        moss_dir = Path("MOSS-TTS-Nano")
        if not moss_dir.exists():
            logger.warning(
                "MOSS-TTS-Nano 未安装。请运行:\n"
                "  git clone https://github.com/OpenMOSS/MOSS-TTS-Nano.git\n"
                "  cd MOSS-TTS-Nano && pip install -r requirements.txt && pip install -e ."
            )
            self._tts_engine = None
            return
        logger.info("MOSS-TTS-Nano 已就绪")
        self._tts_engine = "moss"  # 标记为可用

    def switch_tts(self, engine_key: str):
        """运行时切换TTS引擎"""
        self._tts_type = engine_key
        self._init_tts()
        logger.info(f"TTS引擎已切换: {engine_key}")

    # ======================== 语音识别 ========================

    def _get_input_device(self):
        """获取可用麦克风设备索引；没有可用输入设备时返回 None"""
        try:
            import sounddevice as sd

            def _validate_device(device_index):
                if device_index is None or device_index < 0:
                    return None
                try:
                    device_info = sd.query_devices(device_index)
                    if device_info.get('max_input_channels', 0) <= 0:
                        return None

                    # 优先用设备默认采样率，避免固定 16000 在部分声卡上打开失败。
                    sample_rate = int(device_info.get('default_samplerate') or self._sample_rate or 16000)
                    sd.check_input_settings(
                        device=device_index,
                        channels=1,
                        samplerate=sample_rate,
                        dtype='float32',
                    )
                    return device_index, sample_rate, device_info.get('name', '')
                except Exception as e:
                    logger.debug(f"输入设备不可用: {device_index}, {e}")
                    return None

            default_device = sd.default.device
            default_input = default_device[0] if isinstance(default_device, (list, tuple)) else default_device
            validated = _validate_device(default_input)
            if validated:
                device_index, sample_rate, _ = validated
                self._sample_rate = sample_rate
                self.last_error = ""
                return device_index

            for idx, _device_info in enumerate(sd.query_devices()):
                validated = _validate_device(idx)
                if validated:
                    device_index, sample_rate, device_name = validated
                    self._sample_rate = sample_rate
                    self.last_error = ""
                    logger.warning(f"默认麦克风不可用，已改用输入设备: {device_index} {device_name}")
                    return device_index
        except Exception as e:
            self.last_error = f"⚠️ 麦克风检测失败: {e}"
            logger.error(self.last_error)
            return None

        self.last_error = "⚠️ 未找到可用麦克风，请检查系统输入设备；如果刚插入麦克风，请重启程序后再试"
        logger.error(self.last_error)
        return None

    def has_input_device(self) -> bool:
        """检查是否存在可用麦克风"""
        self._input_device = self._get_input_device()
        return self._input_device is not None

    def listen_once(self, timeout: float = 5.0) -> str | None:
        """
        录制一次语音并转为文字
        returns: 识别出的文字，失败返回 None
        """
        if not self.recognizer:
            logger.error("语音模块未初始化")
            return None

        try:
            import sounddevice as sd

            device = self._input_device
            if device is None:
                device = self._get_input_device()
                self._input_device = device
            if device is None:
                return None

            def callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"录音状态: {status}")
                self._audio_queue.put(indata.copy())

            self._audio_queue.queue.clear()
            recorded = []

            with sd.InputStream(
                samplerate=self._sample_rate,
                device=device,
                channels=1,
                dtype='float32',
                callback=callback
            ):
                import time
                start = time.time()
                while time.time() - start < timeout:
                    try:
                        data = self._audio_queue.get(timeout=0.1)
                        recorded.append(data)
                    except queue.Empty:
                        pass
                    # 静音自动结束
                    if recorded and len(recorded) > 5:
                        last = np.concatenate(recorded[-5:])
                        if np.max(np.abs(last)) < 0.02:
                            break

            if not recorded:
                return None

            audio_data = np.concatenate(recorded)
            audio_int16 = (audio_data * 32767).astype(np.int16)

            import speech_recognition as sr
            audio = sr.AudioData(audio_int16.tobytes(), self._sample_rate, 2)
            text = self.recognizer.recognize_google(audio, language='zh-CN')
            logger.info(f"语音识别: {text}")
            return text

        except Exception as e:
            self.last_error = f"⚠️ 语音识别失败: {e}"
            logger.error(self.last_error)
            if "Error querying device" in str(e):
                self._input_device = None
            return None

    def start_continuous_listen(self, callback) -> bool:
        """持续监听循环（后台线程）"""
        if self.is_listening:
            return True
        if not self.has_input_device():
            self.is_listening = False
            return False

        def _loop():
            failed_count = 0
            while self.is_listening:
                text = self.listen_once(timeout=3.0)
                if text:
                    failed_count = 0
                    logger.info(f"语音输入: {text}")
                    try:
                        callback(text)
                    except Exception as e:
                        logger.error(f"语音回调出错: {e}")
                elif self.last_error and ("麦克风" in self.last_error or "Error querying device" in self.last_error):
                    failed_count += 1
                    if failed_count >= 1:
                        logger.error("语音输入设备不可用，已停止持续监听")
                        self.stop()
                        break

        self.last_error = ""
        self.is_listening = True
        t = threading.Thread(target=_loop, daemon=True)
        t.start()
        return True

    def stop(self):
        """停止持续监听"""
        self.is_listening = False

    # ======================== 语音合成 ========================

    def speak(self, text: str):
        """朗读文字（根据当前TTS引擎选择不同后端）"""
        if not text:
            return
        if self._tts_type == "microsoft":
            self._speak_microsoft(text)
        elif self._tts_type == "moss":
            self._speak_moss(text)
        else:
            self._speak_microsoft(text)

    def _speak_microsoft(self, text: str):
        """微软TTS朗读"""
        if not self._tts_engine:
            logger.warning("微软TTS未初始化")
            return
        try:
            def _say():
                self._tts_engine.say(text)
                self._tts_engine.runAndWait()
            t = threading.Thread(target=_say, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"微软TTS失败: {e}")

    def _speak_moss(self, text: str):
        """MOSS-TTS-Nano朗读（支持CPU/GPU切换）"""
        try:
            moss_dir = Path("MOSS-TTS-Nano")
            if not moss_dir.exists():
                logger.warning("MOSS-TTS-Nano 目录不存在，请运行:\n"
                               "  git clone https://github.com/OpenMOSS/MOSS-TTS-Nano.git\n"
                               "  cd MOSS-TTS-Nano && pip install -r requirements.txt && pip install -e .")
                self._speak_microsoft(text)
                return

            prompt_wav = str(moss_dir / "assets" / "audio" / "zh_1.wav")
            if not Path(prompt_wav).exists():
                logger.warning("MOSS参考音频不存在")
                self._speak_microsoft(text)
                return

            # 读取执行后端配置（cpu / cuda）
            provider = load_moss_provider()
            exec_arg = [] if provider == "cpu" else ["--execution-provider", "cuda"]

            def _run_moss():
                try:
                    result = subprocess.run(
                        [sys.executable, "infer_onnx.py",
                         "--prompt-audio-path", prompt_wav,
                         "--text", text] + exec_arg,
                        cwd=str(moss_dir),
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode == 0:
                        from playsound import playsound
                        out_wav = moss_dir / "generated_audio" / "infer_output.wav"
                        if out_wav.exists():
                            playsound(str(out_wav))
                    else:
                        logger.error(f"MOSS失败: {result.stderr[:200]}")
                        self._speak_microsoft(text)
                except Exception as e:
                    logger.error(f"MOSS异常: {e}")
                    self._speak_microsoft(text)

            t = threading.Thread(target=_run_moss, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"MOSS朗读失败: {e}")
            self._speak_microsoft(text)

    def cleanup(self):
        """清理资源"""
        self.stop()
        if self._tts_engine and hasattr(self._tts_engine, 'stop'):
            try:
                self._tts_engine.stop()
            except Exception:
                pass
