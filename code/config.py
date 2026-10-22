"""설정과 경로. config.toml(조정값)과 .env(키)를 읽는다."""
import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")

with open(Path(__file__).with_name("config.toml"), "rb") as f:
    CONFIG = tomllib.load(f)


def require_env(name: str) -> str:
    """키가 없으면 값 대신 이름만 알려 주고 멈춘다. (NF2003, NF2004)"""
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name}이(가) 없습니다. 프로젝트 루트의 .env를 확인하세요.")
    return value
