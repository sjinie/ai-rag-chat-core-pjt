# 데이터·문서 출처와 이용 조건 (NF2007)

확인일: 2026-10-23. 각 출처의 이용 조건은 해당 사이트의 저작권·이용 안내 페이지를 직접 열어 확인한 내용만 적었다. 찾지 못한 항목은 **미확인**이다.

| 출처 | 쓰는 데이터 | 수집 방식 | 이용 조건 | 확인한 곳 |
|---|---|---|---|---|
| 기상청 API허브 `apihub.kma.go.kr` | ASOS 일자료(2016~2025), 지점 정보, 단기예보 개황(2021~2025, 오늘) | API 키로 호출, 원문을 `data/raw/`에 캐시 | **미확인** — 첫 화면에 이용 조건 문구 없음("이용안내" 메뉴는 열어 보지 못함). 같은 자료의 기상자료개방포털 이용 조건을 따른다고 가정 | apihub.kma.go.kr 첫 화면 |
| 기상청 기상자료개방포털 `data.kma.go.kr` | (위 ASOS 자료의 공개 출처, 근거 링크로 사용) | 링크만 | 공공누리 "출처표시" 유형 표식이 첫 화면에 있음 → 출처 표시 조건으로 이용 | data.kma.go.kr 첫 화면 |
| 한국어 위키백과 `ko.wikipedia.org` | 기상 현상·지역 문서 본문 | 질문 시 MediaWiki API 검색·본문 수집 | CC BY-SA 4.0(문서에 따라 GFDL 1.3 병행). 사용 시 저작자 표시, 가공물은 같은 라이선스 | 위키백과:저작권 |
| NASA `science.nasa.gov` | 기후 과학 설명 글 | 질문 시 WordPress 검색 API·본문 수집 | NASA 자료는 미국에서 대체로 저작권 대상이 아님("generally are not subject to copyright in the United States"). NASA를 출처로 표기. 보증을 암시하면 안 되고, AI 결과물을 NASA 작성물로 표기하면 안 됨. 제3자 저작물 표시가 있는 자료는 예외 | NASA Images and Media Usage Guidelines |
| NOAA Climate.gov `www.climate.gov` | Climate Q&A, Understanding Climate 글 | 사이트맵 목록에서 선별 후 본문 수집 (`/search`는 robots.txt가 금지해 쓰지 않음) | **미확인** — About 페이지와 정책 링크에서 저작권 문구를 찾지 못함 | climate.gov/about |
| IPCC `www.ipcc.ch` | AR6 WG1 Annex VII 용어집(PDF) | 한 번 내려받아 용어 단위로 색인 | 개인·비상업 용도로 내려받기 허용. 그림이나 **짧은 발췌**는 보고서 전체 이름 등 원출처를 밝히면 허가 없이 사용 가능. 재배포·파생물 작성 등 그 밖의 용도는 IPCC 허가 필요 → 화면에는 인용된 짧은 발췌만, 보고서 이름과 함께 표시 | ipcc.ch/copyright |
| 기상청 날씨누리 `www.weather.go.kr` | 기상특보 기준(forecast03), 예보용어(forecast05) | 한 번 받아 용어 단위로 색인 | **미확인** — 날씨누리 저작권 안내 페이지를 찾지 못함 | weather.go.kr |

## 지키는 방법

- 근거 목록에 출처 이름과 원문 링크를 항상 표시한다 (F2008).
- 외부 문서 요청은 위 호스트로만 보내고(`code/rag/web.py`), User-Agent에 연락처를 넣는다 (NF2006).
- 수집한 원문은 저장소에 커밋하지 않는다(`data/raw/`, `data/chroma/`는 git 제외).
- **미확인** 항목은 제출 전에 각 기관 안내 페이지나 문의처로 다시 확인한다.
