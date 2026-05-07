# src/ollama_client/ollama_client.py
# Ollama API 调用封装（v0.6.x 兼容 Client 模式）

from loguru import logger
import ollama
from config.settings import OLLAMA_HOST, OLLAMA_MODEL, SYSTEM_PROMPT


def test_connection() -> tuple[bool, str]:
    """测试 Ollama 连接状态"""
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        client.list()
        return True, f"Ollama 已连接，默认模型: {OLLAMA_MODEL}"
    except Exception as e:
        return False, f"Ollama 连接失败: {e}"


class OllamaClient:
    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        host: str = OLLAMA_HOST,
        system_prompt: str = None,
    ):
        self.model = model
        self.host = host
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self._client = ollama.Client(host=host)
        self._available_models = []
        self._refresh_models()

    def _refresh_models(self):
        try:
            resp = self._client.list()
            self._available_models = [m.model for m in resp.models]
            logger.info(f"可用模型: {self._available_models}")
        except Exception as e:
            logger.warning(f"获取模型列表失败: {e}")

    @property
    def available_models(self) -> list[str]:
        return self._available_models

    def chat(self, user_message: str, stream: bool = False) -> str | None:
        """发送消息给 Ollama，返回回复"""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]
        try:
            if stream:
                return self._chat_stream(messages)
            resp = self._client.chat(
                model=self.model,
                messages=messages,
                options={"num_ctx": 4096},
            )
            return resp.message.content
        except Exception as e:
            logger.error(f"Ollama 调用失败: {e}")
            raise

    def _chat_stream(self, messages: list) -> str:
        full = ""
        stream = self._client.chat(
            model=self.model,
            messages=messages,
            stream=True,
            options={"num_ctx": 4096},
        )
        for chunk in stream:
            if hasattr(chunk, "message") and hasattr(chunk.message, "content") and chunk.message.content:
                full += chunk.message.content
        return full

    def change_model(self, model_name: str):
        """切换模型"""
        if model_name in self._available_models:
            self.model = model_name
            logger.info(f"模型切换为: {model_name}")
        else:
            raise ValueError(f"模型 {model_name} 不可用，可用: {self._available_models}")
