import tomllib
import unittest
from pathlib import Path

STREAMLIT_CONFIG = Path(__file__).resolve().parents[1] / ".streamlit" / "config.toml"


class StreamlitConfigTest(unittest.TestCase):
    def test_error_details_hidden(self):
        # 코드의 try/except를 빠져나간 예외도 화면에 트레이스백을 보이지 않는다 (NF2004)
        with open(STREAMLIT_CONFIG, "rb") as f:
            self.assertIs(tomllib.load(f)["client"]["showErrorDetails"], False)


if __name__ == "__main__":
    unittest.main()
