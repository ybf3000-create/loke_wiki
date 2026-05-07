# src/voice/voice_module.py
# 语音交互模块（sounddevice + SpeechRecognition + pyttsx3）

import threading
import queue
import numpy as np
from pathlib import Path
from loguru import logger

from config.settings import VOICE_WAKE_WORD


class VoiceModule:
    """
    语音交互模块
    
    组件：
    - sounddevice: 麦克风录音（比pyaudio安装简单）
    - SpeechRecognition: 语音转文字(ASR)
    - pyttsx3: 文字转语音(TTS)，离线可用
    
    用法：
    vm = VoiceModule()
    vm.initialize()
    text = vm.listen_once()  # 录一次音转文字
    vm.speak("你好")  # 朗读
    """

    def __init__(self, wake_word: str = VOICE_WAKE_WORD):
        self.wake_word = wake_word
        self.is_listening = False
        self.recognizer = None
        self.tts_engine = None
        self._audio_queue = queue.Queue()
        self._sample_rate = 16000

    def initialize(self) -> bool:
        """初始化语音引擎"""
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            # 调整环境噪声适应
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.energy_threshold = 4000
            logger.info("SpeechRecognition 已加载")
        except ImportError:
            logger.error("请安装: pip install SpeechRecognition sounddevice")
            return False

        try:
            import pyttsx3
            self.tts_engine = pyttsx3.init()
            # 设置中文语音（Windows自带）
            voices = self.tts_engine.getProperty('voices')
            for v in voices:
                if 'Chinese' in v.name or 'chinese' in v.id:
                    self.tts_engine.setProperty('voice', v.id)
                    break
            self.tts_engine.setProperty('rate', 180)  # 语速
            self.tts_engine.setProperty('volume', 0.9)
            logger.info("pyttsx3 TTS 已加载")
        except ImportError:
            logger.warning("pyttsx3 未安装，TTS不可用: pip install pyttsx3")

        return True

    def listen_once(self, timeout: float = 5.0, phrase_limit: float = 10.0) -> str | None:
        """
        录制一次语音并转为文字
        returns: 识别出的文字，失败返回 None
        """
        if not self.recognizer:
            logger.error("语音模块未初始化")
            return None

        try:
            import sounddevice as sd

            def callback(indata, frames, time_info, status):
                if status:
                    logger.debug(f"录音状态: {status}")
                self._audio_queue.put(indata.copy())

            # 录音
            self._audio_queue.queue.clear()
            recorded = []

            with sd.InputStream(
                samplerate=self._sample_rate,
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
                    # 检测静音结束
                    if recorded and len(recorded) > 5:
                        last = np.concatenate(recorded[-5:])
                        if np.max(np.abs(last)) < 0.02:
                            break

            if not recorded:
                return None

            audio_data = np.concatenate(recorded)
            # 转16-bit PCM
            audio_int16 = (audio_data * 32767).astype(np.int16)

            # 用 SpeechRecognition 识别
            import speech_recognition as sr
            audio = sr.AudioData(audio_int16.tobytes(), self._sample_rate, 2)
            text = self.recognizer.recognize_google(audio, language='zh-CN')
            logger.info(f"语音识别: {text}")
            return text

        except Exception as e:
            logger.error(f"语音识别失败: {e}")
            return None

    def speak(self, text: str):
        """TTS朗读文字"""
        if not self.tts_engine:
            logger.info(f"[TTS未安装] 朗读: {text[:50]}...")
            return
        try:
            # 在子线程中执行避免阻塞UI
            def _say():
                self.tts_engine.say(text)
                self.tts_engine.runAndWait()
            t = threading.Thread(target=_say, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"TTS朗读失败: {e}")

    def start_continuous_listen(self, callback):
        """持续监听循环（后台线程）"""
        def _loop():
            while self.is_listening:
                text = self.listen_once(timeout=3.0)
                if text:
                    logger.info(f"语音输入: {text}")
                    try:
                        callback(text)
                    except Exception as e:
                        logger.error(f"语音回调出错: {e}")
        self.is_listening = True
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def stop(self):
        """停止持续监听"""
        self.is_listening = False

    def cleanup(self):
        """清理资源"""
        self.stop()
        if self.tts_engine:
            try:
                self.tts_engine.stop()
            except Exception:
                pass
