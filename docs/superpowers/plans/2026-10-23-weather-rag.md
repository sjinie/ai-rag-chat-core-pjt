# 날씨 RAG 챗봇 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 선택한 지점의 오늘 개황을 과거 유사 사례·최근 10년 기준값·허용 출처의 외부 문서에 비추어 근거와 함께 답하는 RAG 채팅과, 근거 없이 답하는 단순 채팅을 Streamlit에 나란히 띄운다.

**Architecture:** 수집·색인은 빌드 스크립트(`build_*.py`)가 미리 하고, 질문 시에는 LangGraph `retrieve → generate` 두 노드가 동작한다. retrieve 안에서 프롬프트1이 필요한 근거 종류와 출처별 검색어를 정하고, 유사 사례(개황 유사도 → SQLite 관측)와 외부 문서(질문 시 수집 + 미리 색인)를 모아 번호를 붙인다. 화면은 `service` 함수만 부르므로 나중에 FastAPI·Vue가 같은 함수를 쓴다.

**Tech Stack:** Python 3.12 · Streamlit 1.62.0 · LangGraph 1.2.10 · langchain-openai 1.4.3(GMS) · langchain-chroma 1.1.0 / ChromaDB 1.5.9 · langchain-text-splitters 1.1.2 · SQLite(표준 라이브러리) · requests 2.34.2 · pypdf

**Spec:** `docs/AI코어프로젝트_2회차_요구사항정의서.pdf`(원본), `docs/요구사항정의서.md`(요약), `AGENTS.md`(확정 설계), `GLOSSARY.md`(용어), `docs/adr/0001-유사사례-개황유사도.md`

## Global Constraints

- 라이브러리 버전은 `requirements.txt`의 고정 버전만 쓴다. 새 의존성은 `pypdf==5.4.0` 하나만 추가한다.
- LLM: `ChatOpenAI(model=CONFIG["llm"]["chat_model"], api_key=GMS_KEY, base_url="https://gms.ssafy.io/gmsapi/api.openai.com/v1/")`, 모델 `gpt-6-luna`(프롬프트 3개 + 단순 채팅 모두). 임베딩 `text-embedding-3-small`.
- 키는 `.env`(`GMS_KEY`, `KMA_API_KEY`, `WIKI_CONTACT`)로만 읽는다. 화면·로그·예외 메시지에 키, URL 쿼리, 프롬프트 전문, 트레이스백을 내지 않는다 (NF2003, NF2004).
- 웹 요청은 허용 호스트 5곳만: `ko.wikipedia.org`, `science.nasa.gov`, `www.climate.gov`, `www.ipcc.ch`, `www.weather.go.kr`. 리다이렉트도 같은 규칙. 기상청 API허브(`apihub.kma.go.kr`)는 기존 `domain/kma.py`만 호출한다.
- User-Agent: `WeatherRAG/0.1 ({WIKI_CONTACT}) python-requests` (영문 연락처, 없으면 괄호 생략). 같은 호스트 호출 사이 0.5초, 429·5xx·연결 오류는 `Retry-After` 또는 2초부터 두 배로 최대 4회.
- 청크·검색 값은 `code/config.toml`의 `[rag]`에 둔다: `chunk_size = 1000`, `chunk_overlap = 200`, `top_k = 4`, `fetch_k = 20`, `search_type = "similarity"`(또는 `"mmr"`), `case_candidates = 10`, `case_max = 5`.
- 용어는 `GLOSSARY.md`를 따른다. 화면·답변에 "평년값"을 쓰지 않고 "최근 10년 기준값"이라 쓴다.
- 고정 문구: 답변 아래 `공식 특보·예보는 기상청 발표를 확인하세요.` / 유사 사례 근거가 있으면 `과거 유사 사례는 참고용이며 예보가 아닙니다.` / 인용 0건이면 `ⓘ 답변에 인용된 근거가 없습니다.`
- 테스트는 표준 라이브러리 `unittest`로 `code/tests/`에 둔다. 실행: `cd code && ../.venv/Scripts/python.exe -m unittest discover -s tests -v`. LLM은 `tests/fakes.py`의 `FakeLLM`, 임베딩은 `langchain_core.embeddings.DeterministicFakeEmbedding(size=64)`로 대체하고, 네트워크 호출은 테스트에서 하지 않는다.
- 커밋 메시지는 한국어, 저장소 형식 `feat/…`, `fix/…`, `docs/…`.

## 시작 전

- 수집 단계 수정분(영하 기온 결측, 키 노출, 올해 캐시, 출처 필드, 메타데이터만 갱신, 관할 지방청 매핑, `GLOSSARY.md`, ADR 0001, AGENTS.md)이 아직 커밋되지 않았다. Task 1 전에 `fix/수집 단계 버그 수정과 설계 문서`로 커밋한다.
- 이미 끝난 것: F2001·F2002 (`build_climate.py`), 5년치 개황 색인 (`build_forecast.py`), SQLite `obs_daily`·`baseline`.

## Review Focus

1. **매칭되지 않거나 여러 곳에 맞는 위치 입력**("강남구", "고창"): 엉뚱한 지점으로 조용히 바뀌지 않고, 후보를 보여 주거나 현재 지점을 유지해야 한다. → Task 4 `test_match_ambiguous_and_none`
2. **새벽 00~05시 질문**: 오늘 개황이 없을 때 전날 17시 발표분을 쓰고 제목에 발표 시각을 표시해야 한다. → Task 5 `test_latest_forecast_before_5am_uses_previous_day`
3. **LLM이 JSON이 아닌 답을 낼 때**(프롬프트1·2): 한 번 재시도하고, 그래도 실패하면 유사 사례·외부 문서 없이 지점 정보와 오늘 개황만으로 답해야 한다. → Task 6 `test_parse_plan_falls_back`
4. **답변이 없는 번호를 인용**(`[근거 9]`)하거나 아무것도 인용하지 않을 때: 없는 번호는 무시하고, 인용 0건이면 안내 문구를 보여야 한다. → Task 9 `test_cited_ignores_unknown_numbers`
5. **허용 밖 호스트로의 리다이렉트·네트워크 실패**: 요청을 막고, URL·키 없는 메시지로 그 출처만 건너뛴 채 답변은 계속되어야 한다. → Task 1 `test_redirect_to_disallowed_host_blocked`, Task 8 `test_collect_skips_failed_source`

---

## File Structure

| 파일 | 책임 |
|---|---|
| `code/rag/web.py` (신규) | 허용 호스트만 부르는 HTTP GET, User-Agent·간격·재시도, 리다이렉트 검사 |
| `code/rag/html_text.py` (신규) | HTML → 본문 텍스트 (표준 `html.parser`) |
| `code/rag/sources/{wiki,nasa,noaa}.py` (신규) | 출처별 `search(query) -> list[Candidate]`, `fetch(candidate) -> Doc \| None` |
| `code/rag/fixed_docs.py` (신규) | IPCC 용어집 PDF·기상청 용어 페이지를 용어 단위로 자르기 |
| `code/build_glossary.py` (신규) | 고정 문서를 `climate_docs`에 `common:` ID로 미리 색인 |
| `code/domain/stations.py` (수정) | 지점 기후 성격 문장, 위치 문자열 → 지점 매칭, 편차 판정 |
| `code/domain/kma.py` (수정) | 오늘 최신 개황, 오늘 관측(일자료 부분값) |
| `code/domain/prompts.py` (신규) | 프롬프트 3개 + 단순 채팅 system 문구, JSON 파싱 |
| `code/domain/cases.py` (신규) | 유사 사례 후보 만들기·선별·캐시 |
| `code/rag/cache.py` (신규) | `data/cache.db`: 검색어 캐시, 유사 사례 선별 캐시 |
| `code/rag/collect.py` (신규) | 검색어 → 출처 검색 → 프롬프트2 → 본문 → 청킹·색인, 근거 검색(similarity/MMR) |
| `code/rag/evidence.py` (신규) | `Evidence`, 병합·중복 제거·번호, 근거 블록, 인용 추출 |
| `code/rag/graph.py` (신규) | LangGraph `retrieve`, `generate` |
| `code/rag/store.py` (수정) | `get_store`에 테스트용 임베딩·경로 주입 |
| `code/service.py` (신규) | `ask`, `plain_chat`, `today_report`, `explore` — 화면이 부르는 유일한 진입점 |
| `code/app.py` (신규) | Streamlit 화면 |
| `code/scripts/{backtest_cases,compare_mmr,compare_rag}.py` (신규) | 검증 스크립트 |
| `code/tests/` (신규) | `fakes.py` + 테스트 |
| `data/sources.md`, `docs/RAG_파이프라인_설계.md`, `docs/검증결과.md`, `README.md` (신규) | 제출 문서 |

---

### Task 1: 허용 출처 전용 웹 접근 + 출처·이용 조건 기록

**Files:**
- Create: `code/rag/web.py`, `code/rag/html_text.py`, `code/tests/__init__.py`, `code/tests/fakes.py`, `code/tests/test_web.py`, `data/sources.md`
- Modify: `code/config.toml` (`[web] allowed_hosts`, `[rag]` 값 — Global Constraints 참고), `requirements.txt` (`pypdf==5.4.0`)

**Interfaces:**
- Produces: `class BlockedHost(Exception)`; `get(url: str, params: dict | None = None, session=requests) -> requests.Response` (허용 호스트 아니면 `BlockedHost`, 실패하면 `RuntimeError("{host} 연결 실패: {예외 종류}")`); `html_to_text(html: str) -> str` (`script`·`style`·`nav`·`header`·`footer` 제외, 블록 요소마다 줄바꿈); `tests/fakes.py`: `FakeLLM(responses: list[str])` — `.invoke(messages)`가 응답을 차례로 `.content`에 담아 돌려주고 받은 메시지를 `.calls`에 쌓음, `FakeResponse(status_code, text, headers)`, `FakeSession(responses)`

- [ ] **Step 1: 실패하는 테스트 작성** — `test_web.py`
  - `test_disallowed_host_blocked`: `get("https://evil.example/x", session=FakeSession([]))`가 `BlockedHost`
  - `test_redirect_to_disallowed_host_blocked`: 첫 응답 `FakeResponse(302, "", {"Location": "https://evil.example/"})` → `BlockedHost`
  - `test_retry_after_429_then_ok`: 429 다음 200이면 본문을 돌려주고 세션 호출 2회 (`time.sleep`은 패치)
  - `test_error_message_has_no_query`: 세션이 `requests.ConnectionError("...?authKey=SECRET")`를 4번 내면 `RuntimeError` 메시지에 `SECRET`과 `?`가 없음
  - `test_html_to_text_drops_scripts`: `<nav>메뉴</nav><p>본문</p><script>x</script>` → `"본문"`
- [ ] **Step 2: 실행해 실패 확인** — `cd code && ../.venv/Scripts/python.exe -m unittest tests.test_web -v` → `ModuleNotFoundError: rag.web`
- [ ] **Step 3: `rag/web.py`, `rag/html_text.py` 구현** — `session.get(..., allow_redirects=False, timeout=30)` 후 3xx면 `Location`을 같은 검사로 최대 3번 따라간다. 호스트별 마지막 호출 시각을 모듈 dict에 두어 0.5초 간격을 지킨다.
- [ ] **Step 4: 테스트 통과 확인** — 같은 명령 → 5개 PASS
- [ ] **Step 5: `data/sources.md` 작성** — 출처마다 URL, 수집 방식, 이용 조건(라이선스·출처 표기 요구), 확인 날짜를 적는다. 대상: 기상청 API허브(ASOS 일자료·지점 정보·단기예보 개황), 한국어 위키백과(CC BY-SA 4.0), NASA science.nasa.gov, NOAA Climate.gov, IPCC AR6 WG1 Annex VII, 기상청 날씨누리 forecast03·forecast05. 각 사이트의 이용 약관·저작권 페이지를 직접 열어 확인한 내용만 적고, 확인하지 못한 항목은 "미확인"으로 남긴다 (NF2007).
- [ ] **Step 6: Commit** — `git add code/rag/web.py code/rag/html_text.py code/tests code/config.toml requirements.txt data/sources.md && git commit -m "feat/허용 출처 전용 웹 접근과 출처 기록"`

### Task 2: 질문 시 수집 출처 어댑터 (위키·NASA·NOAA)

**Files:**
- Create: `code/rag/sources/__init__.py`, `wiki.py`, `nasa.py`, `noaa.py`, `code/tests/test_sources.py`

**Interfaces:**
- Consumes: `web.get`, `html_to_text`
- Produces: `@dataclass Candidate(source: str, doc_id: str, title: str, summary: str, url: str)`; `@dataclass Doc(source: str, doc_id: str, title: str, url: str, text: str)` (둘 다 `rag/sources/__init__.py`); 각 모듈 `search(query: str, limit: int = 5) -> list[Candidate]`, `fetch(c: Candidate) -> Doc | None`; `__init__.py`에 `ADAPTERS = {"wiki": wiki, "nasa": nasa, "noaa": noaa}`
  - wiki: `references/streamlit_lab/step8_wiki_api.py`의 `search`·`fetch_page` 파라미터 그대로. `doc_id = "wiki-{pageid}"`, summary = snippet(태그 제거)
  - nasa: `GET https://science.nasa.gov/wp-json/wp/v2/search?search={q}&per_page={limit}` → title·url·`_links.self[0].href`. `doc_id = "nasa-{id}"`, summary = title. fetch는 self href의 `content.rendered`를 `html_to_text`
  - noaa: `www.climate.gov/sitemap.xml?page=1`, `?page=2`에서 경로가 `/news-features/climate-qa/` 또는 `/news-features/understanding-climate/`로 시작하는 URL만 모은 목록을 `data/raw/noaa_catalog.json`에 캐시. 제목 = 마지막 경로를 URL 디코딩해 `-`를 공백으로. search = 검색어 단어(소문자)와 제목 단어가 겹치는 개수로 정렬해 상위 `limit`(0개는 제외). `/search`는 robots.txt가 막으므로 쓰지 않는다. `doc_id = "noaa-" + 마지막 경로`
- [ ] **Step 1: 실패하는 테스트 작성** — `web.get`을 패치해 저장해 둔 응답 문자열로 검사
  - `test_wiki_search_strips_tags`: 응답 snippet `"<span class=\"searchmatch\">열대야</span> 현상"` → `summary == "열대야 현상"`, `doc_id == "wiki-123"`
  - `test_wiki_fetch_missing_returns_none`: `pages[0]`에 `"missing": true` → `None`
  - `test_nasa_search_maps_fields`: 앞서 확인한 실제 응답 모양(`id`, `title`, `url`, `_links.self[0].href`) → Candidate 필드
  - `test_noaa_catalog_filters_and_ranks`: 사이트맵 XML에 climate-qa 2건과 다른 경로 1건 → 목록 2건, `search("solar storms heat waves")` 1순위가 `do-solar-storms-cause-heat-waves-earth`
- [ ] **Step 2: 실행해 실패 확인** — `python -m unittest tests.test_sources -v` → ImportError
- [ ] **Step 3: 세 모듈 구현** (Interfaces 그대로)
- [ ] **Step 4: 테스트 통과 확인** — 4개 PASS. 이어서 실제 호출 1회씩 확인: `python -c "from rag.sources import ADAPTERS as A; [print(k, [c.title for c in m.search(q)][:3]) for k, m, q in [('wiki', A['wiki'], '열대야'), ('nasa', A['nasa'], 'greenhouse effect'), ('noaa', A['noaa'], 'heat wave')]]"` → 각 출처에서 제목 1개 이상
- [ ] **Step 5: Commit** — `feat/위키·NASA·NOAA 수집 어댑터`

### Task 3: 고정 문서 미리 색인 (IPCC 용어집, 기상청 특보 기준·예보용어)

**Files:**
- Create: `code/rag/fixed_docs.py`, `code/build_glossary.py`, `code/tests/test_fixed_docs.py`
- Modify: `code/rag/store.py` — `get_store(collection: str, embeddings=None, persist_dir: str | None = None) -> Chroma` (기본값은 지금과 같음)

**Interfaces:**
- Consumes: `web.get`, `html_to_text`, `get_store`, `upsert_changed`
- Produces: `split_glossary_pdf(pages: list[str]) -> list[tuple[str, str, int]]` (용어, 정의, 쪽); `split_kma_terms(text: str) -> list[tuple[str, str]]` (용어, 설명); `climate_docs` 문서 — ID `common:{source}:{slug}:0`, 메타데이터 `{"source_type": "ipcc" | "kma_terms", "stn": "common", "doc_id", "title", "url", "page"(ipcc만), "collected_at"}`
  - IPCC PDF: `https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_AnnexVII.pdf` → `data/raw/ipcc_ar6_wg1_glossary.pdf`
  - 기상청: `https://www.weather.go.kr/kma/biz/forecast03.jsp`(특보 기준), `https://www.weather.go.kr/kma/biz/forecast05.jsp`(예보용어)
- [ ] **Step 1: 원문 내려받아 살펴보기** — PDF와 두 페이지를 `data/raw/`에 받고, PDF 텍스트에서 용어가 시작되는 줄의 모양과 기상청 페이지의 용어 행 모양을 확인한다.
- [ ] **Step 2: 실패하는 테스트 작성** — Step 1에서 본 실제 발췌 문자열로
  - `test_glossary_terms_split`: 발췌에서 `Albedo`, `Carbon budget`, `Radiative forcing`이 각각 별도 항목이고 정의가 비어 있지 않으며 쪽 번호가 붙음
  - `test_kma_terms_split`: 발췌에서 `열대야`, `폭염`이 각각 별도 항목이고 설명에 기준 수치(예: `25℃`)가 들어 있음
- [ ] **Step 3: 실행해 실패 확인**
- [ ] **Step 4: `fixed_docs.py`, `build_glossary.py` 구현** — 용어 하나가 청크 하나. 2,000자를 넘는 정의만 `[rag] chunk_size/chunk_overlap`으로 더 자르고, 순번을 ID 끝에 붙인다.
- [ ] **Step 5: 테스트 통과 + 빌드 확인** — `python build_glossary.py` → 용어 수를 출력하고, 두 번째 실행에서 `추가·갱신 0`
- [ ] **Step 6: Commit** — `feat/IPCC 용어집·기상청 용어 고정 색인`

### Task 4: 지점 프로필 보강 + 위치 → 지점 매칭

**Files:**
- Modify: `code/domain/stations.py`, `code/build_climate.py` (보강 문장을 `station_text`에 넣고 다시 빌드)
- Create: `code/tests/test_stations.py`

**Interfaces:**
- Consumes: `fetch_stations()`의 지점 dict, `parse_daily` 행
- Produces: `climate_traits(rows: list[dict], info: dict) -> list[str]`; `station_text(stn, info, months, period, traits)` (인자 하나 추가); `match_stations(text: str, stations: dict) -> list[str]`
  - 성격 규칙(연평균 일수는 해당 지점 자료 연도 수로 나눔): 폭염일(`ta_max >= 33`) ≥10 → "폭염 잦음", 열대야(`ta_min >= 25`) ≥10 → "열대야 잦음", 한파일(`ta_min <= -12`) ≥10 → "한파 잦음", 연강수량 ≥1500mm → "다우지", ≤1000mm → "소우지", 해발 <100m "평지", 100~400m "구릉", ≥400m "고지대", 주소 `(산지)` → "산지", 지점명이 `도`로 끝나면 → "섬". 일수 숫자도 문장에 함께 쓴다(예: "폭염 연 12.3일").
  - 매칭 규칙: 입력에서 지점명(끝의 "시"·"군"을 뗀 형태 포함)이나 주소의 시·군·구 단어(`…시`, `…군`, `…구`)가 나오는 지점을 모두 돌려준다. 지점명 일치가 있으면 그것만. 없으면 빈 목록.
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_traits_hot_and_rainy`: 2년치 가짜 행에 폭염 30일·열대야 25일·연 1,600mm, 해발 50m → "폭염 잦음", "열대야 잦음", "다우지", "평지"가 들어 있고 "한파 잦음"은 없음
  - `test_traits_mountain_island`: `{"mountain": True, "height": 772.4, "name": "대관령"}` → "산지", "고지대"; `name="울릉도"` → "섬"
  - `test_match_by_name_and_district`: "강릉 날씨" → `["105"]` (북강릉 104는 주소 시 단어 "강릉시"로도 맞지만 지점명 일치가 우선); "정선 비 와?" → `["217"]`
  - `test_match_ambiguous_and_none`: "고창" → `["172", "251"]` 두 개; "강남구" → `[]`
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 테스트 통과 + 다시 빌드** — `python build_climate.py` → `station_meta 97건(추가·갱신 97)`. 이어서 `get_store("station_meta").similarity_search("겨울에 아주 춥고 산이 많은 곳", k=3)` 결과에 대관령(100) 또는 태백(216)이 들어 있어야 한다.
- [ ] **Step 5: Commit** — `feat/지점 기후 성격 보강과 위치 매칭`

### Task 5: 오늘 데이터 (최신 개황, 오늘 관측) + 편차 판정

**Files:**
- Modify: `code/domain/kma.py`, `code/domain/stations.py`
- Create: `code/tests/test_today.py`

**Interfaces:**
- Consumes: `request_kma`, `parse_forecasts`, `today_summary`, `parse_daily`, `get_baseline`
- Produces:
  - `fetch_latest_forecast(office: str, now: datetime) -> dict | None` — `{"office", "tmfc", "body", "summary"}`. 조회 구간은 `now`가 05시 이전이면 전날 `1700`~`1700`, 아니면 오늘 `0000`~`now`이며, 가장 늦은 발표분을 돌려준다.
  - `live_forecast_doc(f: dict, office_name: str) -> tuple[str, str, dict]` — Chroma `live_forecasts`에 넣을 (ID `live:{office}:{tmfc}`, 오늘 문단, 메타데이터 `{"source_type": "kma_forecast_live", "doc_id", "office", "tmfc", "title": "{지방청} 단기예보 개황 · YYYY-MM-DD HH시 발표", "url": FORECAST_SOURCE_URL, "body", "collected_at"}`) (F2004 "항목 자체 문서는 항상 색인")
  - `fetch_today_obs(stn: str, today: date) -> dict | None` — `kma_sfcdd.php?tm=YYYYMMDD&stn={stn}`를 `parse_daily`로. 오늘 값은 아직 결측이 많다.
  - `classify(value: float | None, mean: float | None, sd: float | None) -> str` — z = (value−mean)/sd. z ≤ −2 "매우 낮음", ≤ −1 "낮음", < 1 "비슷", < 2 "높음", 그 이상 "매우 높음". value·mean이 None이면 "자료 없음", sd가 0 또는 None이면 차이가 0일 때만 "비슷"이고 아니면 부호에 따라 "높음"/"낮음".
  - `anomaly_sentence(obs: dict, base: dict) -> str` — 6개 항목마다 "최고기온 3.1℃(최근 10년 기준값보다 4.2℃ 낮음, 매우 낮음)" 형식. 강수는 관측 0이면 "비 없음".
- [ ] **Step 1: 실패하는 테스트 작성** (`request_kma` 패치)
  - `test_latest_forecast_picks_latest_issue`: 오늘 05·11시 두 건 응답, `now=15:00` → `tmfc`가 `…1100`
  - `test_latest_forecast_before_5am_uses_previous_day`: `now=2026-10-24 03:00` → 요청 구간이 `202610231700`~`202610231700`, 결과 `tmfc == "202610231700"`
  - `test_classify_thresholds`: `classify(10, 14, 2) == "매우 낮음"`, `classify(13, 14, 2) == "비슷"`, `classify(18.5, 14, 2) == "매우 높음"`, `classify(None, 14, 2) == "자료 없음"`
  - `test_anomaly_sentence_rain_none`: 강수 0 → `"비 없음"` 포함, 최고기온 문장에 `"최근 10년 기준값보다"` 포함
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 테스트 통과 + 실호출 확인** — `python -c "from datetime import datetime; from domain.kma import fetch_latest_forecast; print(fetch_latest_forecast('156', datetime.now())['tmfc'])"` → 오늘 발표 시각
- [ ] **Step 5: Commit** — `feat/오늘 개황·관측과 기준값 편차 판정`

### Task 6: 프롬프트 3개 + 응답 파싱

**Files:**
- Create: `code/domain/prompts.py`, `code/tests/test_prompts.py`

**Interfaces:**
- Produces:
  - `PLAIN_SYSTEM: str` — 단순 채팅용 기상 전문가 역할 문구 (지점·날짜 정보 없음)
  - `@dataclass Plan(need_cases: bool, queries: dict[str, list[str]])` — 키는 `wiki`, `nasa`, `noaa`, `ipcc`, `kma_terms` 5개 고정(빈 목록 허용), 출처별 최대 2개
  - `plan_messages(station: str, today: str, forecast_summary: str, question: str, history: list[dict]) -> list[dict]` — 프롬프트1. 역할 "기상 전문가". JSON만 출력하도록 지시하고, **출처별 언어**(wiki·kma_terms 한국어, nasa·noaa·ipcc 영어)와 "오늘·이 지점 날씨 그 자체는 외부 문서로 찾지 않는다"를 명시
  - `parse_plan(text: str) -> Plan | None` — 코드 펜스 허용, 모르는 키 무시, 형식이 틀리면 `None`
  - `select_messages(purpose: str, items: list[tuple[int, str, str]], query: str) -> list[dict]` — 프롬프트2. `items`는 (번호, 제목, 요약). `purpose`는 `"cases"`(오늘 개황 `query`와 시간대·현상이 맞는 사례), `"docs"`(질문 `query`에 답하는 데 쓸 문서), `"stations"`(조건 `query`에 맞는 지점) 중 하나. 출력 `{"selected": [번호]}`
  - `parse_selected(text: str, valid: set[int]) -> list[int] | None`
  - `answer_messages(question: str, evidence_block: str, history: list[dict]) -> list[dict]` — 프롬프트3. 근거 블록만 사용, 주장마다 `[근거 N]`, 근거가 없으면 `근거 문서에서 확인되지 않습니다.`, 숫자는 근거에 있는 값만 쓰고 직접 계산하지 않음, "평년값" 대신 "최근 10년 기준값"
  - `ask_json(llm, messages, parse) -> object | None` — 호출 후 파싱, 실패하면 "JSON만 다시 출력" 메시지를 덧붙여 한 번 더, 그래도 실패하면 `None`
- [ ] **Step 1: 실패하는 테스트 작성**
  - `test_parse_plan_valid`: ```` ```json {"need_cases": true, "queries": {"wiki": ["열대야"], "nasa": []}} ``` ```` → `Plan(True, {"wiki": ["열대야"], "nasa": [], "noaa": [], "ipcc": [], "kma_terms": []})`
  - `test_parse_plan_caps_two_queries`: wiki에 검색어 3개 → 앞 2개만
  - `test_parse_plan_falls_back`: `FakeLLM(["모르겠어요", "여전히 아님"])`으로 `ask_json(..., parse_plan)` → `None`이고 호출 2번
  - `test_parse_selected_filters_invalid`: `'{"selected": [1, 7, "x"]}'`, valid `{1, 2}` → `[1]`
  - `test_plan_prompt_mentions_languages`: `plan_messages(...)`의 system 내용에 `"영어"`와 `"한국어"`가 모두 들어 있음
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 테스트 통과 확인**
- [ ] **Step 5: Commit** — `feat/프롬프트 3개와 JSON 파싱`

### Task 7: 유사 사례 (후보 → 관측·편차 → 선별 → 캐시)

**Files:**
- Create: `code/rag/cache.py`, `code/domain/cases.py`, `code/tests/test_cases.py`

**Interfaces:**
- Consumes: `forecast_texts` 스토어, `get_obs`, `get_baseline`, `anomaly_sentence`, `select_messages`, `parse_selected`, `ask_json`
- Produces:
  - `rag/cache.py`: `connect_cache(path=DATA_DIR / "cache.db") -> sqlite3.Connection`; `get_selection(conn, stn, tmfc) -> list[str] | None`; `put_selection(conn, stn, tmfc, doc_ids)`; `seen_query(conn, stn, source, query) -> bool`; `mark_query(conn, stn, source, query)`
  - `@dataclass Case(doc_id: str, date: str, title: str, url: str, forecast: str, obs: dict, sentence: str)` — `sentence` = 오늘 문단 + `anomaly_sentence`
  - `case_candidates(store, conn_db, stn: str, office: str, summary: str, n: int, exclude_dates: frozenset[str] = frozenset()) -> list[Case]` — `similarity_search(summary, k=n*3, filter={"office": office})`를 유사도 순으로 돌면서 `exclude_dates`에 없고 관측이 있는 날만 n건까지 채운다 (Q31). `exclude_dates`는 사후 검증이 자기 자신과 앞뒤 날짜를 빼는 데 쓴다.
  - `select_cases(llm, cache_conn, stn, tmfc, candidates: list[Case], max_n: int) -> list[Case]` — 캐시가 있으면 그대로, 없으면 프롬프트2(`purpose="cases"`). 파싱 실패면 빈 목록(캐시하지 않음)
- [ ] **Step 1: 실패하는 테스트 작성** — 임시 Chroma(`DeterministicFakeEmbedding`) + 임시 SQLite
  - `test_candidates_same_office_only`: 156·109 지방청 개황 각 3건 → `office="156"` 결과는 모두 156
  - `test_candidates_skip_missing_obs`: 1순위 날짜의 관측이 없으면 빠지고, 다음 날짜들로 n건을 채움
  - `test_select_uses_cache`: 첫 호출은 `FakeLLM(['{"selected":[2]}'])`로 2번 후보, 두 번째 호출은 LLM 호출 0번에 같은 결과
  - `test_select_parse_failure_not_cached`: 응답 2번 모두 JSON이 아니면 `[]`이고, 캐시에 저장되지 않음
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 테스트 통과 확인**
- [ ] **Step 5: Commit** — `feat/유사 사례 후보·선별·캐시`

### Task 8: 외부 문서 수집·색인과 근거 검색 (F2003~F2006, F2014, F2016)

**Files:**
- Create: `code/rag/collect.py`, `code/tests/test_collect.py`

**Interfaces:**
- Consumes: `ADAPTERS`, `Candidate`, `Doc`, `Plan`, `select_messages`, `parse_selected`, `ask_json`, cache 함수, `upsert_changed`, `CONFIG["rag"]`
- Produces:
  - `collect(llm, store, cache_conn, stn: str, plan: Plan, on_step) -> list[str]` — 질문 시 수집 출처(`wiki`, `nasa`, `noaa`)의 검색어마다: 이미 `seen_query`면 건너뛴다. 아니면 `search` → 후보를 모아 프롬프트2(`purpose="docs"`) → 고른 것만 `fetch` → `RecursiveCharacterTextSplitter(chunk_size, chunk_overlap)` → ID `{stn}:{doc_id}:{순번}`, 메타데이터 `{"source_type": source, "stn", "doc_id", "title", "url", "query", "collected_at"}`로 색인 → `mark_query`. 출처 하나가 실패(`RuntimeError`, `BlockedHost`)하면 `on_step("… 출처를 건너뜀")`만 남기고 나머지는 계속한다. 돌려주는 값은 새로 색인한 문서 제목.
  - `search_docs(store, stn: str, plan: Plan) -> list[Document]` — 검색어가 있는 출처마다 그 출처 언어의 검색어로 `filter={"$and": [{"source_type": source}, {"stn": {"$in": [stn, "common"]}}]}`를 걸어 `search_type`에 따라 `similarity_search(k=top_k)` 또는 `max_marginal_relevance_search(k=top_k, fetch_k=fetch_k)`. 결과를 합쳐 `top_k`개를 넘기지 않는다.
- [ ] **Step 1: 실패하는 테스트 작성** (어댑터는 가짜 모듈로 교체)
  - `test_collect_indexes_selected_with_ids`: 후보 2건 중 프롬프트2가 1번 선택 → 그 문서만 `{stn}:wiki-1:0` 등으로 색인되고 메타데이터에 `query`, `collected_at`이 있음
  - `test_collect_skips_cached_query`: 같은 (stn, source, query) 두 번째 호출 → 어댑터 `search` 호출 0번 (NF2002)
  - `test_collect_skips_failed_source`: nasa `search`가 `RuntimeError` → wiki는 그대로 색인되고 `on_step` 메시지에 "NASA"
  - `test_chunk_size_from_config`: `chunk_size`를 500으로 바꾸면 2,400자 문서의 청크 수가 늘어남
  - `test_search_scoped_to_station_or_common`: 다른 지점 `stn`으로 색인된 청크는 결과에 없고 `common` 청크는 있음
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 테스트 통과 확인**
- [ ] **Step 5: Commit** — `feat/외부 문서 수집·색인과 근거 검색`

### Task 9: 근거 모델과 LangGraph (retrieve / generate)

**Files:**
- Create: `code/rag/evidence.py`, `code/rag/graph.py`, `code/tests/test_graph.py`

**Interfaces:**
- Consumes: Task 5~8의 모든 Produces
- Produces:
  - `@dataclass Evidence(kind: str, doc_id: str, title: str, url: str, text: str)` — `kind`는 `"지점 정보"`, `"오늘 개황"`, `"유사 사례"`, `"위키백과"`, `"NASA"`, `"NOAA"`, `"IPCC 용어집"`, `"기상청 용어·기준"` 중 하나. `KIND_GROUP`이 앞 셋은 `"항목"`, 나머지는 `"외부 문서"`로 묶는다 (F2007).
  - `merge(*groups: list[Evidence]) -> list[Evidence]` — 순서를 유지하고 `doc_id` 중복을 제거한다.
  - `evidence_block(items: list[Evidence]) -> str` — `[근거 N] (kind) title\n text`
  - `cited(answer: str, items: list[Evidence]) -> list[tuple[int, Evidence]]` — `step7_skeleton.py`의 `CITE_PATTERN`·`cited_sources`와 같은 규칙. 없는 번호는 무시한다.
  - `class GraphState(TypedDict)`: `stn: str`, `question: str`, `history: list[dict]`, `now: datetime`, `evidence: list[Evidence]`, `steps: list[str]`, `answer: str`
  - `build_graph(deps: Deps) -> CompiledGraph`. `Deps`는 `llm`, 스토어 3개(`station_meta`, `forecast_texts`, `climate_docs`), `live_forecasts`, DB 연결, 캐시 연결, `stations`, `on_step`을 담는 dataclass.
    - 노드 `retrieve`: (1) 지점 정보 근거 = 지점 메타 텍스트 + 오늘 기준값·오늘 관측 `anomaly_sentence`, (2) 오늘 개황 근거(`fetch_latest_forecast` → `live_forecasts`에 upsert, 없으면 "오늘 개황을 받지 못했습니다" 단계 기록), (3) 프롬프트1 → `Plan`, 실패면 `Plan(False, 빈 목록들)`, (4) `need_cases`면 `case_candidates` → `select_cases`, (5) 검색어가 있으면 `collect` → `search_docs`, (6) `merge`. 순서는 Q16 순서를 따른다.
    - 노드 `generate`: `answer_messages` → `llm.invoke` → `answer`
- [ ] **Step 1: 실패하는 테스트 작성** (FakeLLM 3응답: 계획 JSON, 선별 JSON, 답변 문자열)
  - `test_graph_has_two_nodes`: `build_graph(...).get_graph().nodes`에서 `__start__`·`__end__`를 뺀 노드가 `{"retrieve", "generate"}`
  - `test_station_and_today_forecast_always_in_context`: 계획이 `need_cases=false`, 검색어 없음이어도 근거 1·2번이 `"지점 정보"`, `"오늘 개황"`
  - `test_no_external_search_for_today_weather`: 계획에 검색어가 없으면 어댑터 `search` 호출 0번
  - `test_cited_ignores_unknown_numbers`: 답변 `"맑음 [근거 2] 비 [근거 9]"`, 근거 3개 → `cited`는 2번만
  - `test_plan_failure_still_answers`: 프롬프트1 응답 2번이 모두 JSON이 아니면 유사 사례·외부 문서 없이 `answer`가 채워짐
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현**
- [ ] **Step 4: 테스트 통과 확인**
- [ ] **Step 5: Commit** — `feat/근거 병합과 retrieve·generate 그래프`

### Task 10: service — 화면이 부르는 진입점

**Files:**
- Create: `code/service.py`, `code/tests/test_service.py`

**Interfaces:**
- Consumes: `build_graph`, `Deps`, `cited`, `PLAIN_SYSTEM`, `match_stations`, `get_store`, `connect`, `connect_cache`, `fetch_stations`
- Produces:
  - `@dataclass Answer(text: str, cited: list[tuple[int, Evidence]], steps: list[str], has_cases: bool)`
  - `check_ready() -> list[str]` — 문제 목록. `GMS_KEY` 없음, `KMA_API_KEY` 없음, `station_meta` 0건, `forecast_texts` 0건, `weather.db` 없음일 때 각각 실행할 스크립트까지 적은 안내 문구 (F2012). 키 값은 넣지 않는다.
  - `ask(stn: str, question: str, history: list[dict], on_step=lambda s: None) -> Answer` — RAG 채팅
  - `plain_chat(history: list[dict]) -> str` — `[{"role": "system", "content": PLAIN_SYSTEM}] + history`, 근거 없음 (Q30)
  - `today_report(stn: str, on_step=...) -> tuple[list[dict], Answer]` — 비교표 행(항목, 오늘 관측, 최근 10년 기준값, 차이, 판정)과, 고정 질문 `"오늘 날씨를 최근 10년 기준값과 과거 유사 사례에 비추어 설명해줘"`를 `need_cases=True`로 강제해 얻은 답변 (F2010)
  - `explore(condition: str) -> list[str]` — `station_meta` 유사도 상위 15개 → 프롬프트2(`purpose="stations"`) → 지점번호 목록 (F2011)
  - `resolve_location(text: str) -> list[str]` — `match_stations` 감싼 것
- [ ] **Step 1: 실패하는 테스트 작성** (`build_graph`·LLM 주입)
  - `test_check_ready_reports_missing_key_without_value`: `GMS_KEY` 없음 → 문구에 `"GMS_KEY"`, 다른 환경 변수 값은 없음
  - `test_plain_chat_sends_only_system_and_history`: FakeLLM이 받은 메시지 = system 1개 + 기록, 지점명 문자열 없음
  - `test_ask_returns_only_cited`: 근거 3개, 답변이 `[근거 1]`만 인용 → `Answer.cited` 길이 1
  - `test_today_report_table_rows`: 6개 항목 행, 판정 값이 `classify` 결과와 같음
- [ ] **Step 2: 실행해 실패 확인**
- [ ] **Step 3: 구현** — 스토어·DB 연결은 모듈 수준에서 한 번만 만든다 (Streamlit은 `@st.cache_resource`로 `service` 객체를 감싼다).
- [ ] **Step 4: 테스트 통과 + 실제 1회** — `python -c "import service; a = service.ask('108', '오늘 서울 기온이 최근 10년 평균보다 높아?', []); print(a.text); print([e.title for _, e in a.cited])"` → 답변과 인용 근거 제목 출력
- [ ] **Step 5: Commit** — `feat/service 진입점`

### Task 11: Streamlit 화면

**Files:**
- Create: `code/app.py`

**Interfaces:**
- Consumes: `service.*` 전부 (다른 모듈은 import하지 않음)

- [ ] **Step 1: 시작 시 점검** — `check_ready()`가 비어 있지 않으면 `st.error`로 문구를 보여 주고 `st.stop()`. 트레이스백은 보이지 않게 모든 `service` 호출을 `try/except Exception`으로 감싸고 안내 문구만 보여 준다 (NF2004).
- [ ] **Step 2: 사이드바** — 지점 `selectbox`(`key="stn"`, 표시 `"{이름}({번호}) · {시/도}"`; 채팅에서 지점을 바꿀 때는 `plus_widget_key.py`의 key+콜백 방식으로 `st.session_state.stn`을 바꾼다), 색인 건수(`station_meta`·`forecast_texts`·`climate_docs`), 조건 탐색 입력과 결과 카드(누르면 그 지점으로 이동), "오늘 날씨 리포트" 버튼(비교표 `st.dataframe` + 답변 + 근거).
- [ ] **Step 3: 본문 두 열** — 왼쪽 "단순 채팅", 오른쪽 "RAG 채팅". 열마다 자기 `st.chat_input`(key `plain_in`, `rag_in`)과 자기 기록을 둔다. 기록은 `st.session_state.histories[stn] = {"plain": [...], "rag": [...]}`이고, 다시 그릴 때 RAG 메시지는 저장해 둔 `cited`로 근거 목록도 다시 그린다.
- [ ] **Step 4: RAG 입력 흐름** — `resolve_location(질문)`이 1개면 그 지점으로 바꾼 뒤 답한다. 2개 이상이면 후보 버튼만 보여 주고 답하지 않는다. 0개면 현재 지점으로 답한다. `st.status`에 `on_step` 메시지를 차례로 쓰고, 끝나면 수집한 문서 제목을 보여 준다. 답변 아래에는 인용 근거 expander(`[근거 N] 제목 · 유형 · [원문](url)`), 인용 0건 안내, 고정 문구(Global Constraints)를 둔다.
- [ ] **Step 5: 수동 확인** — `cd code && ../.venv/Scripts/streamlit.exe run app.py`
  - 왼쪽·오른쪽에 같은 질문 "오늘 서울 기온이 최근 10년 평균보다 높아?"를 따로 입력해서 왼쪽은 근거 없이, 오른쪽은 근거와 함께 답하는지 본다.
  - 오른쪽에 "고창 날씨"를 입력해 후보 버튼 2개가 나오는지, "강릉 날씨"면 사이드바가 강릉으로 바뀌는지 본다.
  - 지점을 바꾸면 양쪽 대화가 함께 바뀌는지 본다.
  - `.env`의 `GMS_KEY`를 잠시 지우면 안내만 보이는지 본다.
- [ ] **Step 6: Commit** — `feat/Streamlit 단순·RAG 채팅 화면`

### Task 12: 검증 스크립트 (사후 검증, F2014, F2015)

**Files:**
- Create: `code/scripts/backtest_cases.py`, `code/scripts/compare_mmr.py`, `code/scripts/compare_rag.py`, `docs/검증결과.md`

**Interfaces:**
- Consumes: `case_candidates`, `get_obs`, `get_baseline`, `search_docs`, `service.ask`, `service.plain_chat`

- [ ] **Step 1: `backtest_cases.py`** — 2025년 `forecast_texts`에서 지방청마다 무작위 30일(시드 0)을 뽑는다. 각 날짜 D에 대해 같은 지방청 상위 5건(D ±3일 제외)의 대표 지점 최고기온 평균을 구해, D의 실제 최고기온과의 MAE를 **D의 기준값 평균**의 MAE와 비교한다. 비 온 날(≥1mm) 맞힘률도 계산한다. 대표 지점은 지방청 번호와 같은 지점이고, 109는 108(서울)로 둔다. 결과 표를 `docs/검증결과.md`의 "유사 사례 사후 검증" 절에 붙인다. 프롬프트2 선별 없이 순수 유사도만 쓰므로 LLM 호출이 없다.
- [ ] **Step 2: `compare_mmr.py`** — 대표 질문 ⑤를 서울(108)로 similarity와 MMR 두 방식으로 검색해 근거 제목 목록을 나란히 출력한다 (F2014).
- [ ] **Step 3: `compare_rag.py`** — AGENTS.md의 대표 질문 5개를 지점 `[108, 156, 108, 100, 108]`로 `plain_chat`(질문 1개짜리 기록)과 `ask`에 돌려, 두 답과 인용 근거를 `docs/검증결과.md`의 "RAG 전후 비교" 표에 적는다. 사실 정확성·근거 제시·"모르면 모른다" 세 칸은 비워 두고 사람이 채운다 (F2015). 질문마다 `ask` 전체 처리 시간(첫 실행·두 번째 실행)도 초 단위로 적는다 (NF2001, 두 번째는 검색어 캐시 효과 확인).
- [ ] **Step 4: `docs/검증결과.md` 틀** — 명세 4.1~4.8 확인 항목을 표로 옮기고(통과/실패/미확인 칸, 캡처 경로 `docs/screenshots/…`), 위 세 결과 절을 둔다.
- [ ] **Step 5: 실행 확인** — 세 스크립트를 실행하고 문서에 결과가 들어갔는지 본다.
- [ ] **Step 6: Commit** — `docs/검증 스크립트와 결과`

### Task 13: 제출 문서

**Files:**
- Create: `docs/RAG_파이프라인_설계.md`, `README.md`
- Modify: `docs/요구사항정의서.md`, `AGENTS.md`(구조 절)

- [ ] **Step 1: `docs/요구사항정의서.md`** — 도메인 "(미정)"을 채운다: 지점 97개(출처 API허브), 외부 문서 출처와 이용 조건(`data/sources.md` 요약), 근거가 필요한 질문 3개 이상(대표 질문 ①②④), 위험 도메인 아님 + 기상청 안내 문구. 기능 표에 이 프로젝트의 표현을 덧붙인다.
- [ ] **Step 2: `docs/RAG_파이프라인_설계.md`** — 명세 6장 2)의 항목 순서대로 쓴다: 컬렉션 4개(`station_meta`, `forecast_texts`, `live_forecasts`, `climate_docs`)와 SQLite 2개 표의 필드, 수집·청킹·색인 흐름, 병합·중복 제거, 프롬프트 3개의 역할과 출력 형식, 1,000/200·top_k 4를 고른 이유와 바꿨을 때의 차이(Task 12 결과), 근거 표시 방식, 특화 기능 설계 이유(ADR 0001 인용), 출처별 청킹 차이(용어 단위 vs 1,000자)의 이유(F2016), 겪은 문제(영하 기온 결측, cp949, 지점 정보 열 밀림, Chroma 변수 한도).
- [ ] **Step 3: `README.md`** — 개요, 설치(`.venv`, `pip install -r requirements.txt`), `.env` 키 3개, 빌드 순서(`build_climate.py` → `build_forecast.py` → `build_glossary.py`), 실행(`streamlit run app.py`), 기능 표(필수/심화 구분, F2013은 미구현 예정이라고 명시), 데이터 출처·이용 조건.
- [ ] **Step 4: AGENTS.md 구조 절** — 실제 파일 구성으로 고친다.
- [ ] **Step 5: 전체 테스트** — `cd code && ../.venv/Scripts/python.exe -m unittest discover -s tests -v` → 모두 PASS
- [ ] **Step 6: Commit** — `docs/요구사항정의서·설계문서·README`
