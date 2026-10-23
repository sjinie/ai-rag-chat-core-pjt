"""정형 날씨 데이터(SQLite). 숫자는 임베딩하지 않고 날짜·지점으로 정확히 조회한다."""
import sqlite3

from config import DATA_DIR
from domain.stations import VARIABLES

DB_PATH = DATA_DIR / "weather.db"
SD = [f"{v}_sd" for v in VARIABLES]


def connect(path=DB_PATH) -> sqlite3.Connection:
    """테스트는 ':memory:'를 넘긴다. Streamlit은 화면을 다시 그리는 스레드가 달라 같은 연결을 여러 스레드에서 쓴다."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS obs_daily (
            stn TEXT, date TEXT, {", ".join(f"{v} REAL" for v in VARIABLES)},
            PRIMARY KEY (stn, date));
        CREATE TABLE IF NOT EXISTS baseline (
            stn TEXT, mmdd TEXT, {", ".join(f"{v} REAL" for v in VARIABLES + SD)}, n INTEGER, years INTEGER,
            PRIMARY KEY (stn, mmdd));
    """)
    return conn


def save_obs(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """같은 (지점, 날짜)는 덮어쓴다."""
    cols = ["stn", "date"] + VARIABLES
    conn.executemany(f"INSERT OR REPLACE INTO obs_daily ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                     [[r[c] for c in cols] for r in rows])
    conn.commit()


def save_baselines(conn: sqlite3.Connection, baselines: dict) -> None:
    cols = VARIABLES + SD + ["n", "years"]
    conn.executemany(
        f"INSERT OR REPLACE INTO baseline (stn, mmdd, {', '.join(cols)}) VALUES ({', '.join('?' * (len(cols) + 2))})",
        [[stn, f"{m:02d}{d:02d}"] + [e[c] for c in cols] for stn, daily in baselines.items() for (m, d), e in daily.items()])
    conn.commit()


def get_obs(conn: sqlite3.Connection, stn: str, dates: list[str]) -> list[dict]:
    """해당 지점의 날짜별 실제 관측값. 날짜는 YYYYMMDD."""
    rows = conn.execute(f"SELECT * FROM obs_daily WHERE stn = ? AND date IN ({', '.join('?' * len(dates))}) ORDER BY date",
                        [stn, *dates]).fetchall()
    return [dict(r) for r in rows]


def get_baseline(conn: sqlite3.Connection, stn: str, mmdd: str) -> dict | None:
    row = conn.execute("SELECT * FROM baseline WHERE stn = ? AND mmdd = ?", [stn, mmdd]).fetchone()
    return dict(row) if row else None
