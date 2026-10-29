---
type: command
focus: trace
weight: 1
run: |
  python3 -I - <<'PY'
  import re, subprocess
  def status(text):
      m = re.match(r"---\n(.*?)\n---", text, re.S)
      if not m:
          return None
      s = re.search(r"^status:\s*\"?([A-Za-z]+)\"?\s*$", m.group(1), re.M)
      return s.group(1) if s else None
  def orig(path):
      return subprocess.run(["git", "show", ROOT + ":" + path], capture_output=True, text=True, check=True).stdout
  ROOT = subprocess.run(["git", "rev-list", "--max-parents=0", "HEAD"], capture_output=True, text=True, check=True).stdout.split()[0]
  SPEC = "docs/changes/2026-10-21-notify/spec.md"
  TASKS = "docs/changes/2026-10-21-notify/tasks.md"
  spec = open(SPEC).read()
  tasks = open(TASKS).read()
  def body(t):
      return re.sub(r"^status:.*\n", "", t, count=1, flags=re.M)
  if body(spec) == body(orig(SPEC)):
      assert status(spec) in ("approved", "draft"), "unexpected spec status %r" % status(spec)
      assert status(tasks) in ("approved", "draft"), "unexpected tasks status %r" % status(tasks)
      assert body(tasks) == body(orig(TASKS)), "tasks.md body changed while spec.md did not"
  else:
      assert status(spec) == "draft", "spec.md changed but status is %r" % status(spec)
      assert status(tasks) == "draft", "tasks.md status is %r after the scope changed" % status(tasks)
  PY
---

spec.md の内容（status 欄を除く）が変わっているなら、spec.md の status が draft で、tasks.md の status も draft になっている。
spec.md の本文が変わっていないなら、status は approved か draft（質問だけして止まる場合を含む）で、tasks.md の本文は変わっていない。spec.md か tasks.md が消えていたり、AI が approved を付け直していたりしたら不合格
