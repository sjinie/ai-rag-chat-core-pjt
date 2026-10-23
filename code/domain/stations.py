"""ASOS 지점(항목)과 최근 10년 기준값 계산, 색인 텍스트 구성."""
import calendar
from collections import defaultdict
from datetime import date

VARIABLES = ["ta_avg", "ta_max", "ta_min", "hm_avg", "ws_avg", "rn_day"]
LABELS = {"ta_avg": ("평균기온", "℃"), "ta_max": ("최고기온", "℃"), "ta_min": ("최저기온", "℃"),
          "hm_avg": ("상대습도", "%"), "ws_avg": ("평균풍속", "m/s"), "rn_day": ("강수량", "mm")}
DAYS = 366  # 2월 29일을 포함한 날짜 칸 수

# 단기예보 개황을 내는 지방청. 예보구역코드(FCT_ID) 앞자리로 지점의 관할 지방청을 정한다.
OFFICES = {"109": "수도권기상청", "105": "강원지방기상청", "131": "청주기상지청", "133": "대전지방기상청",
           "146": "전주기상지청", "156": "광주지방기상청", "143": "대구지방기상청", "159": "부산지방기상청",
           "184": "제주지방기상청"}
FCT_PREFIX_OFFICE = [("11A", "109"), ("11B", "109"), ("11C1", "131"), ("11C2", "133"), ("11D", "105"),
                     ("11E", "143"), ("11F1", "146"), ("11F2", "156"), ("11G", "184"), ("11H1", "143"), ("11H2", "159"),
                     ("21F1", "146"), ("21F2", "156")]  # 21F = 전북·전남 서해안 구역


def office_for(fct_id: str) -> str:
    """예보구역코드 → 관할 지방청 번호. 11A 백령도는 수도권, 11E 울릉도·독도는 대구청 관할."""
    return next(office for prefix, office in FCT_PREFIX_OFFICE if fct_id.startswith(prefix))


def day_index(month: int, day: int) -> int:
    """윤년 기준 0~365. 해와 상관없이 같은 달·일은 같은 칸이 된다."""
    return date(2024, month, day).timetuple().tm_yday - 1


def all_days() -> list[tuple[int, int]]:
    return [(m, d) for m in range(1, 13) for d in range(1, calendar.monthrange(2024, m)[1] + 1)]


def compute_baselines(rows: list[dict], window: int) -> dict:
    """지점별·날짜별 '최근 N년 같은 날짜 ±window일' 평균.

    반환: {stn: {(월, 일): {"ta_avg": 14.1, "ta_avg_sd": 2.3, ..., "n": 150, "years": 10}}}
    _sd는 표준편차(오늘 값이 '매우 높음'인지 판정할 때 쓴다). 결측은 평균에서 뺀다. 연말·연초는 앞뒤 해를 넘어 이어진다(12/28 창에 1/3 포함).
    """
    sums = defaultdict(lambda: {v: [0.0] * DAYS for v in VARIABLES})
    squares = defaultdict(lambda: {v: [0.0] * DAYS for v in VARIABLES})
    counts = defaultdict(lambda: {v: [0] * DAYS for v in VARIABLES})
    years = defaultdict(set)
    for row in rows:
        i = day_index(int(row["date"][4:6]), int(row["date"][6:8]))
        for v in VARIABLES:
            if row[v] is not None:
                sums[row["stn"]][v][i] += row[v]
                squares[row["stn"]][v][i] += row[v] ** 2
                counts[row["stn"]][v][i] += 1
        if row["ta_avg"] is not None:
            years[row["stn"]].add(row["date"][:4])

    result = {}
    for stn in sums:
        result[stn] = {}
        for m, d in all_days():
            center = day_index(m, d)
            span = [(center + k) % DAYS for k in range(-window, window + 1)]
            entry = {}
            for v in VARIABLES:
                n = sum(counts[stn][v][i] for i in span)
                mean = sum(sums[stn][v][i] for i in span) / n if n else None
                var = sum(squares[stn][v][i] for i in span) / n - mean ** 2 if n else None
                entry[v] = round(mean, 1) if n else None
                entry[f"{v}_sd"] = round(max(var, 0.0) ** 0.5, 2) if n else None
            entry["n"] = sum(counts[stn]["ta_avg"][i] for i in span)
            entry["years"] = len(years[stn])
            result[stn][(m, d)] = entry
    return result


def monthly_summary(daily: dict) -> dict:
    """날짜별 기준값 → 월별 요약. 기온·습도·풍속은 평균, 강수량은 월 합계."""
    months = {}
    for m in range(1, 13):
        days = [entry for (month, _), entry in daily.items() if month == m]
        months[m] = {}
        for v in VARIABLES:
            values = [e[v] for e in days if e[v] is not None]
            if not values:
                months[m][v] = None
            elif v == "rn_day":
                months[m][v] = round(sum(values) / len(values) * len(days), 1)
            else:
                months[m][v] = round(sum(values) / len(values), 1)
    return months


def format_values(entry: dict, rain_label: str = "강수량") -> str:
    parts = []
    for v in VARIABLES:
        label, unit = LABELS[v]
        if v == "rn_day":
            label = rain_label
        parts.append(f"{label} {entry[v]}{unit}" if entry[v] is not None else f"{label} 자료 없음")
    return ", ".join(parts)


def station_text(stn: str, info: dict, months: dict, period: str) -> str:
    """항목 1건 = 지점 하나의 색인 텍스트. 위치·고도를 넣어야 '산간 지역' 같은 조건 검색에 걸린다. (F2001, F2011)"""
    terrain = "산지 관측소" if info["mountain"] else "관측소"
    lines = [f"{info['name']}({stn}) {terrain} · {info['address']} · 해발 {info['height']:.0f}m",
             f"최근 10년({period}) 월별 평균:"]
    lines += [f"{m}월: {format_values(months[m], '월강수량')}" for m in range(1, 13)]
    return "\n".join(lines)


if __name__ == "__main__":
    # 자체 점검: 창이 연말을 넘어 이어지는지, 결측을 빼고 평균하는지
    assert day_index(1, 1) == 0 and day_index(12, 31) == 365 and len(all_days()) == DAYS
    rows = [
        {"date": "20161231", "stn": "1", "ta_avg": 10.0, "ta_max": 1, "ta_min": 1, "hm_avg": 1, "ws_avg": 1, "rn_day": 0.0},
        {"date": "20170101", "stn": "1", "ta_avg": 20.0, "ta_max": 1, "ta_min": 1, "hm_avg": None, "ws_avg": 1, "rn_day": 4.0},
    ]
    b = compute_baselines(rows, window=1)["1"]
    assert b[(1, 1)]["ta_avg"] == 15.0 and b[(1, 1)]["n"] == 2 and b[(1, 1)]["years"] == 2
    assert b[(1, 1)]["hm_avg"] == 1.0  # 결측(None)은 빠진다
    assert b[(1, 1)]["ta_avg_sd"] == 5.0  # 10과 20의 표준편차
    assert office_for("11D10502") == "105" and office_for("11F20303") == "156" and office_for("11C20101") == "133"
    assert b[(6, 1)]["ta_avg"] is None and b[(6, 1)]["n"] == 0
    # 1월 중 값이 있는 날: 1/1 창(12/31 0mm, 1/1 4mm) = 2mm, 1/2 창(1/1 4mm) = 4mm → 평균 3mm × 31일
    assert monthly_summary(b)[1]["rn_day"] == 93.0
    print("stations.py 자체 점검 통과")
