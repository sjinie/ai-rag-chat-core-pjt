"""외부 문서 수집·색인(F2003~F2005, F2016)과 근거 검색(F2006, F2014).

질문 시 수집 출처(위키·NASA·NOAA): 검색어 → 후보 → 프롬프트2 선별 → 본문 → 청킹 → climate_docs 색인.
미리 색인된 고정 문서(IPCC·기상청 용어)는 검색만 한다.
"""
from datetime import date

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CONFIG
from domain.prompts import ask_json, parse_selected, select_messages
from rag.cache import mark_query, seen_query
from rag.sources import ADAPTERS
from rag.store import upsert_changed

LABELS = {"wiki": "위키백과", "nasa": "NASA", "noaa": "NOAA"}
MAX_CANDIDATES = 15


def collect(llm, store, cache_conn, stn: str, question: str, plan, on_step) -> list[str]:
    """프롬프트1이 낸 검색어로 새 문서를 수집·색인하고, 새로 색인한 문서 제목을 돌려준다.

    이미 수집한 (지점, 출처, 검색어)는 건너뛴다(NF2002). 출처 하나가 실패해도 나머지는 계속한다.
    """
    candidates, searched = [], []
    for source in ADAPTERS:
        for query in plan.queries.get(source, []):
            if seen_query(cache_conn, stn, source, query):
                continue
            try:
                found = ADAPTERS[source].search(query)
            except Exception:  # 네트워크·허용 목록·응답 형식 오류. 주소·키가 화면에 나가지 않게 종류도 감춘다
                on_step(f"{LABELS[source]} 출처에 연결하지 못해 건너뜀")
                break
            searched.append((source, query))
            candidates += [(c, query) for c in found if c.doc_id not in {x.doc_id for x, _ in candidates}]
    candidates = candidates[:MAX_CANDIDATES]
    if not candidates:
        for source, query in searched:
            mark_query(cache_conn, stn, source, query)
        return []

    items = [(i, f"[{LABELS[c.source]}] {c.title}", c.summary) for i, (c, _) in enumerate(candidates, 1)]
    picked = ask_json(llm, select_messages("docs", items, question),
                      lambda text: parse_selected(text, set(range(1, len(candidates) + 1))))
    if picked is None:
        return []  # 선별에 실패하면 검색어를 기록하지 않아 다음에 다시 시도한다

    splitter = RecursiveCharacterTextSplitter(chunk_size=CONFIG["rag"]["chunk_size"],
                                              chunk_overlap=CONFIG["rag"]["chunk_overlap"])
    ids, texts, metas, titles = [], [], [], []
    for n in picked:
        cand, query = candidates[n - 1]
        try:
            doc = ADAPTERS[cand.source].fetch(cand)
        except Exception:
            on_step(f"{LABELS[cand.source]} 문서를 받지 못해 건너뜀: {cand.title}")
            continue
        if not doc or not doc.text.strip():
            continue
        for i, chunk in enumerate(splitter.split_text(doc.text)):
            ids.append(f"{stn}:{doc.doc_id}:{i}")  # 지점을 앞에 붙여 여러 지점이 같은 문서를 모아도 덮어쓰지 않는다
            texts.append(chunk)
            metas.append({"source_type": doc.source, "stn": stn, "doc_id": doc.doc_id, "title": doc.title,
                          "url": doc.url, "query": query, "collected_at": date.today().isoformat()})
        titles.append(doc.title)
    if ids:
        upsert_changed(store, ids, texts, metas)
    for source, query in searched:
        mark_query(cache_conn, stn, source, query)
    return titles


def search_docs(store, stn: str, plan) -> list[Document]:
    """검색어가 있는 출처마다 그 출처 언어의 검색어로, 이 지점이 모은 문서와 공통 문서에서만 찾는다.

    출처·검색어별 결과를 순위대로 번갈아 합쳐 top_k개까지. search_type이 mmr이면 다양성을 고려한다(F2014).
    """
    rag = CONFIG["rag"]
    ranked = []
    for source, queries in plan.queries.items():
        for query in queries:
            where = {"$and": [{"source_type": source}, {"stn": {"$in": [stn, "common"]}}]}
            if rag["search_type"] == "mmr":
                ranked.append(store.max_marginal_relevance_search(query, k=rag["top_k"], fetch_k=rag["fetch_k"],
                                                                  filter=where))
            else:
                ranked.append(store.similarity_search(query, k=rag["top_k"], filter=where))
    merged, seen = [], set()
    for rank in range(rag["top_k"]):
        for docs in ranked:
            if rank < len(docs) and docs[rank].id not in seen and len(merged) < rag["top_k"]:
                seen.add(docs[rank].id)
                merged.append(docs[rank])
    return merged
