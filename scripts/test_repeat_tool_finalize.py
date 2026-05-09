# -*- coding: utf-8 -*-
"""最小回归测试：模拟重复同参 tool_call，验证不会中断而是强制收尾回答"""

from types import SimpleNamespace
from src.ollama_client.agent_loop import run_agent_loop


class FakeTC:
    def __init__(self, name, args):
        self.function = SimpleNamespace(name=name, arguments=args)


class FakeMsg:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeResp:
    def __init__(self, msg):
        self.message = msg


class FakeClient:
    """按调用次数返回预设响应：
    1) 请求 tool
    2) 再次请求同参 tool（触发重复）
    3) 强制收尾回答（不带 tools）
    """

    def __init__(self):
        self.n = 0

    def chat(self, model=None, messages=None, tools=None, options=None):
        self.n += 1
        if self.n == 1:
            return FakeResp(FakeMsg(tool_calls=[FakeTC("query_spirits_by_skill", {"skill_name": "虫鸣"})]))
        if self.n == 2:
            return FakeResp(FakeMsg(tool_calls=[FakeTC("query_spirits_by_skill", {"skill_name": "虫鸣"})]))
        return FakeResp(FakeMsg(content="已基于已有结果回答：虫鸣可由30只精灵学习。"))


class FakeOllama:
    def __init__(self):
        self.model = "fake"
        self._client = FakeClient()


if __name__ == "__main__":
    out = run_agent_loop("哪些精灵能学虫鸣", ollama_client=FakeOllama())
    print(out)
