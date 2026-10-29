"""請求書番号の払い出し。番号は偶数なら A 窓口、奇数なら B 窓口へ回す。"""
from pathlib import Path

COUNTER = Path(__file__).resolve().parents[1] / ".invoice-counter"


def next_number() -> int:
    n = int(COUNTER.read_text()) if COUNTER.exists() else 0
    COUNTER.write_text(str(n + 1))
    return n


def queue_for(number: int) -> str:
    return "A" if number % 2 == 0 else "B"
