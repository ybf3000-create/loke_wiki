# src/core/vector_store.py
# Chroma 向量知识库模块（非结构化语义检索）

import chromadb
from chromadb.utils import embedding_functions
from pathlib import Path
from loguru import logger
from config.settings import CHROMA_DIR, EMBEDDING_MODEL

_client = None
_collection = None


def _get_ef():
    try:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        logger.info(f"使用本地嵌入模型: {EMBEDDING_MODEL}")
        return ef
    except Exception as e:
        logger.warning(f"本地嵌入模型加载失败({e})，使用默认模型")
        return embedding_functions.DefaultEmbeddingFunction()


def get_collection(collection_name: str = "loke_wiki"):
    global _client, _collection
    if _collection is not None:
        return _collection
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = _get_ef()
    _collection = _client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )
    logger.info(f"向量集合 [{collection_name}] 已就绪，文档数: {_collection.count()}")
    return _collection


def add_documents(docs: list[dict]):
    """
    批量导入文档
    docs: [{"id": str, "text": str, "metadata": dict}, ...]
    """
    col = get_collection()
    ids = [d["id"] for d in docs]
    texts = [d["text"] for d in docs]
    metas = [d.get("metadata", {}) for d in docs]
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        col.upsert(
            ids=ids[i:i + batch_size],
            documents=texts[i:i + batch_size],
            metadatas=metas[i:i + batch_size]
        )
    logger.info(f"向量库新增/更新 {len(docs)} 条文档")


def search(query: str, n_results: int = 5, where: dict = None) -> list[dict]:
    """语义检索，返回 [{text, metadata, distance}, ...]"""
    col = get_collection()
    if col.count() == 0:
        return []
    kwargs = {"query_texts": [query], "n_results": min(n_results, col.count())}
    if where:
        kwargs["where"] = where
    result = col.query(**kwargs)
    hits = []
    for i, doc in enumerate(result["documents"][0]):
        hits.append({
            "text": doc,
            "metadata": result["metadatas"][0][i],
            "distance": result["distances"][0][i]
        })
    return hits


def delete_collection(collection_name: str = "loke_wiki"):
    global _client, _collection
    if _client:
        _client.delete_collection(collection_name)
        _collection = None
        logger.warning(f"向量集合 [{collection_name}] 已删除")
