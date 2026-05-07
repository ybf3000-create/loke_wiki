# src/ollama_client/ollama_client.py
# Ollama API 调用封装（v0.6.x 兼容 Client 模式）

from loguru import logger
import ollama
from config.settings import OLLAMA_HOST, OLLAMA_MODEL, build_system_prompt, load_ai_rules, load_last_model, save_last_model


def test_connection() -> tuple[bool, str]:
    """测试 Ollama 连接状态"""
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        client.list()
        return True, "Ollama 已连接"
    except Exception as e:
        return False, f"Ollama 连接失败: {e}"


class OllamaClient:
    def __init__(
        self,
        model: str = None,
        host: str = OLLAMA_HOST,
        system_prompt: str = None,
    ):
        self.host = host
        # 读取上次选择的模型
        self.model = model or load_last_model()
        # 构建 System Prompt（内置规则 + 用户自定义规则）
        rules_text = load_ai_rules()
        self.system_prompt = system_prompt or build_system_prompt(rules_text)
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

    def update_system_prompt(self, new_prompt: str = None):
        """更新 System Prompt（例如加载新的用户规则后）"""
        if new_prompt:
            self.system_prompt = new_prompt
        else:
            self.system_prompt = build_system_prompt(load_ai_rules())
        logger.info("System Prompt 已更新")

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

    def send_reminder(self) -> bool:
        """发送系统提示词刷新（用于防失忆），只发送不返回回复"""
        try:
            self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": "【系统刷新】请记住以上规则继续执行，不需要回复。"},
                ],
                options={"num_ctx": 4096},
            )
            logger.info("系统规则刷新已发送（防失忆）")
            return True
        except Exception as e:
            logger.warning(f"防失忆发送失败: {e}")
            return False

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
        """切换模型并保存选择"""
        if model_name in self._available_models:
            self.model = model_name
            save_last_model(model_name)
            # 重建client连接
            self._client = ollama.Client(host=self.host)
            logger.info(f"模型切换为: {model_name}")
        else:
            raise ValueError(f"模型 {model_name} 不可用，可用: {self._available_models}")
