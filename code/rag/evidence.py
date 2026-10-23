"""근거: 종류·병합·번호 붙이기·인용 추출. (F2006~F2008)"""
import re
from dataclasses import dataclass

KIND_GROUP = {"지점 정보": "항목", "오늘 개황": "항목", "유사 사례": "항목",
              "위키백과": "외부 문서", "NASA": "외부 문서", "NOAA": "외부 문서",
              "IPCC 용어집": "외부 문서", "기상청 용어·기준": "외부 문서"}
SOURCE_KIND = {"wiki": "위키백과", "nasa": "NASA", "noaa": "NOAA", "ipcc": "IPCC 용어집", "kma_terms": "기상청 용어·기준"}

# 답변 본문의 [근거 3], [근거 3, 5] 표기 (references/streamlit_lab/step7_skeleton.py와 같은 규칙)
CITE_PATTERN = re.compile(r"\[근거\s*([\d,\s]+)\]")


@dataclass
class Evidence:
    kind: str    # KIND_GROUP의 키
    doc_id: str
    title: str
    url: str
    text: str


def merge(*groups: list[Evidence]) -> list[Evidence]:
    """순서를 지키며 doc_id가 같은 근거는 처음 것만 남긴다."""
    seen, merged = set(), []
    for group in groups:
        for e in group:
            if e.doc_id not in seen:
                seen.add(e.doc_id)
                merged.append(e)
    return merged


def evidence_block(items: list[Evidence]) -> str:
    return "\n\n".join(f"[근거 {i}] ({e.kind}) {e.title}\n{e.text}" for i, e in enumerate(items, 1))


def cited(answer: str, items: list[Evidence]) -> list[tuple[int, Evidence]]:
    """답변이 실제로 인용한 근거만 (번호, 근거)로. 없는 번호는 무시한다."""
    numbers = {int(n) for group in CITE_PATTERN.findall(answer) for n in group.split(",") if n.strip().isdigit()}
    return [(i, e) for i, e in enumerate(items, 1) if i in numbers]
