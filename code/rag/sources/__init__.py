"""질문할 때 수집하는 외부 문서 출처. 모듈마다 search(query) → 후보, fetch(후보) → 본문."""
from dataclasses import dataclass


@dataclass
class Candidate:
    """본문을 받기 전의 검색 결과. 프롬프트2가 제목·요약만 보고 고른다."""
    source: str
    doc_id: str
    title: str
    summary: str
    url: str


@dataclass
class Doc:
    source: str
    doc_id: str
    title: str
    url: str
    text: str


from rag.sources import nasa, noaa, wiki  # noqa: E402  (Candidate·Doc 정의 뒤에 불러야 순환 import가 없다)

ADAPTERS = {"wiki": wiki, "nasa": nasa, "noaa": noaa}
