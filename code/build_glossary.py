"""고정 문서(IPCC 용어집, 기상청 특보 기준·예보용어)를 climate_docs에 용어 단위로 미리 색인한다.

    cd code
    python build_glossary.py

문서가 하나로 고정돼 있어 질문할 때마다 받을 필요가 없다. 원문은 data/raw에 한 번 받아 둔다.
ID = common:{ipcc|kma_terms}:{slug}:{순번}. 2,000자를 넘는 정의만 [rag] chunk_size로 더 자른다.
"""
import re
from datetime import date

from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CONFIG, DATA_DIR
from rag import web
from rag.fixed_docs import read_glossary_runs, split_glossary_runs, split_kma_terms
from rag.store import get_store, upsert_changed

RAW = DATA_DIR / "raw"
IPCC_URL = "https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_AnnexVII.pdf"
KMA_PAGES = {"forecast03": ("기상특보 발표기준", "https://www.weather.go.kr/kma/biz/forecast03.jsp"),
             "forecast05": ("예보용어", "https://www.weather.go.kr/kma/biz/forecast05.jsp")}
LONG = 2000


def download(name: str, url: str):
    path = RAW / name
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        path.write_bytes(web.get(url).content)
    return path


def slug(term: str) -> str:
    return re.sub(r"[^\w]+", "-", term.lower()).strip("-")


def main() -> None:
    rag = CONFIG["rag"]
    splitter = RecursiveCharacterTextSplitter(chunk_size=rag["chunk_size"], chunk_overlap=rag["chunk_overlap"])
    ids, texts, metas = [], [], []

    def add(source: str, key: str, term: str, body: str, meta: dict) -> None:
        pieces = splitter.split_text(body) if len(body) > LONG else [body]
        for i, piece in enumerate(pieces):
            ids.append(f"common:{source}:{key}:{i}")
            texts.append(f"{term}: {piece}")
            metas.append({"source_type": source, "stn": "common", "doc_id": f"{source}-{key}", **meta})

    pdf = download("ipcc_ar6_wg1_glossary.pdf", IPCC_URL)
    collected = date.fromtimestamp(pdf.stat().st_mtime).isoformat()
    seen = {}
    for term, body, page in split_glossary_runs(read_glossary_runs(pdf)):
        key = slug(term)
        seen[key] = seen.get(key, 0) + 1
        key = key if seen[key] == 1 else f"{key}-{seen[key]}"  # 같은 이름의 용어가 또 나오면 구분
        add("ipcc", key, term, body, {"title": f"IPCC AR6 WG1 Glossary · {term}", "url": IPCC_URL,
                                      "page": page, "collected_at": collected})
    ipcc_count = len(set(m["doc_id"] for m in metas))

    for name, (label, url) in KMA_PAGES.items():
        html_path = download(f"kma_{name}.html", url)
        collected = date.fromtimestamp(html_path.stat().st_mtime).isoformat()
        for term, body in split_kma_terms(html_path.read_bytes().decode("utf-8")):
            add("kma_terms", f"{name}-{slug(term)}", term, body,
                {"title": f"기상청 {label} · {term}", "url": url, "collected_at": collected})
    assert len(ids) == len(set(ids)), "같은 ID가 두 번 나왔다"

    store = get_store("climate_docs")
    added = upsert_changed(store, ids, texts, metas)
    print(f"IPCC 용어 {ipcc_count}개, 기상청 용어 {len(set(m['doc_id'] for m in metas)) - ipcc_count}개 "
          f"→ 청크 {len(ids)}건 (이번에 추가·갱신 {added})")


if __name__ == "__main__":
    main()
