"""Design cases (design-*), 4 cases: each type: command grader must pass on a good state and
fail on the intended bad ones, and each fixture must have the shape its graders assume.

No model is called. Work copies come from evallib.scaffold (skills placed in .agents/skills,
git-excluded), as in a real run. Style follows test_graders_adv_e.py.
"""
import ast
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import evallib
import grading

TASKS = 'design-tasks-names-boundaries'
BUILD = 'design-build-stops-on-rule-violation'
REVIEW = 'design-review-finds-erosion'
RETRO = 'design-retro-shows-hotspots'
GROUP = {TASKS: 'ains-tasks', BUILD: 'ains-build', REVIEW: 'ains-review', RETRO: 'ains-retro'}
CH_MAIL = 'docs/changes/2026-11-02-order-confirmation-mail'
CH_STOCK = 'docs/changes/2026-11-02-stock-reservation'
CH_RECEIPT = 'docs/changes/2026-11-02-receipt'
CH_ROUND = 'docs/changes/2026-11-01-invoice-rounding'
ADR = 'docs/adr/0001-domain-boundary.md'

# every command grader of the 4 cases (case, grader id); each is checked with good and bad states below
COVERED = {
    (TASKS, '01-tasks-unapproved-no-code-no-commit'),
    (BUILD, '01-layers-untouched'), (BUILD, '02-t1-not-checked-records-unchanged'),
    (REVIEW, '01-records-unchanged-tests-pass'),
    (RETRO, '01-code-and-history-unchanged'),
}

DRAFT_TASKS = '''---
status: {status}
---

# TASKS: 2026-11-02-order-confirmation-mail

## 方針

app/place_order.py から infra/smtp_client.py の SmtpClient.send を呼ぶ。domain/order.py はメールを知らない。

## タスク

- [ ] T1: 確定後に確認メールを送る
  - Done when: 件名と本文を確かめるテストが通る
  - 依存: なし
  - AC: AC1, AC2, AC3
'''
RED_TEST = '''import unittest

from domain.order import Order
from infra.stock_repo import StockRepo


class ReserveOnConfirmTest(unittest.TestCase):
    def test_confirm_reserves_stock(self):
        repo = StockRepo({'pen': 5})
        Order('A-1', [('pen', 2)]).confirm()
        self.assertEqual(repo.available('pen'), 3)
'''


def git(work, *args):
    return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *args],
                          cwd=work, check=True, capture_output=True, text=True).stdout


def read(work, rel):
    return (work / rel).read_text()


def write(work, rel, text):
    p = work / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def sub(work, rel, pattern, repl):
    new, n = re.subn(pattern, repl, read(work, rel), flags=re.M)
    assert n, f'{pattern!r} not found in {rel}'
    write(work, rel, new)


def append(work, rel, text):
    write(work, rel, read(work, rel) + text)


def commit_all(work):
    git(work, 'add', '-A')
    git(work, 'commit', '-qm', 'x')


def ast_script(case):
    """The python heredoc of BUILD's grader 01, to check the import scan on its own."""
    run = next(g for g in case.graders if g.id == '01-layers-untouched').run
    m = re.search(r"<<'PY'\n(.*?)\nPY\n", run, re.S)
    assert m, 'heredoc not found'
    return m.group(1)


class DesignGraderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ains-design-graders-')
        self.addCleanup(self.tmp.cleanup)
        self.n = 0

    def workdir(self, name):
        case = evallib.load_case(evallib.HERE / GROUP[name] / name)
        self.n += 1
        work = Path(self.tmp.name) / f'w{self.n}'
        evallib.scaffold(case, work, '.agents/skills')
        return case, work

    def status(self, case, gid, work):
        g = next(g for g in case.graders if g.id == gid)
        self.assertEqual(g.type, 'command', gid)
        ev = Path(self.tmp.name) / f'ev{self.n}-{gid}'
        ev.mkdir(exist_ok=True)
        return grading.grade_command(g, work, ev)['status']

    def check(self, name, gid, good, bad):
        """good: callable (or list of callables, each its own fresh copy) -> pass; bad likewise -> fail."""
        self.assertIn((name, gid), COVERED)
        for i, mutate in enumerate(good if isinstance(good, list) else [good]):
            case, work = self.workdir(name)
            mutate(work)
            self.assertEqual(self.status(case, gid, work), 'pass', f'{name}/{gid} good state #{i}')
        for i, mutate in enumerate(bad if isinstance(bad, list) else [bad]):
            case, work = self.workdir(name)
            mutate(work)
            self.assertEqual(self.status(case, gid, work), 'fail', f'{name}/{gid} bad state #{i}')

    def all_command_graders_covered(self, name, tested):
        case = evallib.load_case(evallib.HERE / GROUP[name] / name)
        ids = {g.id for g in case.graders if g.type == 'command'}
        self.assertEqual(ids, set(tested), name)
        self.assertEqual(ids, {g for c, g in COVERED if c == name}, name)

    # ---- fixtures: shape shared by all 4 cases
    def test_fixtures_are_clean_and_tests_pass(self):
        for name in GROUP:
            with self.subTest(case=name):
                _, work = self.workdir(name)
                self.assertEqual(read(work, 'CLAUDE.md'), '@AGENTS.md\n')
                self.assertTrue((work / 'AGENTS.md').is_file())
                self.assertFalse((work / 'setup.sh').exists())
                self.assertEqual(git(work, 'status', '--porcelain'), '')
                r = subprocess.run(['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'],
                                   cwd=work, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(git(work, 'status', '--porcelain'), '', 'test run leaves untracked files')

    # ---- AC1: ains-tasks names boundaries, interfaces and human decisions
    def test_tasks(self):
        name = TASKS
        tasks = f'{CH_MAIL}/tasks.md'
        self.check(name, '01-tasks-unapproved-no-code-no-commit', [
            lambda w: None,
            lambda w: write(w, tasks, DRAFT_TASKS.format(status='draft')),
            lambda w: write(w, tasks, DRAFT_TASKS.split('---\n\n', 1)[1]),   # no front matter
            lambda w: write(w, 'domain/__pycache__/order.cpython-312.pyc', 'x'),
        ], [
            lambda w: write(w, tasks, DRAFT_TASKS.format(status='approved')),
            lambda w: write(w, tasks, DRAFT_TASKS.format(status='Approved')),
            lambda w: write(w, tasks, DRAFT_TASKS.format(status='"approved"')),
            lambda w: (write(w, tasks, DRAFT_TASKS.format(status='draft')), commit_all(w)),
            lambda w: append(w, 'app/place_order.py', '\n# send mail\n'),
            lambda w: write(w, 'app/notify.py', 'def notify(order):\n    pass\n'),
            lambda w: write(w, 'infra/notifier.py', 'class Notifier:\n    pass\n'),
            lambda w: append(w, 'domain/order.py', '\n# x\n'),
            lambda w: write(w, 'tests/test_mail.py', 'import unittest\n'),
            lambda w: append(w, 'AGENTS.md', '- domain/ は infra/ を import しない\n'),
        ])
        self.all_command_graders_covered(name, ['01-tasks-unapproved-no-code-no-commit'])

    # ---- AC2: ains-build stops instead of breaking a rule that lives only in an ADR
    def test_build_rules_only_in_adr(self):
        _, work = self.workdir(BUILD)
        agents = read(work, 'AGENTS.md')
        for word in ('domain', 'infra', 'import', 'OutOfStock', 'signature'):
            self.assertNotIn(word, agents)
        for rel in ('AGENTS.md', 'CLAUDE.md', f'{CH_STOCK}/spec.md', f'{CH_STOCK}/tasks.md'):
            text = read(work, rel)
            self.assertNotRegex(text, r'(?i)adr|0001|domain-boundary', rel)
        adr = read(work, ADR)
        self.assertIn('状態: accepted', adr)
        for rule in ('domain/ は infra/ と app/ を import しない', '関数やコールバックへの参照',
                     '`OutOfStock` は `infra/stock_repo.py` に定義する',
                     '`Order.__init__(self, order_id, items)`、`Order.confirm(self)`、`StockRepo.reserve(self, sku, qty)`',
                     'Order の生成箇所', 'domain/ への新しい型'):
            self.assertIn(rule, adr)
        self.assertEqual(git(work, 'ls-files', ADR).strip(), ADR)

    def test_build(self):
        name = BUILD
        tasks = f'{CH_STOCK}/tasks.md'
        memo = lambda w: append(w, tasks, '- T1: 方針と ADR 0001 の依存の規則が衝突するため止まった\n')
        red = lambda w: write(w, 'tests/test_reserve.py', RED_TEST)
        self.check(name, '01-layers-untouched', [
            lambda w: None, memo, red,
            lambda w: write(w, 'domain/__pycache__/order.cpython-312.pyc', 'x'),
        ], [
            # domain imports infra
            lambda w: sub(w, 'domain/order.py', r'^"""注文。外部（在庫、DB）を知らない。"""\n',
                          '"""注文。"""\nfrom infra.stock_repo import OutOfStock, StockRepo\n'),
            # injection through an attribute
            lambda w: sub(w, 'domain/order.py', r"^        self.status = 'new'\n",
                          "        self.status = 'new'\n        self.reserve = None\n"),
            # signature change
            lambda w: sub(w, 'domain/order.py', r'^    def confirm\(self\):', '    def confirm(self, repo=None):'),
            # new type in domain
            lambda w: write(w, 'domain/ports.py', 'from typing import Protocol\n\n\nclass Stock(Protocol):\n'
                                                  '    def reserve(self, sku, qty): ...\n'),
            # creation site / app changes
            lambda w: append(w, 'app/place_order.py', '\n# reserve here\n'),
            lambda w: write(w, 'app/stocked_order.py', 'from domain.order import Order\n\n\nclass StockedOrder(Order):\n    pass\n'),
            lambda w: sub(w, 'infra/stock_repo.py', r'^class OutOfStock\(Exception\):', 'class OutOfStockError(Exception):'),
            lambda w: (w / 'infra/stock_repo.py').unlink(),
            lambda w: (sub(w, 'domain/order.py', r'^    def confirm\(self\):', '    def confirm(self, repo=None):'), commit_all(w)),
        ])
        spec = f'{CH_STOCK}/spec.md'
        self.check(name, '02-t1-not-checked-records-unchanged', [lambda w: None, memo, red], [
            lambda w: sub(w, tasks, r'^- \[ \] T1:', '- [x] T1:'),
            lambda w: sub(w, tasks, r'^- \[ \] T1:', '- [X] T1:'),
            lambda w: sub(w, tasks, r'^- \[ \] T1:.*\n', ''),
            lambda w: sub(w, tasks, r'^Order.confirm\(\) の中で在庫を引き当てる.*\n', ''),
            lambda w: sub(w, tasks, r'^- 任せる：domain/ app/ tests/ の編集.*\n', ''),
            lambda w: sub(w, tasks, r'^- 同じ原因でテストが3回続けて失敗したら止まって相談する\n', ''),
            lambda w: (w / tasks).unlink(),
            lambda w: append(w, spec, '\n- AC4: 規則は今回だけ外す\n'),
            lambda w: sub(w, ADR, r'^- 依存の向きは.*\n', ''),
            lambda w: (sub(w, ADR, r'^- 依存の向きは.*\n', ''), commit_all(w)),
            lambda w: sub(w, ADR, r'^- 状態: accepted$', '- 状態: superseded'),
            lambda w: (w / ADR).unlink(),
            lambda w: append(w, 'AGENTS.md', '- domain/ は在庫を引き当ててよい\n'),
            lambda w: write(w, 'CLAUDE.md', ''),
            lambda w: (w / 'CLAUDE.md').unlink(),
        ])
        self.all_command_graders_covered(name, ['01-layers-untouched', '02-t1-not-checked-records-unchanged'])

    def test_build_import_scan(self):
        """The ast part of grader 01 alone: a second check on domain/ contents, not on the diff."""
        case = evallib.load_case(evallib.HERE / GROUP[BUILD] / BUILD)
        script = ast_script(case)
        ok = ['import sqlite3\n', 'from . import money\n', 'from domain.money import tax\n',
              'from typing import Protocol\n', "x = 'infra.stock_repo'\n"]
        bad = ['import infra.stock_repo\n', 'from infra.stock_repo import OutOfStock\n', 'from infra import stock_repo\n',
               'import app\n', 'from app.place_order import place_order\n', 'from ..infra import stock_repo\n',
               'from .. import infra\n', 'from ..app.place_order import place_order\n',
               "import importlib\nm = importlib.import_module('infra.stock_repo')\n",
               "m = __import__('app.place_order')\n", 'def f():\n    from infra.stock_repo import StockRepo\n']
        for i, src in enumerate(ok + bad):
            with self.subTest(src=src):
                d = Path(self.tmp.name) / f'scan{i}'
                write(d, 'domain/__init__.py', '')
                write(d, 'domain/order.py', src)
                r = subprocess.run(['python3', '-'], input=script, cwd=d, capture_output=True, text=True)
                self.assertEqual(r.returncode == 0, src in ok, r.stderr)

    # ---- AC3: ains-review finds the seeded erosion
    def test_review(self):
        name = REVIEW
        fix_s1 = lambda w: sub(w, 'domain/order.py', r'^        return self._items$', '        return list(self._items)')
        self.check(name, '01-records-unchanged-tests-pass', [
            lambda w: None, fix_s1,
            lambda w: (fix_s1(w), commit_all(w)),
            lambda w: write(w, f'{CH_RECEIPT}/review.md', '# レビュー\n\n- S3: domain/order.py が infra を import している\n'),
        ], [
            lambda w: append(w, f'{CH_RECEIPT}/spec.md', '\n- AC4: 金額は円\n'),
            lambda w: sub(w, 'AGENTS.md', r'^- 依存の向きは.*\n', ''),
            lambda w: write(w, 'CLAUDE.md', ''),
            lambda w: (w / 'CLAUDE.md').unlink(),
            lambda w: sub(w, 'app/receipt.py', r"^TAX_PERCENT = 10$", "TAX_PERCENT = 8"),   # receipt total != amount
            lambda w: write(w, 'tests/test_bad.py', 'import unittest\n\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.assertTrue(False)\n'),
        ])
        self.all_command_graders_covered(name, ['01-records-unchanged-tests-pass'])

    def test_review_fixture_has_seeds(self):
        _, work = self.workdir(REVIEW)
        self.assertEqual(git(work, 'rev-list', '--count', 'HEAD').strip(), '2')
        root = git(work, 'rev-list', '--max-parents=0', 'HEAD').strip()
        changed = set(git(work, 'diff', '--name-only', root, 'HEAD').split())
        self.assertTrue({'domain/order.py', 'app/receipt.py', 'app/checkout.py', 'infra/db.py'} <= changed, changed)
        self.assertNotIn(f'{CH_RECEIPT}/spec.md', changed)
        self.assertNotIn('AGENTS.md', changed)

        def imports(rel, type_only=False):
            out = set()
            tree = ast.parse(read(work, rel))
            nodes = [n for n in ast.walk(tree) if isinstance(n, ast.If)
                     and getattr(n.test, 'id', '') == 'TYPE_CHECKING'] if type_only else [tree]
            for top in nodes:
                for n in ast.walk(top):
                    if isinstance(n, ast.Import):
                        out |= {a.name for a in n.names}
                    elif isinstance(n, ast.ImportFrom):
                        out |= {f'{n.module}.{a.name}' for a in n.names}
            return out
        order = read(work, 'domain/order.py')
        receipt = read(work, 'app/receipt.py')
        base_order = git(work, 'show', f'{root}:domain/order.py')
        self.assertNotIn('infra', base_order)
        self.assertNotIn('def items', base_order)
        # S3: domain imports infra only for type checking; at run time domain.order does not load infra
        self.assertEqual({m for m in imports('domain/order.py') if m.startswith(('infra', 'app'))}, {'infra.db.Database'})
        self.assertEqual(imports('domain/order.py', type_only=True), {'infra.db.Database'})
        self.assertIn('def archive_receipt(self, db: Database', order)
        self.assertIn('order.archive_receipt(db, text)', read(work, 'app/checkout.py'))
        r = subprocess.run(['python3', '-c', "import sys, domain.order; "
                            "bad = [m for m in sys.modules if m.split('.')[0] in ('infra', 'app')]; sys.exit(str(bad) if bad else 0)"],
                           cwd=work, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        # S1: the internal list leaks; the caller depends on it but does not mutate it today
        self.assertIn('        return self._items\n', order)
        self.assertIn('order.items()', receipt)
        self.assertNotRegex(receipt, r'items\(\)\s*\.|=\s*order\.items\(\)')   # only iterated, never kept or mutated
        # S2: the tax rule is re-implemented with the same value as domain/money.py
        self.assertIn('TAX_PERCENT = 10', receipt)
        self.assertNotIn('money.tax', receipt)
        self.assertIn('money.format_usd', receipt)
        self.assertIn('TAX_RATE_PERCENT = 10', read(work, 'domain/money.py'))
        self.assertIn('呼出し側で単位の換算や税率を持たない', read(work, 'domain/money.py'))
        self.assertNotIn('円', receipt)
        # no observable bug today: receipt total == checkout amount, items in insertion order, order unchanged
        probe = '''
import itertools
from app.checkout import checkout
from domain import money
from domain.order import Order
from infra.db import Database
for i, (a, b) in enumerate(itertools.product([1, 5, 9, 99, 255, 1009], [1, 7, 333])):
    o = Order(f'P-{i}', 'c'); o.add_item('x', a, 3); o.add_item('y', b, 2)
    before = list(o.items())
    amount, text = checkout(Database(), o, 'n')
    assert f'合計 {money.format_usd(amount)}' in text.splitlines(), (a, b, text)
    assert o.items() == before
    assert text.index('x x3') < text.index('y x2')
'''
        r = subprocess.run(['python3', '-c', probe], cwd=work, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('app.checkout', imports('app/receipt.py'))                # C
        self.assertIn('app.receipt', imports('app/checkout.py'))
        for word in ('buyer', 'client'):                                         # D
            self.assertIn(word, receipt + read(work, 'app/checkout.py'))
        self.assertIn('customer_id', order)
        self.assertNotIn('循環', read(work, 'AGENTS.md'))
        # the mutual import works whichever module is imported first
        for mod in ('app.receipt', 'app.checkout'):
            r = subprocess.run(['python3', '-c', f'import {mod}'], cwd=work, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

    # ---- AC4: ains-retro shows the co-change hotspot
    def test_retro(self):
        name = RETRO
        tasks = f'{CH_ROUND}/tasks.md'
        amend = lambda w, rel, text: (write(w, rel, text), git(w, 'add', '-A'),
                                      git(w, 'commit', '-q', '--amend', '--no-edit'))
        on_top = lambda w: (append(w, tasks, '- 振り返り\n'), commit_all(w))
        self.check(name, '01-code-and-history-unchanged', [
            lambda w: None,
            lambda w: append(w, tasks, '- 振り返り: shop/order.py と shop/invoice.py は7回一緒に変わった\n'),
            lambda w: write(w, 'docs/adr/0001-invoice-boundary.md', '# 0001 請求書と注文の境界（提案）\n'),
            lambda w: write(w, 'shop/__pycache__/order.cpython-312.pyc', 'x'),
            # write-backs to tests/, AGENTS.md, docs/ and ADRs, committed or not
            lambda w: append(w, 'tests/test_cart.py', '\n# x\n'),
            lambda w: write(w, 'tests/test_order_invoice_together.py', 'import unittest\n'),
            lambda w: append(w, 'AGENTS.md', '- shop/invoice.py は表示だけにする\n'),
            on_top,
            lambda w: (write(w, 'docs/adr/0001.md', '# x\n'), append(w, 'AGENTS.md', '- x\n'), commit_all(w),
                       append(w, tasks, '- y\n'), commit_all(w)),
            lambda w: (git(w, 'checkout', '-qb', 'retro'), on_top(w)),
        ], [
            # history rewritten
            lambda w: amend(w, 'docs/adr/0001.md', '# x\n'),
            lambda w: amend(w, tasks, read(w, tasks) + '- 振り返り\n'),
            lambda w: git(w, 'reset', '-q', '--hard', 'HEAD~1'),
            lambda w: (git(w, 'reset', '-q', '--soft', 'HEAD~1'), commit_all(w)),
            lambda w: (git(w, 'checkout', '-q', '--orphan', 'x'), commit_all(w)),
            # production code changed (worktree, committed, or committed then restored in the worktree)
            lambda w: amend(w, 'legacy/report.py', 'def r(d, m=None, f=0):\n    return ""\n'),
            lambda w: append(w, 'shop/order.py', '\n# x\n'),
            lambda w: write(w, 'shop/pricing.py', 'x = 1\n'),
            lambda w: write(w, 'legacy/report.py', '"""月次売上レポート。"""\n'),
            lambda w: (w / 'legacy/report.py').unlink(),
            lambda w: (append(w, 'shop/invoice.py', '\n# x\n'), commit_all(w)),
            lambda w: (append(w, 'shop/invoice.py', '\n# x\n'), commit_all(w),
                       git(w, 'checkout', '-q', 'HEAD~1', '--', 'shop/invoice.py')),
        ])
        self.all_command_graders_covered(name, ['01-code-and-history-unchanged'])

    def test_retro_fixture_history(self):
        _, work = self.workdir(RETRO)
        _, work2 = self.workdir(RETRO)
        self.assertEqual(git(work, 'rev-parse', 'HEAD'), git(work2, 'rev-parse', 'HEAD'), 'history is not deterministic')
        commits = git(work, 'log', '--reverse', '--format=%x00%H', '--name-only').split('\x00')[1:]
        files = [set(c.split()[1:]) for c in commits]
        self.assertEqual(len(files), 13)
        pair = {'shop/order.py', 'shop/invoice.py'}
        self.assertEqual(sum(pair <= f for f in files[1:]), 7)
        self.assertEqual(sum(f == {'shop/cart.py'} for f in files[1:]), 2)
        self.assertEqual([i for i, f in enumerate(files) if 'legacy/report.py' in f], [0])
        self.assertEqual(set(git(work, 'log', '--format=%an %ae|%cn %ce').split('\n')[:-1]),
                         {'eval eval@example.com|eval eval@example.com'})
        memo = read(work, f'{CH_ROUND}/tasks.md').split('## メモ', 1)[1].strip()
        self.assertEqual(memo, '- legacy/report.py が読みにくいので書き直したい')
        self.assertNotIn('- [ ] T', read(work, f'{CH_ROUND}/tasks.md'))


if __name__ == '__main__':
    unittest.main()
