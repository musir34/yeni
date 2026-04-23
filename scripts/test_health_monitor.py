"""Health monitor'ı lokal test et — kimse abone değilse mail atmaz, sadece loglar."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from stock_sync.health_monitor import run_all_checks


def main() -> int:
    with app.app_context():
        result = run_all_checks()
        print("\n=== HEALTH MONITOR SONUCU ===")
        for key, val in result.items():
            print(f"{key}: {val}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
