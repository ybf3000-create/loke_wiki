# scripts/test_ollama.py
# Ollama 连接与知识库查询测试

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import OLLAMA_MODEL
from src.ollama_client import OllamaClient, test_connection
from src.ollama_client.knowledge_agent import execute_knowledge_query, classify_intent


def test_connection_and_models():
    """测试 1: Ollama 连接与模型列表"""
    print("=" * 60)
    print("测试 1: Ollama 连接")
    ok, msg = test_connection()
    print(f"  {msg}")

    if ok:
        client = OllamaClient()
        print(f"\n可用模型 ({len(client.available_models)}):")
        for m in client.available_models:
            print(f"  - {m}")
        print(f"\n当前模型: {client.model}")
    return ok


def test_intent_parsing():
    """测试 2: 意图解析"""
    print("=" * 60)
    print("测试 2: 意图解析\n")
    tests = [
        "查询火神的蛋组",
        "水系精灵有哪些",
        "火系克制草系",
        "冰冻技能的效果",
        "搜索生命宝石",
    ]
    for text in tests:
        intent, args = classify_intent(text)
        print(f"  输入: {text}")
        print(f"  意图: {intent}, 参数: {args}\n")


def test_knowledge_query():
    """测试 3: 知识库查询（纯本地，不调AI）"""
    print("=" * 60)
    print("测试 3: 知识库查询（纯本地模式）\n")
    from src.core.database import init_db
    init_db()

    # 先查询 SQLite 测试（空库）
    result = execute_knowledge_query("火神")
    print(f"  > 查询「火神」")
    print(f"  类型: {result['type']}")
    print(f"  回复: {result['reply'][:200]}...\n")

    result = execute_knowledge_query("火系克制草系")
    print(f"  > 查询「火系克制草系」")
    print(f"  类型: {result['type']}")
    print(f"  回复: {result['reply']}\n")

    result = execute_knowledge_query("不存在的精灵")
    print(f"  > 查询「不存在的精灵」")
    print(f"  类型: {result['type']}")
    print(f"  回复: {result['reply']}\n")


def test_ollama_chat():
    """测试 4: Ollama AI 对话"""
    print("=" * 60)
    print("测试 4: Ollama AI 对话\n")
    try:
        client = OllamaClient()
        reply = client.chat("你好，请介绍一下你自己")
        print(f"  > 输入: 你好，请介绍一下你自己")
        print(f"  回复: {reply[:300]}...\n")
    except Exception as e:
        print(f"  ❌ Ollama 对话失败: {e}\n")


def show_menu():
    print("\n" + "=" * 60)
    print(" 洛克王国小智 - 测试脚本")
    print("=" * 60)
    print("  1. 测试 Ollama 连接")
    print("  2. 测试意图解析（不调用模型）")
    print("  3. 测试知识库查询（纯本地）")
    print("  4. 测试 Ollama AI 对话")
    print("  0. 全部测试")
    print("=" * 60)
    return input("请选择 [0-4]: ").strip()


def main():
    choice = show_menu()
    if choice == "1":
        test_connection_and_models()
    elif choice == "2":
        test_intent_parsing()
    elif choice == "3":
        test_knowledge_query()
    elif choice == "4":
        test_ollama_chat()
    elif choice == "0":
        test_connection_and_models()
        test_intent_parsing()
        test_knowledge_query()
        test_ollama_chat()
    else:
        print("无效选择")


if __name__ == "__main__":
    main()
