"""Deterministic greedy pairwise generator with declared exclusions and conditional axes.

Standard library only. Terms used by every function here:
  axes     {axis: [value, ...]} in declaration order; order decides tie-breaks.
  exclude  [((axis, value), (axis, value)), ...] pairs that cannot occur in one row.
  when     {axis: (cond_axis, (value, ...))}: the axis is active only when cond_axis is
           active and has one of the values. cond_axis must be declared earlier.
           Inactive axes are absent from rows.
  rows     [{axis: value}]; partial rows are allowed (e.g. hand-mapped existing tests).
"""
from itertools import combinations


def check_spec(axes, exclude=(), when=None):
    order = list(axes)
    for axis, (cond, values) in (when or {}).items():
        if axis not in axes or cond not in axes or order.index(cond) >= order.index(axis):
            raise ValueError(f'when[{axis}]: condition axis {cond} must be declared before it')
        if not set(values) <= set(axes[cond]):
            raise ValueError(f'when[{axis}]: unknown values {set(values) - set(axes[cond])}')
    for pair in exclude:
        for a, v in pair:
            if v not in axes.get(a, ()):
                raise ValueError(f'exclude: unknown value {a}={v}')


def _active(axis, row, when):
    """Whether axis is active given the (already decided) earlier axes in row."""
    if axis not in when:
        return True
    cond, values = when[axis]
    return _active(cond, row, when) and row.get(cond) in values


def _ok(item, row, bad):
    return not any(frozenset((item, p)) in bad for p in row.items())


def _complete(row, axes, bad, when, order, i=0):
    """Depth-first completion of row over order[i:]; returns a full valid row or None."""
    for j in range(i, len(order)):
        axis = order[j]
        active = _active(axis, row, when)
        if axis in row:
            if not active:
                return None
            continue
        if not active:
            continue
        for v in axes[axis]:
            if _ok((axis, v), row, bad):
                got = _complete({**row, axis: v}, axes, bad, when, order, j + 1)
                if got is not None:
                    return got
        return None
    return row


def _valid(row, axes, bad, when):
    if any(not _ok(p, {a: v for a, v in row.items() if a != p[0]}, bad) for p in row.items()):
        return None
    return _complete(dict(row), axes, bad, when, list(axes))


def required_pairs(axes, exclude=(), when=None):
    """All value pairs that some valid full row can contain."""
    when, bad = when or {}, {frozenset(p) for p in exclude}
    return {frozenset(((a, x), (b, y)))
            for a, b in combinations(axes, 2) for x in axes[a] for y in axes[b]
            if _valid({a: x, b: y}, axes, bad, when) is not None}


def pairs_of(row):
    return {frozenset(p) for p in combinations(row.items(), 2)}


def generate(axes, exclude=(), when=None, covered=()):
    """Greedy rows covering every feasible pair and value that covered rows do not cover."""
    check_spec(axes, exclude, when)
    when, bad = when or {}, {frozenset(p) for p in exclude}
    order = list(axes)
    rank = {(a, v): (order.index(a), axes[a].index(v)) for a in order for v in axes[a]}
    todo = required_pairs(axes, exclude, when)
    for row in covered:
        todo -= pairs_of(row)
    seen = {p for row in covered for p in row.items()}
    singles = [(a, v) for a in order for v in axes[a] if (a, v) not in seen]
    rows = []
    while todo or singles:
        seed = dict(min(todo, key=lambda p: sorted(rank[i] for i in p))) if todo else dict(singles[:1])
        row = _fill(seed, axes, bad, when, order, todo)
        if row is None:
            raise ValueError(f'cannot complete a row for {seed}')
        rows.append(row)
        todo -= pairs_of(row)
        singles = [s for s in singles if row.get(s[0]) != s[1]]
    return rows


def _fill(seed, axes, bad, when, order, todo):
    """Assign axes in order, picking the value that covers the most open pairs (first wins ties)."""
    row = dict(seed)
    if _valid(row, axes, bad, when) is None:
        return None
    for axis in order:
        if axis in row or not _active(axis, row, when):
            continue
        best, best_gain = None, -1
        for v in axes[axis]:
            cand = {**row, axis: v}
            if not _ok((axis, v), row, bad) or _complete(cand, axes, bad, when, order) is None:
                continue
            gain = sum(frozenset(((axis, v), p)) in todo for p in row.items())
            if gain > best_gain:
                best, best_gain = v, gain
        if best is None:
            return None
        row[axis] = best
    return {a: row[a] for a in order if a in row}


def coverage(axes, exclude=(), when=None, generated=(), existing=()):
    """Counts plus the unused values and uncovered pairs (AC1 wants both empty)."""
    req = required_pairs(axes, exclude, when)
    by_existing = set().union(*map(pairs_of, existing)) & req
    by_generated = set().union(*map(pairs_of, generated)) & req
    used = {p for r in [*generated, *existing] for p in r.items()}
    total = sum(len(axes[a]) * len(axes[b]) for a, b in combinations(axes, 2))
    return {
        'values': sum(map(len, axes.values())),
        'unused_values': [f'{a}={v}' for a in axes for v in axes[a] if (a, v) not in used],
        'pairs_total': total,
        'pairs_excluded': total - len(req),
        'pairs_required': len(req),
        'pairs_by_existing': len(by_existing),
        'pairs_by_generated_only': len(by_generated - by_existing),
        'uncovered_pairs': sorted(' & '.join(f'{a}={v}' for a, v in sorted(p))
                                  for p in req - by_existing - by_generated),
    }
