"""ポイント残高。legacy_points は旧ポイント制度の残高で、新制度の points に移行済みのはず。"""


def balance(user: dict) -> int:
    return user.get("points", 0) + user.get("legacy_points", 0)
