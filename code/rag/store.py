"""Chroma 컬렉션 생성·조회·저장."""
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from config import CONFIG, ROOT, require_env


def get_store(collection: str) -> Chroma:
    embeddings = OpenAIEmbeddings(
        model=CONFIG["llm"]["embedding_model"],
        api_key=require_env("GMS_KEY"),
        base_url=CONFIG["llm"]["base_url"],
    )
    return Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=str(ROOT / CONFIG["chroma"]["persist_dir"]),
    )


def upsert_missing(store: Chroma, ids: list[str], texts: list[str], metadatas: list[dict]) -> int:
    """아직 없는 ID만 임베딩해 넣는다. 같은 ID를 다시 넣어도 덮어쓰기만 된다. (F2002)"""
    existing = set(store.get(include=[])["ids"])
    todo = [i for i, doc_id in enumerate(ids) if doc_id not in existing]
    batch = CONFIG["chroma"]["embed_batch"]
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        store.add_texts(
            texts=[texts[i] for i in chunk], metadatas=[metadatas[i] for i in chunk], ids=[ids[i] for i in chunk]
        )
        print(f"  {store._collection.name}: {min(start + batch, len(todo))}/{len(todo)}건 임베딩", flush=True)
    return len(todo)
