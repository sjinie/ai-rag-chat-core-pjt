"""ASOS 지점(항목)과 최근 10년 기준값 계산, 색인 텍스트 구성."""
import calendar
from collections import defaultdict
from datetime import date

# shortcut: 지점명·시/도는 수기 매핑. stn_inf.php 활용신청이 승인되면 API 응답으로 교체한다.
STATIONS = {
    "90": ("속초", "강원"), "93": ("북춘천", "강원"), "95": ("철원", "강원"), "98": ("동두천", "경기"),
    "99": ("파주", "경기"), "100": ("대관령", "강원"), "101": ("춘천", "강원"), "102": ("백령도", "인천"),
    "104": ("북강릉", "강원"), "105": ("강릉", "강원"), "106": ("동해", "강원"), "108": ("서울", "서울"),
    "112": ("인천", "인천"), "114": ("원주", "강원"), "115": ("울릉도", "경북"), "119": ("수원", "경기"),
    "121": ("영월", "강원"), "127": ("충주", "충북"), "129": ("서산", "충남"), "130": ("울진", "경북"),
    "131": ("청주", "충북"), "133": ("대전", "대전"), "135": ("추풍령", "충북"), "136": ("안동", "경북"),
    "137": ("상주", "경북"), "138": ("포항", "경북"), "140": ("군산", "전북"), "143": ("대구", "대구"),
    "146": ("전주", "전북"), "152": ("울산", "울산"), "155": ("창원", "경남"), "156": ("광주", "광주"),
    "159": ("부산", "부산"), "162": ("통영", "경남"), "165": ("목포", "전남"), "168": ("여수", "전남"),
    "169": ("흑산도", "전남"), "170": ("완도", "전남"), "172": ("고창", "전북"), "174": ("순천", "전남"),
    "177": ("홍성", "충남"), "181": ("서청주", "충북"), "184": ("제주", "제주"), "185": ("고산", "제주"),
    "188": ("성산", "제주"), "189": ("서귀포", "제주"), "192": ("진주", "경남"), "201": ("강화", "인천"),
    "202": ("양평", "경기"), "203": ("이천", "경기"), "211": ("인제", "강원"), "212": ("홍천", "강원"),
    "216": ("태백", "강원"), "217": ("정선군", "강원"), "221": ("제천", "충북"), "226": ("보은", "충북"),
    "232": ("천안", "충남"), "235": ("보령", "충남"), "236": ("부여", "충남"), "238": ("금산", "충남"),
    "239": ("세종", "세종"), "243": ("부안", "전북"), "244": ("임실", "전북"), "245": ("정읍", "전북"),
    "247": ("남원", "전북"), "248": ("장수", "전북"), "251": ("고창군", "전북"), "252": ("영광군", "전남"),
    "253": ("김해시", "경남"), "254": ("순창군", "전북"), "255": ("북창원", "경남"), "257": ("양산시", "경남"),
    "258": ("보성군", "전남"), "259": ("강진군", "전남"), "260": ("장흥", "전남"), "261": ("해남", "전남"),
    "262": ("고흥", "전남"), "263": ("의령군", "경남"), "264": ("함양군", "경남"), "266": ("광양시", "전남"),
    "268": ("진도군", "전남"), "271": ("봉화", "경북"), "272": ("영주", "경북"), "273": ("문경", "경북"),
    "276": ("청송군", "경북"), "277": ("영덕", "경북"), "278": ("의성", "경북"), "279": ("구미", "경북"),
    "281": ("영천", "경북"), "283": ("경주시", "경북"), "284": ("거창", "경남"), "285": ("합천", "경남"),
    "288": ("밀양", "경남"), "289": ("산청", "경남"), "294": ("거제", "경남"), "295": ("남해", "경남"),
    "296": ("북부산", "부산"),
}

VARIABLES = ["ta_avg", "ta_max", "ta_min", "hm_avg", "ws_avg", "rn_day"]
LABELS = {"ta_avg": ("평균기온", "℃"), "ta_max": ("최고기온", "℃"), "ta_min": ("최저기온", "℃"),
          "hm_avg": ("상대습도", "%"), "ws_avg": ("평균풍속", "m/s"), "rn_day": ("강수량", "mm")}
DAYS = 366  # 2월 29일을 포함한 날짜 칸 수


def day_index(month: int, day: int) -> int:
    """윤년 기준 0~365. 해와 상관없이 같은 달·일은 같은 칸이 된다."""
    return date(2024, month, day).timetuple().tm_yday - 1


def all_days() -> list[tuple[int, int]]:
    return [(m, d) for m in range(1, 13) for d in range(1, calendar.monthrange(2024, m)[1] + 1)]


def compute_baselines(rows: list[dict], window: int) -> dict:
    """지점별·날짜별 '최근 N년 같은 날짜 ±window일' 평균.

    반환: {stn: {(월, 일): {"ta_avg": 14.1, ..., "n": 150, "years": 10}}}
    결측은 평균에서 뺀다. 연말·연초는 앞뒤 해를 넘어 이어진다(12/28 창에 1/3 포함).
    """
    sums = defaultdict(lambda: {v: [0.0] * DAYS for v in VARIABLES})
    counts = defaultdict(lambda: {v: [0] * DAYS for v in VARIABLES})
    years = defaultdict(set)
    for row in rows:
        i = day_index(int(row["date"][4:6]), int(row["date"][6:8]))
        for v in VARIABLES:
            if row[v] is not None:
                sums[row["stn"]][v][i] += row[v]
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
                entry[v] = round(sum(sums[stn][v][i] for i in span) / n, 1) if n else None
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


def station_text(stn: str, months: dict, period: str) -> str:
    """항목 1건 = 지점 하나의 색인 텍스트. (F2001)"""
    name, sido = STATIONS[stn]
    lines = [f"{name}({stn}) 관측 지점 · {sido}", f"최근 10년({period}) 월별 평균:"]
    lines += [f"{m}월: {format_values(months[m], '월강수량')}" for m in range(1, 13)]
    return "\n".join(lines)


def baseline_text(stn: str, month: int, day: int, entry: dict, period: str, window: int) -> str:
    name, sido = STATIONS[stn]
    return (
        f"{name}({stn}, {sido}) {month}월 {day}일 최근 10년({period}, ±{window}일) 평균: "
        f"{format_values(entry, '일강수량')} (표본 {entry['n']}일, {entry['years']}개 연도)"
    )


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
    assert b[(6, 1)]["ta_avg"] is None and b[(6, 1)]["n"] == 0
    # 1월 중 값이 있는 날: 1/1 창(12/31 0mm, 1/1 4mm) = 2mm, 1/2 창(1/1 4mm) = 4mm → 평균 3mm × 31일
    assert monthly_summary(b)[1]["rn_day"] == 93.0
    print("stations.py 자체 점검 통과")
