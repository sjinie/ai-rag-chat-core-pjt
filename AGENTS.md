# AGENTS.md

SSAFY AI 코어 프로젝트 2회차 — **RAG 기반 도메인 지식 서비스**.
도메인: **날씨** — 사용자가 입력한 위치의 현재 날씨·예보를 최근 10년 평균과 비교해 근거와 함께 설명하는 챗봇.

- 명세 원본: `docs/AI코어프로젝트_2회차_요구사항정의서.pdf`
- 요구사항 요약: `docs/요구사항정의서.md` (F2001~F2016, NF2001~NF2007)
- 실습 참고 코드: `references/streamlit_lab/` — `step7_skeleton.py`가 앱 골격, `step8_wiki_api.py`가 위키 수집 재료. 수정하지 말고 가져다 쓴다.

## 절대 규칙 (명세 필수 · 수정 불가)

- **F2001~F2012는 모두 구현한다.** 도메인에 맞게 표현만 바꿀 수 있다.
- LangGraph는 **retrieve / generate 두 노드**로 구성한다 (F2007).
- 답변은 검색된 근거만 사용하고, 근거가 없으면 "확인되지 않는다"고 답한다. 주장마다 `[근거 N]`을 붙이고, **실제로 인용된 근거만** 제목·원문 출처와 함께 표시한다. 인용이 0건이면 그 사실을 안내한다 (F2008).
- 청크 크기·중복 길이·Top-k·검색 방식(similarity/MMR)은 **코드가 아니라 설정 파일**에 둔다 (F2005, F2006, F2014).
- API 키는 `.env`로만 관리한다. 코드·로그·화면에 키, 프롬프트 전문, 트레이스백을 노출하지 않는다 (NF2003, NF2004). 오류는 안내 문구만 보여준다.
- 수집·색인·검색·생성·UI 책임을 모듈로 분리하고, 도메인 종속 코드는 `domain/`에만 둔다 (NF2005).
- 외부 API는 재시도(429 대기)·호출 간격을 지키고, 위키백과는 User-Agent에 영문 연락처를 넣는다 (NF2006).
- 사용한 데이터·문서의 출처와 이용 조건을 `data/sources.md`에 기록한다 (NF2007).

## 도메인 설계 (확정 사항)

| 명세 개념 | 이 프로젝트 |
|---|---|
| 항목 (약 100건) | ASOS 종관 지점 97개 |
| 항목 선택 (F2009) | 채팅 입력과 사이드바 지점 목록 둘 다 사용, 서로 동기화. 채팅의 위치는 **지점명·시/군/구 글자 매칭**(앞뒤 낱말 경계 확인: '남해안'·'강화된다'는 지명 아님)으로 찾고, **현재와 다른 지점이면 바꿀지 묻는다**(하나든 여럿이든). '지금 지점 그대로'도 고를 수 있다. 관할 지방청은 예보구역코드 `FCT_ID` 앞자리(`office_for`). 대화 기록은 지점별로 분리 |
| 기후 항목 6종 | 최고기온 · 평균기온 · 최저기온 · 상대습도 · 평균풍속 · 강수량 |
| 비교 기준 | **최근 10년(2016~2025) ±7일 관측 평균·표준편차**. 공식 평년값(30년)이 아니므로 화면·답변에서 "평년값"이라 부르지 않고 "최근 10년 평균"이라 쓴다 |
| 항목 자체 문서 (F2003·F2004) | **오늘 개황**(관할 지방청의 오늘 최신 개황). 근거 후보에 항상 들어간다 |
| 날씨 질문 (핵심 흐름) | **유사 사례**: 오늘 개황의 오늘 문단으로 `forecast_texts`에서 **같은 관할 지방청** 안의 유사도 상위 10건(날짜 조건 없음) → 각 날짜의 선택 지점 관측 + 그날 기준값과의 차이를 붙여 후보로 → **프롬프트2가 질문에 맞는 사례만 선별**(최대 5건) → 선별 결과는 (지점, 개황 발표시각)별로 캐시. 다시 색인하지 않는다. 화면에 "과거 유사 사례 참고이며 예보가 아님" 표시 |
| 질문 종류 판단 | 프롬프트1(도메인 전문가)이 retrieve 노드 안에서 판단: 유사 사례가 필요한지, 어떤 허용 출처에 어떤 검색어로 찾을지. 필요 없는 근거는 찾지 않는다 (예: "오늘 날씨"를 위키에서 검색하지 않음) |
| 외부 문서 | **허용 출처**에서만 가져온다: 한국어 위키백과, NASA Climate, NOAA Climate.gov, IPCC 용어집(AR6 WG1 부록 VII PDF), 기상청 날씨누리 특보 기준(forecast03)·예보용어(forecast05). 위키·NASA(WordPress 검색 API)·NOAA(robots가 `/search`를 막아 사이트맵의 Climate Q&A·Understanding Climate 목록 사용)는 **질문할 때 수집**, IPCC·기상청 페이지는 고정 문서라 **미리 한 번 색인**(용어 하나 = 청크 하나). 프롬프트2로 선별 → 본문·원문 URL 수집 → `climate_docs` 색인. **허용 목록 밖 도메인은 코드에서 차단** (리다이렉트 포함). 여러 출처 결합(F2016)은 처음부터 구현 |
| 도메인 특화 기능 (F2010) | 유사 사례의 실제 날씨 요약 + 오늘 vs 최근 10년 기준값 비교. 사이드바 "오늘 날씨 리포트" 버튼 |
| 답변 모드 | **단순 채팅**(전문가 역할 system 메시지 + 대화만, 지점·날짜도 사용자가 말해야 앎, 근거 없음)과 **RAG 채팅**을 코드로 분리하고, 화면 양쪽에 두 채팅을 나란히 두고 **입력창도 각각 따로** 둔다. 기록도 양쪽 따로, 둘 다 지점별로 저장 (F2015 전후 비교에도 사용). 대표 질문(확정): ① 오늘 서울 기온이 최근 10년 평균보다 높아? ② 오늘 광주 예보와 비슷했던 날에는 실제로 비가 얼마나 왔어? ③ 열대야 기준이 뭐야? ④ 대관령은 왜 한겨울에 다른 곳보다 훨씬 추워? ⑤ 온실효과가 한반도 여름 기온에 어떤 영향을 줘? |
| 검색어 언어 | 프롬프트1이 출처별 언어로 검색어를 낸다 (위키·기상청 = 한국어, NASA·NOAA·IPCC = 영어). 답변은 한국어 |
| 대화 기록 | references처럼 대화 전체를 `st.session_state`에 저장하고 매번 history 전체를 넘긴다. 지점별로 분리 |
| 오늘 개황 시각 | 05시 이전에는 전날 17시 발표분을 쓰고 근거 제목에 발표 시각을 표시 |
| 유사 사례 후보 | 선택 지점의 관측이 없는 날은 빼고 다음 순위로 채워 10건 유지 |
| MMR (F2014) | 외부 문서 청크 검색에만 적용(20개 → 4개). `search_type`으로 similarity/MMR 전환, 비교 스크립트로 차이 출력 |
| 검증 기록 | 명세 4장 체크리스트·사후 검증·F2014/F2015 비교는 `docs/검증결과.md`, 캡처는 `docs/screenshots/` |
| 범위 | 심화 F2014~F2016은 처음부터 구현. **F2013(Vue.js 프론트엔드)은 아직 구현하지 않는다** — 화면은 Streamlit chat. 단 핵심 기능은 `service.ask(...)` 하나로 두어 나중에 FastAPI가 같은 함수를 쓰게 한다 |

- **편차·평균·판정(높음/낮음)은 Python 코드로 한다.** LLM에는 계산 결과만 근거로 넘기고 설명만 맡긴다.
- 숫자는 임베딩하지 않는다. 임베딩은 문장(예보 개황, 외부 문서, 지점 프로필)에만 쓰고, 숫자는 SQLite에서 날짜·지점으로 조회한다.
- 위험 도메인은 아니지만 "공식 특보·예보는 기상청 발표를 확인하세요" 안내를 표시한다.

## 데이터 저장

| 저장소 | 내용 | 키 | 조회 |
|---|---|---|---|
| Chroma `station_meta` | 지점 프로필(주소·고도·산지·관할 지방청) + 월별 10년 평균 | `{지점번호}` | 선택 지점은 ID로 직접, 조건 탐색(F2011)은 유사도 |
| Chroma `forecast_texts` | 지방청별 단기예보 개황 '종합·오늘' 문단, 2021~2025, 05시 발표 | `fcst:{지방청}:{YYYYMMDD}` | 유사도 + 필터(같은 관할 지방청만). 메타데이터 `body`에 원문 전체, `url`·`collected_at` |
| Chroma `live_forecasts` | 오늘 개황(항목 자체 문서, 질문 시 색인) | `live:{지방청}:{발표시각}` | ID 직접 |
| Chroma `climate_docs` | 외부 문서 청크 | 질문 시 수집 `{지점}:{문서ID}:{순번}`, 고정 문서 `common:{ipcc|kma_terms}:{용어}:{순번}` | 유사도/MMR, 필터 `stn ∈ {지점, common}` |
| SQLite `data/cache.db` | 검색어 캐시, 유사 사례 선별 캐시 | `(stn, source, query)`, `(stn, tmfc)` | `rag/cache.py` |
| SQLite `data/weather.db` `obs_daily` | 지점 × 날짜 실제 관측 6종 (2016~2025) | `(stn, date)` | `get_obs` |
| SQLite `data/weather.db` `baseline` | 지점 × MMDD 10년 평균·표준편차·표본 수 | `(stn, mmdd)` | `get_baseline` |

- 한 번 받은 데이터는 저장하고 재사용한다. 오늘 예보·관측은 **키에 발표·관측 시각을 넣어** 만료시킨다 — 어제 데이터로 오늘을 답하면 안 된다.
- 재색인해도 같은 ID는 덮어쓰기만 일어나야 한다 (F2002).
- 이미 수집한 검색어는 다시 수집하지 않는다 (F2004, NF2002).

## 기상청 API허브 (`https://apihub.kma.go.kr/api`, 키: `KMA_API_KEY`)

| 용도 | 엔드포인트 | 상태 |
|---|---|---|
| 기간 일자료 (10년 평균 계산) | `typ01/url/kma_sfcdd3.php?tm1=YYYYMMDD&tm2=YYYYMMDD&stn=0` | ✅ 동작. 공백 구분 |
| 일자료 | `typ01/url/kma_sfcdd.php?tm=YYYYMMDD&stn=0` | ✅ 동작. 쉼표 구분. 오늘 자료는 최고·최저만 있고 나머지 결측 |
| 공식 평년값 (참고용) | `typ01/url/sfc_norm1.php?tmst=2021&norm=D&stn=0&MM1=&DD1=&MM2=&DD2=` | ✅ 동작. 대구·전주·세종·홍성 등 13개 ASOS 지점 없음 |
| 시간자료 (현재 날씨) | `typ01/url/kma_sfctm2.php` | ❌ 403 활용신청 필요 |
| 단기예보·초단기실황 | `typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst`, `getUltraSrtNcst` | ❌ 403 활용신청 필요 |
| 지점 정보 | `typ01/url/stn_inf.php?inf=SFC` | ✅ 동작. 영문명에 공백이 있는 행(Jeongseon Gun)은 열이 밀린다 → `parse_stations` 참고. 2026 주소 기준 광주·전남은 "전남광주통합특별시" |
| 단기예보 개황 (원문 텍스트) | `typ01/url/fct_afs_ds.php?stn=지방청&tmfc1=YYYYMMDDHHmm&tmfc2=` | ✅ 동작. 1년 범위 1회 호출 가능. 지방청 9곳 × 하루 3회(05·11·17시). 2016년부터 확인 |
| 특보 자료 | `typ01/url/wrn_met_data.php?wrn=A&reg=0&tmfc1=&tmfc2=` | ✅ 동작. 텍스트가 아니라 코드(특보구역·종류·수준) — 구역 코드표 미확보 |

- 응답은 **EUC-KR** 계열 — `response.content.decode("cp949")` (개황 원문에 EUC-KR 밖 글자가 있어 euc-kr로는 실패). `#`으로 시작하는 줄은 주석.
- 결측값은 `-9`, `-99`. 단 일강수량 `RN_DAY = -9.0`은 "강수 없음"이므로 0으로 처리한다.
- `kma_sfcdd(3)` 열 위치(0부터): `WS_AVG 2`, `TA_AVG 10`, `TA_MAX 11`, `TA_MIN 13`, `HM_AVG 18`, `RN_DAY 38`.
- 기상청 API에는 시/도 단위가 없다. 지점번호(관측) / 격자 nx,ny(예보) 단위다.

## 기술 스택 (명세 고정 버전 — 임의로 바꾸지 않는다)

Python 3.10+ · Streamlit 1.62.0 · LangChain 1.3.14 · LangGraph 1.2.10 · LangSmith 0.10.17 · langchain-core 1.6.0 · langchain-openai 1.4.3 · langchain-community 0.4.2 · langchain-chroma 1.1.0 · langchain-text-splitters 1.1.2 · ChromaDB 1.5.9 · OpenAI 2.54.0 · Requests 2.34.2 · python-dotenv 1.2.3 · typing-extensions 4.16.0
(심화) fastapi 0.141.1 · uvicorn[standard] 0.52.4 · pydantic 2.13.5 · (PDF) pypdf

- LLM은 SSAFY GMS 경유 (references/streamlit_lab 방식): `ChatOpenAI(model=..., api_key=GMS_KEY, base_url=GMS_BASE_URL)`, `GMS_BASE_URL = "https://gms.ssafy.io/gmsapi/api.openai.com/v1/"`. 모델은 **gpt-6-luna로 통일**(프롬프트 3개 모두), 임베딩은 text-embedding-3-small. 모델명은 `config.toml`에 둔다.
- `.env` 키: `GMS_KEY`, `KMA_API_KEY`, `WIKI_CONTACT`(영문 이메일).

## 구조

소스는 `code/`, 데이터는 `data/`. 스크립트는 `code/`에서 실행한다 (모듈 import 기준 경로).

```
code/
  config.toml           # 모델명, 기간·창 크기, 개황 기간, [rag] 청크·top_k·검색 방식·유사 사례 수, [web] 허용 호스트
  config.py             # config.toml + 루트 .env 로드
  build_climate.py      # 10년 일자료 → weather.db(obs_daily·baseline) + station_meta 색인
  build_forecast.py     # 5년 단기예보 개황 → forecast_texts 색인
  build_glossary.py     # IPCC 용어집 PDF·기상청 특보 기준·예보용어 → climate_docs(common) 색인
  service.py            # 화면이 부르는 유일한 진입점: Service.ask / plain_chat / today_report / explore / resolve_location, check_ready
  app.py                # Streamlit: 사이드바(지점·조건 탐색·리포트) + 단순 채팅 | RAG 채팅
  domain/               # 도메인 종속 코드
    kma.py              # API허브 호출·파싱·캐시, 오늘 최신 개황, 오늘 관측
    stations.py         # 기준값·표준편차, 기후 특징, 편차 판정, 위치→지점 매칭, 관할 지방청
    weather_db.py       # SQLite 정형 데이터 (obs_daily, baseline)
    prompts.py          # 프롬프트 3개 + 단순 채팅 역할, JSON 파싱(ask_json)
    cases.py            # 유사 사례 후보·선별·캐시 (ADR 0001)
  rag/
    store.py            # Chroma 컬렉션, 바뀐 것만 임베딩(메타데이터만 바뀌면 임베딩 없이 갱신)
    web.py              # 허용 호스트만 부르는 HTTP (User-Agent·간격·재시도·리다이렉트 검사)
    html_text.py        # HTML → 본문 텍스트
    sources/            # 질문 시 수집 출처: wiki.py, nasa.py, noaa.py (search / fetch)
    fixed_docs.py       # IPCC PDF·기상청 표를 용어 단위로 자르기
    collect.py          # 검색어 → 출처 검색 → 프롬프트2 → 수집 → 청킹·색인, 근거 검색(similarity/MMR)
    cache.py            # data/cache.db: 검색어 캐시, 유사 사례 선별 캐시
    evidence.py         # Evidence, 병합·중복 제거, 근거 블록, 인용 추출
    graph.py            # LangGraph retrieve / generate
  scripts/              # 검증: backtest_cases, compare_mmr, compare_rag (docs/검증결과.md에 기록)
  tests/                # unittest (가짜 LLM·임베딩, 네트워크 없음)
data/
  raw/                  # API·웹 원문 캐시 (git 제외)
  chroma/               # 벡터DB (git 제외)
  weather.db, cache.db  # 정형 날씨 데이터, 처리 캐시 (git 제외)
  sources.md            # 출처·이용 조건
```

## 작업 방식

- 가상환경: 루트 `.venv` (`pip install -r requirements.txt`)
- 실행(`code/`에서): 색인 `python build_climate.py` → `python build_forecast.py` → `python build_glossary.py` / 앱 `streamlit run app.py`
- 테스트(`code/`에서): `python -m unittest discover -s tests -v`. 자체 점검: `python domain/stations.py`, `python -m domain.kma`
- 검증 스크립트(`code/`에서): `python -m scripts.backtest_cases` / `compare_mmr` / `compare_rag`
- 새 로직(파싱, 편차 계산, 근거 번호 추출 등)에는 작은 assert 기반 검증을 남긴다.
- 검증은 실행 결과로 증명한다 — 명세 4장 체크리스트(색인 수 일치, 재색인 시 청크 수 불변, 근거 번호와 표시 목록 일치, 키 없음/색인 없음 안내 등).
- 커밋 메시지·문서는 한국어로 쓴다.
