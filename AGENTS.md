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
| 항목 선택 (F2009) | 사용자가 chat input으로 위치 입력 → 가장 가까운 지점 + 예보 격자(nx, ny)로 변환. 사이드바 지점 목록과 동기화. 대화 기록은 지점별로 분리 |
| 기후 항목 6종 | 최고기온 · 평균기온 · 최저기온 · 상대습도 · 평균풍속 · 강수량 |
| 비교 기준 | **최근 10년(2016~2025) ±7일 관측 평균**. 공식 평년값(30년)이 아니므로 화면·답변에서 "평년값"이라 부르지 않고 "최근 10년 평균"이라 쓴다 |
| 외부 문서 | 위키백과(지역·기상현상, 항목 자체 문서) + 기상청 이상기후 보고서·용어/특보 기준 PDF. 출처 종류(`wiki`/`pdf`)를 근거에 표시 (F2016) |
| 도메인 특화 기능 (F2010) | 오늘 vs 최근 10년 평균 비교표 + 근거 기반 해설 |

- **편차·평균 계산은 Python 코드로 한다.** LLM에는 계산 결과만 근거로 넘기고 설명만 맡긴다.
- 위험 도메인은 아니지만 "공식 특보·예보는 기상청 발표를 확인하세요" 안내를 표시한다.

## 데이터 저장 (Chroma)

| 컬렉션 | 내용 | ID 규칙 | 조회 |
|---|---|---|---|
| `station_meta` | 지점 정보 + 월별 10년 평균 | `{지점번호}` | 선택 지점은 ID로 직접, 조건 탐색(F2011)은 유사도 |
| `weather_data` | 기준값·관측·예보 캐시 | `base:{지점}:{MMDD}`, `obs:{지점}:{관측시각}`, `fcst:{nx_ny}:{발표시각}` | ID 직접 조회 |
| `climate_docs` | 위키·PDF 청크 | `{지점번호}:{문서ID}:{순번}`, 공통 PDF는 `common:{문서ID}:{순번}` | 유사도/MMR, 필터 `지점번호 or common` |

- 한 번 받은 데이터는 DB에 저장하고 재사용한다. 단 관측·예보는 **ID에 시각을 넣어** 만료시킨다 — 어제 데이터로 오늘을 답하면 안 된다.
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
| 지점 정보 | `typ01/url/stn_inf.php?inf=SFC` | ❌ 403 활용신청 필요 |

- 응답은 **EUC-KR** — `response.content.decode("euc-kr")`. `#`으로 시작하는 줄은 주석.
- 결측값은 `-9`, `-99`. 단 일강수량 `RN_DAY = -9.0`은 "강수 없음"이므로 0으로 처리한다.
- `kma_sfcdd(3)` 열 위치(0부터): `WS_AVG 2`, `TA_AVG 10`, `TA_MAX 11`, `TA_MIN 13`, `HM_AVG 18`, `RN_DAY 38`.
- 기상청 API에는 시/도 단위가 없다. 지점번호(관측) / 격자 nx,ny(예보) 단위다.

## 기술 스택 (명세 고정 버전 — 임의로 바꾸지 않는다)

Python 3.10+ · Streamlit 1.62.0 · LangChain 1.3.14 · LangGraph 1.2.10 · LangSmith 0.10.17 · langchain-core 1.6.0 · langchain-openai 1.4.3 · langchain-community 0.4.2 · langchain-chroma 1.1.0 · langchain-text-splitters 1.1.2 · ChromaDB 1.5.9 · OpenAI 2.54.0 · Requests 2.34.2 · python-dotenv 1.2.3 · typing-extensions 4.16.0
(심화) fastapi 0.141.1 · uvicorn[standard] 0.52.4 · pydantic 2.13.5 · (PDF) pypdf

- LLM은 SSAFY GMS 경유: `ChatOpenAI(model=..., api_key=GMS_KEY, base_url="https://gms.ssafy.io/gmsapi/api.openai.com/v1/")`. 모델명은 설정 파일에 둔다.
- `.env` 키: `GMS_KEY`, `KMA_API_KEY`, `WIKI_CONTACT`(영문 이메일).

## 예정 구조

```
app.py                  # Streamlit UI (step7_skeleton.py에서 출발)
config.toml             # chunk_size, chunk_overlap, top_k, search_type, 모델명
domain/                 # 도메인 종속 코드는 여기만
  kma.py                # API허브 호출 · 파싱
  stations.py           # 지점 텍스트 구성, 위치→지점/격자 변환, 편차 계산
  prompts.py            # 프롬프트 3개 (검색어 추출 / 후보 선별 / 답변 생성)
rag/
  wiki.py               # 위키 검색·본문 (step8 재사용)
  store.py              # Chroma 컬렉션
  collect.py            # 프롬프트1 → 검색 → 프롬프트2 → 수집 → 청킹·색인
  graph.py              # LangGraph retrieve / generate
scripts/build_index.py  # 10년 평균 계산 + station_meta 색인
data/                   # 원천 데이터, sources.md
```

## 작업 방식

- 실행: `streamlit run app.py` / 색인: `python scripts/build_index.py`
- 새 로직(파싱, 편차 계산, 근거 번호 추출 등)에는 작은 assert 기반 검증을 남긴다.
- 검증은 실행 결과로 증명한다 — 명세 4장 체크리스트(색인 수 일치, 재색인 시 청크 수 불변, 근거 번호와 표시 목록 일치, 키 없음/색인 없음 안내 등).
- 커밋 메시지·문서는 한국어로 쓴다.
