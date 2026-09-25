import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest


@pytest.fixture(autouse=True)
def _run_from_wb_root(monkeypatch):
    # Витринная копия: тесты и код используют пути относительно корня wb/
    # (app/config/..., app/prompts/...). Фикстура позволяет запускать их
    # из корня репозитория командой `python -m pytest`.
    monkeypatch.chdir(ROOT)
