"""Общий conftest витринной копии.

Делает wb/ и ozon/ импортируемыми из корня и подставляет заглушки переменных
окружения, без которых ozon_reviews_reply.py не импортируется (assert на уровне
модуля). Сеть в тестах не используется; заглушки никуда не отправляются.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for sub in ("wb", "ozon"):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

for key in ("OZON_CLIENT_ID", "OZON_API_KEY", "OPENAI_API_KEY"):
    os.environ.setdefault(key, "test-placeholder")
os.environ.setdefault("DRY_RUN", "1")

# Ручные скрипты проверки доступа названы test_*.py, но это не unit-тесты:
# при импорте они ходят в сеть. В сборку pytest не включаем.
collect_ignore = ["wb/test_wb_api.py", "wb/test_openai.py"]
