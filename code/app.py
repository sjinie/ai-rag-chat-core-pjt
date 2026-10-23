"""날씨 RAG 챗봇 — 단순 채팅과 RAG 채팅을 나란히 비교한다.

    cd code
    streamlit run app.py

화면은 service만 부른다. 지점을 다른 곳(채팅·조건 탐색 카드)에서 바꿀 때는 references/streamlit_lab/plus_widget_key.py처럼
selectbox의 key("stn")를 콜백 안에서 고친다. 위젯을 그린 뒤 본문에서 고치면 오류가 나거나 선택이 한 번 무시된다.
"""
import streamlit as st

import service

NOTICE = "공식 특보·예보는 기상청 발표를 확인하세요."
CASE_NOTICE = "과거 유사 사례는 참고용이며 예보가 아닙니다."
NO_CITE = "ⓘ 답변에 인용된 근거가 없습니다."
ERROR = "답변을 만들지 못했습니다. 잠시 뒤 다시 시도해 주세요."

st.set_page_config(page_title="날씨 RAG 챗봇", page_icon="🌦️", layout="wide")

problems = service.check_ready()
if problems:
    st.error("실행 준비가 끝나지 않았습니다.\n\n" + "\n".join(f"- {p}" for p in problems))
    st.stop()


@st.cache_resource
def get_service() -> service.Service:
    return service.create()


try:
    svc = get_service()
except Exception:
    st.error("서비스를 시작하지 못했습니다. 키와 네트워크를 확인해 주세요.")  # 트레이스백은 보이지 않는다 (NF2004)
    st.stop()

STATIONS = svc.deps.stations
state = st.session_state
state.setdefault("stn", "108")
state.setdefault("histories", {})
for key in ("pending_rag", "pending_plain", "held_question", "report"):
    state.setdefault(key, None)
state.setdefault("candidates", [])
state.setdefault("explored", [])


def label(stn: str) -> str:
    info = STATIONS[stn]
    return f"{info['name']}({stn}) · {info['sido']}"


def history(stn: str) -> dict:
    return state.histories.setdefault(stn, {"plain": [], "rag": []})


def pick(stn: str) -> None:
    state.stn = stn
    state.candidates = []


def pick_candidate(stn: str) -> None:
    pick(stn)
    state.pending_rag, state.held_question = state.held_question, None


def keep_current() -> None:
    state.pending_rag, state.held_question, state.candidates = state.held_question, None, []


def on_rag_submit() -> None:
    """채팅에 다른 지점의 지명이 있으면 바꿀지 먼저 묻는다. '양산(우산)'처럼 잘못 잡힐 수 있어 조용히 바꾸지 않는다."""
    question = state.rag_in
    state.candidates, state.held_question = [], None  # 새 질문이 오면 묻던 선택은 버린다
    found = svc.resolve_location(question)
    if found and found != [state.stn]:
        state.candidates, state.held_question = found, question
        return
    state.pending_rag = question


def on_plain_submit() -> None:
    state.pending_plain = state.plain_in


def render_sources(msg: dict) -> None:
    if msg["cited"]:
        with st.expander(f"답변에 사용한 근거 {len(msg['cited'])}건"):
            for n, kind, title, url in msg["cited"]:
                st.markdown(f"**[근거 {n}]** {title} · {kind} · [원문]({url})")
    else:
        st.caption(NO_CITE)
    if msg["has_cases"]:
        st.caption(CASE_NOTICE)
    st.caption(NOTICE)


def answer_message(answer: service.Answer) -> dict:
    return {"role": "assistant", "content": answer.text, "has_cases": answer.has_cases,
            "cited": [(n, e.kind, e.title, e.url) for n, e in answer.cited]}


def plain_history(messages: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["content"]} for m in messages]


# ── 사이드바: 지점 선택(F2009), 색인 건수, 조건 탐색(F2011), 오늘 날씨 리포트(F2010) ──────────
with st.sidebar:
    st.header("지점 선택")
    st.selectbox("질문할 지점", list(STATIONS), key="stn", format_func=label)
    counts = service.collection_counts()
    st.caption(f"지점 {counts.get('station_meta', 0)}곳 · 예보 개황 {counts.get('forecast_texts', 0):,}건 · "
               f"외부 문서 청크 {counts.get('climate_docs', 0):,}건")
    if st.button("이 지점 대화 지우기", width="stretch"):
        state.histories[state.stn] = {"plain": [], "rag": []}

    st.divider()
    st.subheader("조건으로 지점 찾기")
    condition = st.text_input("조건", placeholder="예: 겨울에 아주 춥고 산이 많은 곳")
    if st.button("찾기", width="stretch") and condition:
        with st.spinner("조건에 맞는 지점을 고르는 중..."):
            try:
                state.explored = svc.explore(condition)
            except Exception:
                state.explored = []
                st.error(ERROR)
        if not state.explored:
            st.info("조건에 맞는 지점을 찾지 못했습니다.")
    for stn in state.explored:
        st.button(label(stn), key=f"explore_{stn}", on_click=pick, args=(stn,), width="stretch")

    st.divider()
    if st.button("오늘 날씨 리포트", type="primary", width="stretch"):
        with st.status("리포트를 만드는 중...") as status:
            try:
                rows, answer = svc.today_report(state.stn, on_step=status.write)
                state.report = {"stn": state.stn, "rows": rows, "message": answer_message(answer)}
                status.update(label="리포트 완료", state="complete")
            except Exception:
                status.update(label=ERROR, state="error")

# ── 본문 ─────────────────────────────────────────────────────────────────────────────
stn = state.stn
st.title("🌦️ 날씨 RAG 챗봇")
st.caption(f"선택한 지점: **{label(stn)}** — 오늘 예보를 과거 유사 사례와 최근 10년 기준값에 비추어 설명합니다.")

if state.report and state.report["stn"] == stn:
    with st.container(border=True):
        st.subheader(f"오늘 날씨 리포트 · {label(stn)}")
        st.dataframe(state.report["rows"], hide_index=True, width="stretch")
        st.markdown(state.report["message"]["content"])
        render_sources(state.report["message"])

left, right = st.columns(2)
chats = history(stn)

with left:
    st.subheader("단순 채팅")
    st.caption("근거 없이 LLM만으로 답합니다. 지점·날짜도 질문에 직접 써야 압니다.")
    box = st.container(height=560)
    for m in chats["plain"]:
        box.chat_message(m["role"]).markdown(m["content"])
    st.chat_input("단순 채팅에 질문하기", key="plain_in", on_submit=on_plain_submit)
    if state.pending_plain:
        question, state.pending_plain = state.pending_plain, None
        chats["plain"].append({"role": "user", "content": question})
        box.chat_message("user").markdown(question)
        with box.chat_message("assistant"), st.spinner("답하는 중..."):
            try:
                reply = svc.plain_chat(plain_history(chats["plain"]))
                st.markdown(reply)
                chats["plain"].append({"role": "assistant", "content": reply})
            except Exception:
                st.error(ERROR)

with right:
    st.subheader("RAG 채팅")
    st.caption("오늘 개황, 과거 유사 사례, 허용된 외부 문서를 근거로 답하고 인용한 근거를 보여 줍니다.")
    if state.candidates:
        st.info("질문에 다른 지점의 지명이 있습니다. 어느 지점으로 답할까요?")
        for c in state.candidates:
            st.button(label(c), key=f"cand_{c}", on_click=pick_candidate, args=(c,))
        st.button(f"지금 지점 그대로: {label(stn)}", key="keep_current", on_click=keep_current)
    box = st.container(height=560)
    for m in chats["rag"]:
        with box.chat_message(m["role"]):
            st.markdown(m["content"])
            if m["role"] == "assistant":
                render_sources(m)
    st.chat_input("RAG 채팅에 질문하기 (지명을 쓰면 그 지점으로 바뀝니다)", key="rag_in", on_submit=on_rag_submit)
    if state.pending_rag:
        question, state.pending_rag = state.pending_rag, None
        before = plain_history(chats["rag"])
        chats["rag"].append({"role": "user", "content": question})
        box.chat_message("user").markdown(question)
        with box.chat_message("assistant"):
            with st.status("근거를 찾는 중...") as status:
                try:
                    answer = svc.ask(stn, question, before, on_step=status.write)
                    status.update(label="근거 확인 완료", state="complete")
                except Exception:
                    answer = None
                    status.update(label=ERROR, state="error")
            if answer:
                message = answer_message(answer)
                st.markdown(message["content"])
                render_sources(message)
                chats["rag"].append(message)
