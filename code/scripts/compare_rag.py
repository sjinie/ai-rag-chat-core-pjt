"""RAG 사용 전후 비교 (F2015)와 응답 시간 (NF2001).

    cd code
    python -m scripts.compare_rag

대표 질문 5개를 단순 채팅(근거 없음)과 RAG 채팅에 각각 묻고 답·인용 근거·처리 시간을 적는다.
RAG는 두 번 물어 두 번째 처리 시간으로 검색어·선별 캐시 효과를 본다. 평가 칸은 사람이 채운다.
"""
import time

import service
from scripts.report import cell, write_section

QUESTIONS = [  # AGENTS.md에 확정된 대표 질문과 지점
    ("오늘 서울 기온이 최근 10년 평균보다 높아?", "108"),
    ("오늘 광주 예보와 비슷했던 날에는 실제로 비가 얼마나 왔어?", "156"),
    ("열대야 기준이 뭐야?", "108"),
    ("대관령은 왜 한겨울에 다른 곳보다 훨씬 추워?", "100"),
    ("온실효과가 한반도 여름 기온에 어떤 영향을 줘?", "108"),
]
MARKS = "①②③④⑤"


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def main() -> None:
    svc = service.create()
    out = [f"실행: {service.now():%Y-%m-%d %H:%M}. 오늘 개황과 오늘 관측을 쓰는 질문(①②)은 실행 날짜에 따라 답이 달라진다.", ""]
    for mark, (question, stn) in zip(MARKS, QUESTIONS):
        name = svc.deps.stations[stn]["name"]
        print(f"{mark} {question} ({name})")
        plain, t_plain = timed(lambda: svc.plain_chat([{"role": "user", "content": question}]))
        answer, t_first = timed(lambda: svc.ask(stn, question, []))
        _, t_second = timed(lambda: svc.ask(stn, question, []))
        sources = "<br>".join(f"[근거 {n}] {cell(e.title)} · {e.kind}" for n, e in answer.cited) or "인용 없음"
        out += [f"### {mark} {question} (지점: {name} {stn})", "",
                "| 구분 | 답변 | 인용 근거 | 처리 시간 |", "|---|---|---|---|",
                f"| 단순 채팅 | {cell(plain)} | 없음 | {t_plain:.1f}초 |",
                f"| RAG 채팅 | {cell(answer.text)} | {sources} | 1회 {t_first:.1f}초 / 2회 {t_second:.1f}초 |", ""]
    out += ["### 평가 (사람이 채운다)", "", "| 질문 | 사실 정확성 | 근거 제시 | 모르는 것을 모른다고 답함 |", "|---|---|---|---|"]
    out += [f"| {mark} | 단순: / RAG: | 단순: / RAG: | 단순: / RAG: |" for mark in MARKS]
    write_section("rag", "\n".join(out))


if __name__ == "__main__":
    main()
