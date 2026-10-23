"""Chroma 컬렉션 생성·조회·저장."""
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

from config import CONFIG, ROOT, require_env


def get_store(collection: str, embeddings=None, persist_dir: str | None = None) -> Chroma:
    """기본은 GMS 임베딩과 config의 경로. 테스트는 가짜 임베딩과 임시 경로를 넘긴다."""
    if embeddings is None:
        embeddings = OpenAIEmbeddings(
            model=CONFIG["llm"]["embedding_model"],
            api_key=require_env("GMS_KEY"),
            base_url=CONFIG["llm"]["base_url"],
        )
    return Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=persist_dir or str(ROOT / CONFIG["chroma"]["persist_dir"]),
    )


def upsert_changed(store: Chroma, ids: list[str], texts: list[str], metadatas: list[dict]) -> int:
    """없거나 내용이 바뀐 ID만 임베딩해 넣고, 메타데이터만 바뀐 ID는 임베딩 없이 고친다. (F2002)

    반환값은 추가·갱신한 건수. 같은 ID는 덮어쓰기만 된다.
    """
    existing, offset = {}, 0
    while True:  # 한 번에 다 읽으면 SQLite 변수 개수 한도(too many SQL variables)에 걸려 나눠 읽는다
        page = store.get(include=["documents", "metadatas"], limit=5000, offset=offset)
        existing.update({i: (d, m) for i, d, m in zip(page["ids"], page["documents"], page["metadatas"])})
        if len(page["ids"]) < 5000:
            break
        offset += 5000
    meta_only = [i for i, doc_id in enumerate(ids)
                 if doc_id in existing and existing[doc_id][0] == texts[i] and existing[doc_id][1] != metadatas[i]]
    batch = CONFIG["chroma"]["embed_batch"]
    for start in range(0, len(meta_only), batch):
        chunk = meta_only[start:start + batch]
        store._collection.update(ids=[ids[i] for i in chunk], metadatas=[metadatas[i] for i in chunk])
    todo = [i for i, doc_id in enumerate(ids) if doc_id not in existing or existing[doc_id][0] != texts[i]]
    for start in range(0, len(todo), batch):
        chunk = todo[start:start + batch]
        store.add_texts(
            texts=[texts[i] for i in chunk], metadatas=[metadatas[i] for i in chunk], ids=[ids[i] for i in chunk]
        )
        print(f"  {store._collection.name}: {min(start + batch, len(todo))}/{len(todo)}건 임베딩", flush=True)
    return len(todo) + len(meta_only)
