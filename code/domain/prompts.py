"""프롬프트 3개(검색어 추출 / 후보 선별 / 답변 생성)와 단순 채팅 역할 문구, LLM 응답 파싱."""
import json
import re
from dataclasses import dataclass

SOURCES = ["wiki", "nasa", "noaa", "ipcc", "kma_terms"]
MAX_QUERIES = 2

PLAIN_SYSTEM = "너는 한국의 날씨와 기후를 잘 아는 기상 전문가다. 사용자의 질문에 한국어로 간결하게 답한다."

PLAN_SYSTEM = f"""너는 한국 기상청 예보관 출신의 기상 전문가다. 사용자의 질문에 답하려면 어떤 근거를 더 찾아야 하는지 정한다.

이미 주어지는 근거: 선택한 지점 정보(최근 10년 기준값, 오늘 관측)와 관할 지방청의 오늘 개황.
더 찾을 수 있는 근거:
- need_cases: 오늘 개황과 문장이 비슷했던 과거 날짜와 그날 이 지점의 실제 관측(유사 사례). 오늘·내일 날씨가 실제로 어떨지, 평소와 비교해 어떤지 묻는 질문이면 true.
- queries: 외부 문서 검색어. 출처마다 그 출처의 언어로 쓴다.
  - wiki(한국어 위키백과), kma_terms(기상청 특보 기준·예보용어): 한국어
  - nasa(NASA), noaa(NOAA Climate.gov), ipcc(IPCC 용어집): 영어
  기상 현상·용어·원리·기후변화처럼 설명이 필요한 개념만 찾는다. 오늘이나 이 지점의 날씨 그 자체는 외부 문서로 찾지 않는다.
  필요 없는 출처는 빈 목록으로 두고, 출처마다 검색어는 최대 {MAX_QUERIES}개.

설명 없이 JSON 한 개만 출력한다:
{{"need_cases": true 또는 false, "queries": {{"wiki": [], "nasa": [], "noaa": [], "ipcc": [], "kma_terms": []}}}}"""

SELECT_SYSTEM = {
    "cases": "너는 기상 전문가다. 아래 과거 사례는 오늘 개황과 문장이 비슷해서 뽑은 후보다. 오늘 개황과 비교해 "
             "현상(비·눈·기온 변화 등)과 시간대(아침·오후·밤)가 실제로 맞는 사례만 고른다.",
    "docs": "너는 기상 전문가다. 아래 문서는 검색 결과 후보다. 제목과 요약만 보고, 질문에 답하는 데 실제로 쓸 문서만 고른다.",
    "stations": "너는 기상 전문가다. 아래는 관측 지점 후보다. 사용자가 말한 조건에 맞는 지점만 고른다.",
}
SELECT_QUERY_LABEL = {"cases": "오늘 개황", "docs": "질문", "stations": "조건"}

ANSWER_SYSTEM = """너는 한국 기상청 예보관 출신의 기상 전문가다. 아래 [근거] 블록에 있는 내용만 사용해 한국어로 답한다.
- 근거에서 온 주장마다 끝에 [근거 N]을 붙인다. 여러 근거면 [근거 1, 3]처럼 쓴다.
- 근거에 없는 내용은 추측하지 않고 "근거 문서에서 확인되지 않습니다."라고 답한다.
- 숫자는 근거에 있는 값만 쓰고, 새로 계산하지 않는다.
- '평년값'이라는 말을 쓰지 않는다. 비교 기준은 '최근 10년 기준값'이라고 부른다.
- 유사 사례는 과거 참고 자료이지 예보가 아님을 분명히 한다."""


@dataclass
class Plan:
    need_cases: bool
    queries: dict[str, list[str]]


def _json_object(text: str):
    m = re.search(r"\{.*\}", text, re.S)  # 코드 펜스·앞뒤 설명을 걷어낸다
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def plan_messages(station: str, today: str, forecast_summary: str, question: str, history: list[dict]) -> list[dict]:
    """프롬프트1: 검색어 추출과 질문 종류 판단."""
    user = f"[지점] {station}\n[오늘] {today}\n[오늘 개황] {forecast_summary}\n[질문] {question}"
    return [{"role": "system", "content": PLAN_SYSTEM}, *history, {"role": "user", "content": user}]


def parse_plan(text: str) -> Plan | None:
    data = _json_object(text)
    if not isinstance(data, dict) or not isinstance(data.get("need_cases"), bool):
        return None
    raw = data.get("queries", {})
    if not isinstance(raw, dict):
        return None
    queries = {}
    for source in SOURCES:
        value = raw.get(source, [])
        if not isinstance(value, list) or not all(isinstance(q, str) for q in value):
            return None
        queries[source] = [q.strip() for q in value if q.strip()][:MAX_QUERIES]
    return Plan(data["need_cases"], queries)


def select_messages(purpose: str, items: list[tuple[int, str, str]], query: str) -> list[dict]:
    """프롬프트2: 후보 선별. 본문을 받기 전에 버릴 것을 정해 외부 호출을 줄인다."""
    listing = "\n".join(f"{n}. {title} — {summary}" for n, title, summary in items)
    user = (f"[{SELECT_QUERY_LABEL[purpose]}] {query}\n\n[후보]\n{listing}\n\n"
            '설명 없이 JSON 한 개만 출력한다: {"selected": [고른 번호들]}. 맞는 것이 없으면 빈 목록.')
    return [{"role": "system", "content": SELECT_SYSTEM[purpose]}, {"role": "user", "content": user}]


def parse_selected(text: str, valid: set[int]) -> list[int] | None:
    data = _json_object(text)
    if not isinstance(data, dict) or not isinstance(data.get("selected"), list):
        return None
    picked = []
    for n in data["selected"]:
        if isinstance(n, int) and n in valid and n not in picked:
            picked.append(n)
    return picked


def answer_messages(question: str, evidence_block: str, history: list[dict]) -> list[dict]:
    """프롬프트3: 근거 기반 답변 생성."""
    user = f"[근거]\n{evidence_block}\n\n[질문] {question}"
    return [{"role": "system", "content": ANSWER_SYSTEM}, *history, {"role": "user", "content": user}]


def ask_json(llm, messages: list[dict], parse):
    """LLM을 부르고 parse로 읽는다. 실패하면 JSON만 다시 달라고 한 번 더 묻고, 그래도 실패하면 None."""
    first = llm.invoke(messages).content
    result = parse(first)
    if result is not None:
        return result
    retry = messages + [{"role": "assistant", "content": first},
                        {"role": "user", "content": "위 답을 설명 없이 JSON 한 개로만 다시 출력해."}]
    return parse(llm.invoke(retry).content)
