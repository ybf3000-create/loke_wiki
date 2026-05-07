# src/voice/voice_module.py
# 语音交互模块框架（预留 MOSS-TTS-Nano 接口）

from loguru import logger
from config.settings import VOICE_ENABLED, VOICE_WAKE_WORD


class VoiceModule:
    """
    语音交互模块（骨架代码）
    
    使用说明：
    1. 安装依赖：pip install SpeechRecognition pyaudio
    2. 安装 MOSS-TTS-Nano：参照项目文档部署
    3. 将 VOICE_ENABLED 设为 True
    4. 实现以下三个核心方法
    
    流程：
    用户语音 → ASR (SpeechRecognition/Whisper) → 文字
    文字 → 知识库查询 → AI回复
    AI回复 → TTS (MOSS-TTS-Nano) → 语音朗读
    """

    def __init__(self, wake_word: str = VOICE_WAKE_WORD):
        self.wake_word = wake_word
        self.is_listening = False
        self.recognizer = None
        self.tts_engine = None

    def initialize(self) -> bool:
        """初始化语音识别和TTS引擎"""
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            logger.info("SpeechRecognition 已加载")
        except ImportError:
            logger.error("请先安装 SpeechRecognition: pip install SpeechRecognition pyaudio")
            return False
        # TODO: 初始化 MOSS-TTS-Nano
        # from moss_tts import TTS
        # self.tts_engine = TTS(...)
        logger.info("语音模块初始化完成（骨架模式，TTS未接入）")
        return True

    def listen(self, timeout: float = 3.0) -> str | None:
        """
        监听麦克风输入，返回识别文字
        - 检测唤醒词（如「小智」）后开始识别
        - timeout: 静默超时秒数
        """
        if not self.recognizer:
            logger.error("语音模块未初始化")
            return None
        # 实际实现
        # with sr.Microphone() as source:
        #     self.recognizer.adjust_for_ambient_noise(source)
        #     audio = self.recognizer.listen(source, timeout=timeout)
        #     text = self.recognizer.recognize_google(audio, language='zh-CN')
        #     if self.wake_word in text:
        #         return text.replace(self.wake_word, '').strip()
        #     return None
        logger.info(f"语音监听中（待实现 - 唤醒词: {self.wake_word}）")
        return None

    def speak(self, text: str):
        """TTS朗读回复"""
        if not self.tts_engine:
            logger.info(f"[TTS待实现] 朗读: {text[:50]}...")
            return
        # 实际实现
        # self.tts_engine.synthesize(text)
        # self.tts_engine.play()

    def start_continuous_listen(self, callback):
        """
        持续监听循环（后台线程）
        callback: 收到文字后的处理函数 callback(text: str)
        """
        import threading
        def _loop():
            while self.is_listening:
                text = self.listen()
                if text:
                    logger.info(f"语音识别结果: {text}")
                    try:
                        callback(text)
                    except Exception as e:
                        logger.error(f"语音回调出错: {e}")
        self.is_listening = True
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    def stop(self):
        self.is_listening = False
