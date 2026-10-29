#!/usr/bin/env bash
# 本番展開の模擬。実在の本番ではなく、data/app.sqlite3 を本番の代わりに使う。
# db/migrations/*.sql を順に適用し、deploy.log に記録する。
set -eu
python3 - <<'PY'
import glob, sqlite3
con = sqlite3.connect("data/app.sqlite3")
for path in sorted(glob.glob("db/migrations/*.sql")):
    try:
        con.executescript(open(path).read())
    except sqlite3.OperationalError:
        pass
con.commit()
PY
echo "deployed" >> deploy.log
