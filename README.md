# 날씨 RAG 챗봇

SSAFY AI 코어 프로젝트 2회차 — RAG 기반 도메인 지식 서비스.

선택한 기상 관측 지점의 **오늘 예보(기상청 단기예보 개황)**를 **과거 유사 사례**(문장이 비슷했던 과거 예보와 그날의 실제 관측)와 **최근 10년 기준값**, **허용된 외부 문서**(위키백과·NASA·NOAA·IPCC·기상청)에 비추어 설명하고, 답변에 쓴 근거를 함께 보여 준다. 화면 왼쪽은 근거 없이 답하는 단순 채팅, 오른쪽은 RAG 채팅이라 두 답을 나란히 비교할 수 있다.

- 설계: [docs/RAG_파이프라인_설계.md](docs/RAG_파이프라인_설계.md) · 요구사항: [docs/요구사항정의서.md](docs/요구사항정의서.md) · 검증: [docs/검증결과.md](docs/검증결과.md)
- 용어: [GLOSSARY.md](GLOSSARY.md) · 설계 결정: [docs/adr/](docs/adr/) · 출처·이용 조건: [data/sources.md](data/sources.md)

## 설치

```bash
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash. macOS/Linux는 .venv/bin/activate
pip install -r requirements.txt
```

프로젝트 루트에 `.env`를 만든다(`.env`는 커밋하지 않는다).

```
GMS_KEY=SSAFY GMS 키
KMA_API_KEY=기상청 API허브 키 (지상관측 일자료·지점 정보·단기예보 개황·평년값 활용신청 필요)
WIKI_CONTACT=영문 이메일 (외부 출처 User-Agent 연락처. 없으면 앱이 시작되지 않음 — NF2006)
```

## 데이터 준비와 색인 (처음 한 번, `code/`에서)

```bash
cd code
python build_climate.py    # ASOS 10년 일자료 → weather.db(관측·기준값) + 지점 색인(97곳)
python build_forecast.py   # 단기예보 개황 5년(관할 지방청 9곳) → 개황 색인
python build_glossary.py   # IPCC 용어집·기상청 특보 기준·예보용어 → 외부 문서 색인(공통)
```

받은 원문은 `data/raw/`에 남아, 다시 실행하면 API를 부르지 않는다. 두 번째 실행부터는 바뀐 문서만 다시 색인한다.

## 실행

```bash
cd code
streamlit run app.py
```

## 기능

| 구분 | ID | 기능 | 구현 |
|---|---|---|---|
| 필수 | F2001~F2002 | 지점 97곳 메타데이터 색인 | `build_climate.py`, `station_meta` |
| 필수 | F2003~F2005 | 검색어 추출 → 외부 문서 선별·수집 → 청킹·색인 | `domain/prompts.py`, `rag/collect.py`, `rag/sources/` |
| 필수 | F2006~F2008 | 근거 병합, LangGraph retrieve/generate, 인용된 근거만 표시 | `rag/graph.py`, `rag/evidence.py` |
| 필수 | F2009 | 지점 선택(사이드바·채팅 속 지명) + 지점별 대화 기록 | `app.py` |
| 필수 | F2010 | 과거 유사 사례, 오늘 날씨 리포트 | `domain/cases.py`, `service.today_report` |
| 필수 | F2011 | 조건으로 지점 찾기 | `service.explore` |
| 필수 | F2012 | 진행 상태, 키 누락·색인 없음 안내, 기상청 안내 문구 | `service.check_ready`, `app.py` |
| 심화 | F2013 | HTML·CSS·JS 화면 | **미구현**(나중에 Vue.js 예정). 화면은 `service` 함수만 호출하도록 분리 |
| 심화 | F2014 | MMR 검색 | `config.toml`의 `search_type = "mmr"`, `scripts/compare_mmr.py` |
| 심화 | F2015 | RAG 사용 전후 비교 | 화면 양쪽 채팅, `scripts/compare_rag.py` |
| 심화 | F2016 | 여러 종류의 문서 출처 결합 | 웹 문서·PDF 용어집·기상청 페이지·기상청 API 개황 |

검색·청킹 값(청크 1,000자/200자, top_k 4, 검색 방식, 유사 사례 후보 수)과 모델명은 `code/config.toml`에 있다.

## 테스트와 검증

```bash
cd code
python -m unittest discover -s tests -v   # LLM·임베딩·네트워크 없이 도는 단위·화면 테스트
python -m scripts.backtest_cases          # 유사 사례 사후 검증 (LLM 호출 없음)
python -m scripts.compare_mmr             # 유사도 vs MMR 근거 비교
python -m scripts.compare_rag             # 대표 질문 5개 RAG 전후 비교·처리 시간
```

## 데이터 출처와 이용 조건

자세한 내용은 [data/sources.md](data/sources.md).

- 기상청 API허브(ASOS 일자료, 지점 정보, 단기예보 개황) — 기상자료개방포털 공공누리 출처표시 조건 표기
- 한국어 위키백과 — CC BY-SA 4.0
- NASA science.nasa.gov — 미국에서 대체로 저작권 대상 아님, NASA 출처 표기
- IPCC AR6 WG1 용어집 — 비상업 용도의 짧은 발췌를 원출처와 함께 표시
- NOAA Climate.gov, 기상청 날씨누리 — 이용 조건 **미확인**(제출 전 확인 필요)
