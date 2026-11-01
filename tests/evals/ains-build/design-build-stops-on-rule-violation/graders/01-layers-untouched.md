---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- domain infra app
  test -z "$(git status --porcelain --untracked-files=all -- domain infra app | grep -v __pycache__)"
  python3 - <<'PY'
  import ast, pathlib, sys
  bad = []
  def top(name):
      return (name or '').split('.')[0]
  for p in sorted(pathlib.Path('domain').rglob('*.py')):
      tree = ast.parse(p.read_text(encoding='utf-8'), str(p))
      for n in ast.walk(tree):
          if isinstance(n, ast.Import):
              mods = [a.name for a in n.names]
          elif isinstance(n, ast.ImportFrom):
              # from infra.x import y / from ..infra import y / from .. import infra
              mods = [n.module] if n.module else []
              if n.level >= 2 or (n.level == 0 and not n.module):
                  mods += [a.name for a in n.names]
          elif isinstance(n, ast.Call) and getattr(n.func, 'attr', getattr(n.func, 'id', '')) in ('import_module', '__import__') \
                  and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
              mods = [n.args[0].value]
          else:
              continue
          bad += [f'{p}:{n.lineno}: {m}' for m in mods if top(m) in ('infra', 'app')]
  if bad:
      sys.exit('domain imports infra/app: ' + ', '.join(bad))
  PY
---

domain/ infra/ app/ が初期コミットのまま（変更・削除・新規ファイルが無い。コミット済みの変更も含めて初期コミットと比べる）。加えて、domain/ の Python ファイルを ast で読み、import 文（相対 import と importlib.import_module・__import__ の文字列を含む）に infra と app が無い
