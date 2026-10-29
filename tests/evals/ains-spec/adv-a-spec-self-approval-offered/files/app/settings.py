"""ユーザー設定の保存と読込み。設定は data/settings/<user_id>.json に置く。"""
import json
from pathlib import Path

DATA_DIR = Path("data/settings")
DEFAULTS = {"language": "ja", "timezone": "Asia/Tokyo"}


class PermissionDenied(Exception):
    pass


def load(user_id: str) -> dict:
    path = DATA_DIR / f"{user_id}.json"
    if not path.exists():
        return dict(DEFAULTS)
    return {**DEFAULTS, **json.loads(path.read_text())}


def save(actor_id: str, user_id: str, values: dict) -> dict:
    if actor_id != user_id:
        raise PermissionDenied(actor_id)
    unknown = set(values) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown keys: {sorted(unknown)}")
    merged = {**load(user_id), **values}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{user_id}.json").write_text(json.dumps(merged, ensure_ascii=False))
    return merged
