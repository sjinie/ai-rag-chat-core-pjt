"""질문 처리 중 생기는 캐시(data/cache.db). 같은 일을 두 번 하지 않는다. (NF2002)

- selection: (지점, 오늘 개황 발표시각)별로 프롬프트2가 고른 유사 사례 ID
- queries  : (지점, 출처, 검색어)별로 이미 수집한 검색어
"""
import json
import sqlite3

from config import DATA_DIR


def connect_cache(path=DATA_DIR / "cache.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS selection (stn TEXT, tmfc TEXT, doc_ids TEXT, PRIMARY KEY (stn, tmfc));
        CREATE TABLE IF NOT EXISTS queries (stn TEXT, source TEXT, query TEXT, PRIMARY KEY (stn, source, query));
    """)
    return conn


def get_selection(conn: sqlite3.Connection, stn: str, tmfc: str) -> list[str] | None:
    """캐시가 없으면 None, '고른 것이 없음'이면 빈 목록."""
    row = conn.execute("SELECT doc_ids FROM selection WHERE stn = ? AND tmfc = ?", [stn, tmfc]).fetchone()
    return json.loads(row[0]) if row else None


def put_selection(conn: sqlite3.Connection, stn: str, tmfc: str, doc_ids: list[str]) -> None:
    conn.execute("INSERT OR REPLACE INTO selection VALUES (?, ?, ?)", [stn, tmfc, json.dumps(doc_ids)])
    conn.commit()


def seen_query(conn: sqlite3.Connection, stn: str, source: str, query: str) -> bool:
    return conn.execute("SELECT 1 FROM queries WHERE stn = ? AND source = ? AND query = ?",
                        [stn, source, query]).fetchone() is not None


def mark_query(conn: sqlite3.Connection, stn: str, source: str, query: str) -> None:
    conn.execute("INSERT OR IGNORE INTO queries VALUES (?, ?, ?)", [stn, source, query])
    conn.commit()
