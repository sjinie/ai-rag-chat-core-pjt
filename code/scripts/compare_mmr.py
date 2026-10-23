"""유사도 검색과 MMR 검색의 근거 차이 (F2014).

    cd code
    python -m scripts.compare_mmr

대표 질문 ⑤를 서울(108)로 묻는다고 보고, 같은 검색어로 두 방식의 외부 문서 근거 목록을 나란히 적는다.
재현할 수 있게 검색어는 고정한다(프롬프트1을 부르지 않음). 문서가 아직 없으면 먼저 수집한다(프롬프트2 사용).
"""
from unittest.mock import patch

import service
from config import CONFIG
from domain.prompts import Plan
from rag.collect import collect, search_docs
from scripts.report import cell, write_section

QUESTION = "온실효과가 한반도 여름 기온에 어떤 영향을 줘?"
STN = "108"
PLAN = Plan(False, {"wiki": ["온실효과", "폭염"], "nasa": ["greenhouse effect"], "noaa": ["greenhouse gases heat waves"],
                    "ipcc": ["greenhouse effect"], "kma_terms": []})


def listing(docs) -> list[str]:
    return [f"{d.metadata['title']} (청크 {d.id.rsplit(':', 1)[-1]})" for d in docs]


def main() -> None:
    svc = service.create()
    titles = collect(svc.deps.llm, svc.deps.climate_docs, svc.deps.cache, STN, QUESTION, PLAN, print)
    print("새로 수집:", titles)
    rag = CONFIG["rag"]
    single = Plan(False, {**{s: [] for s in PLAN.queries}, "wiki": ["온실효과"]})
    sections = [f"질문: {QUESTION} (지점 서울 108). 설정: top_k={rag['top_k']}, MMR fetch_k={rag['fetch_k']}"]
    for name, plan in (("검색어 하나(위키 '온실효과')", single), ("출처 4곳 검색어 5개 전체", PLAN)):
        results = {}
        for search_type in ("similarity", "mmr"):
            with patch.dict(CONFIG["rag"], {"search_type": search_type}):
                results[search_type] = listing(search_docs(svc.deps.climate_docs, STN, plan))
        rows = ["| 순위 | 유사도 검색 | MMR 검색 |", "|---|---|---|"]
        for i in range(max(len(v) for v in results.values())):
            pick = [cell(v[i]) if i < len(v) else "" for v in results.values()]
            rows.append(f"| {i + 1} | {pick[0]} | {pick[1]} |")
        same = len(set(results["similarity"]) & set(results["mmr"]))
        sections += ["", f"### {name}", "", *rows, "", f"두 방식에 공통으로 나온 근거: {same}/{rag['top_k']}건."]
    sections += ["", "검색어가 여러 개면 검색어마다 1순위부터 번갈아 담기 때문에(top_k 안에서 1순위끼리 채워짐) MMR과 유사도 검색의 결과가 같다. "
                 "MMR의 차이는 한 검색어 안에서 같은 문서의 이웃 청크가 몰리는 것을 막을 때 나타난다."]
    write_section("mmr", "\n".join(sections))


if __name__ == "__main__":
    main()
