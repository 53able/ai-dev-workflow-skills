"""Inert, finite terminal reconstruction for synthetic/source review only.

No I/O, process, key generation, resize, identity, secret classification or N7
admission. Callers supply actual ordered output bytes and monotonic read times.
Frames prove only this decoder's rendering of the retained raw prefix. They do
not authenticate a PID, UI, question, choice, or server/model delivery.

Profile: fixed <=200x400 grid; UTF-8 ASCII, box drawing (ambiguous width=1),
Japanese kana/CJK/fullwidth (width=2), <=4 U+0300..036F marks per base.
At most 8 million decode/render mutation and grid-allocation work units per
capture. Immutable frame snapshots separately copy at most 80,000 cells per
call; feed admits at most 4096 read receipts. Callers bound direct frame calls.
Other graphemes/emoji/variation selectors are deliberately unsupported. Unicode
version is part of parserVersion. Attributes are retained, not stripped. Unknown
controls, invalid UTF-8, unsupported modes, capture overflow and resize HOLD.
The first failure is sticky. Overflow retains only the preceding bounded prefix
and identifies the rejected chunk; it cannot claim complete raw capture.
"""
from dataclasses import dataclass, replace
import codecs
import hashlib
import json
import math
import unicodedata

PARSER_VERSION = 'n7-terminal-1/unicode-' + unicodedata.unidata_version


@dataclass(frozen=True)
class Style:
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    blink: bool = False
    inverse: bool = False
    hidden: bool = False
    strike: bool = False
    foreground: tuple = ()
    background: tuple = ()


@dataclass(frozen=True)
class Cell:
    text: str = ' '
    width: int = 1  # 0 is the continuation of a width-two cell
    style: Style = Style()


@dataclass(frozen=True)
class Receipt:
    start: int
    end: int
    read_start: float
    read_end: float
    chunk_sha256: str
    prefix_sha256: str
    chain_sha256: str


@dataclass(frozen=True)
class Frame:
    parserVersion: str
    rows: int
    columns: int
    cells: tuple
    cursor: tuple
    cursor_visible: bool
    alternate: bool
    raw_end: int
    raw_sha256: str
    chain_sha256: str
    read_end: object
    complete: bool
    reason: object
    query_intents: tuple

    @property
    def lines(self):
        return tuple(''.join(cell.text for cell in row) for row in self.cells)


class Terminal:
    """Caller-owned capture, bounded computation/storage; never writes a terminal.

    feed retains the *whole admitted chunk before decoding*, even on failure.
    Thus a failed frame can bind bytes after the offending character, but never
    claims that those bytes were rendered. Frame complete=False forbids proof.
    Query intents are observations only; no response/key bytes are generated.
    """
    def __init__(self, rows, columns, *, max_bytes=4 * 1024 * 1024,
                 max_receipts=4096):
        if (type(rows) is not int or type(columns) is not int or
                not 1 <= rows <= 200 or not 2 <= columns <= 400):
            raise ValueError('invalid fixed dimensions')
        if (type(max_bytes) is not int or not 1 <= max_bytes <= 4 * 1024 * 1024 or
                type(max_receipts) is not int or not 1 <= max_receipts <= 4096):
            raise ValueError('invalid capture bounds')
        self.rows, self.columns = rows, columns
        self.max_bytes, self.max_receipts = max_bytes, max_receipts
        self._raw = bytearray()
        self._receipts = []
        self._hash = hashlib.sha256()
        self._chain = '0' * 64
        self._last_time = None
        self._decode_offset = 0
        self.reason = None
        self.rejected_chunk = None
        self._utf = codecs.getincrementaldecoder('utf-8')('strict')
        self._state, self._sequence = 'text', ''
        self._style = Style()
        self._work_remaining = 8_000_000
        self._grid = self._blank_grid()
        self._primary = None
        self._saved = None
        self._x = self._y = 0
        self._top, self._bottom = 0, rows - 1
        self._wrap = True
        self._pending_wrap = False
        self._visible = True
        self._queries = []

    @property
    def raw(self):
        return bytes(self._raw)

    @property
    def receipts(self):
        return tuple(self._receipts)

    def _fail(self, reason):
        if self.reason is None:
            self.reason = reason

    def feed(self, data, *, read_start, read_end):
        if self.reason:
            return self.frame()
        if type(data) is not bytes:
            raise TypeError('output must be bytes')
        if (any(type(t) not in (int, float) or not 0 <= t <= 1e15 or not math.isfinite(t)
                for t in (read_start, read_end)) or read_end < read_start or
                (self._last_time is not None and read_start < self._last_time)):
            self._fail('nonmonotonic_read_interval')
            return self.frame()
        if len(self._raw) + len(data) > self.max_bytes or len(self._receipts) >= self.max_receipts:
            self.rejected_chunk = (len(data), hashlib.sha256(data).hexdigest())
            self._fail('capture_bound_exceeded')
            return self.frame()
        start = len(self._raw)
        self._raw.extend(data)
        self._hash.update(data)
        chunk_hash = hashlib.sha256(data).hexdigest()
        metadata = [start, len(self._raw), read_start, read_end, chunk_hash, self._hash.hexdigest()]
        self._chain = hashlib.sha256(bytes.fromhex(self._chain) +
                                    json.dumps(metadata, separators=(',', ':')).encode()).hexdigest()
        self._receipts.append(Receipt(*metadata, self._chain))
        self._last_time = read_end
        # Incremental one-byte decode keeps prefix semantics on invalid suffixes.
        for index, byte in enumerate(data):
            self._decode_offset = start + index + 1
            try:
                text = self._utf.decode(bytes([byte]))
            except UnicodeDecodeError:
                self._fail('invalid_utf8')
                break
            for char in text:
                self._consume(char)
                if self.reason:
                    break
            if self.reason:
                break
        return self.frame()

    def finish(self):
        """Declare actual EOF; partial escape/UTF-8 becomes a sticky failure."""
        if self._utf.getstate()[0] or self._state != 'text':
            self._fail('truncated_output')
        return self.frame()

    def resize(self, rows, columns):
        self._fail('resize_not_admitted')
        return self.frame()

    def frame(self):
        pending = self._state != 'text' or bool(self._utf.getstate()[0])
        reason = self.reason or ('incomplete_sequence' if pending else None)
        return Frame(PARSER_VERSION, self.rows, self.columns,
                     tuple(tuple(row) for row in self._grid), (self._y, self._x),
                     self._visible, self._primary is not None, len(self._raw),
                     self._hash.hexdigest(), self._chain, self._last_time,
                     reason is None, reason, tuple(self._queries))

    def _blank_grid(self):
        if not self._work(self.rows * self.columns):
            return None
        return [[Cell() for _ in range(self.columns)] for _ in range(self.rows)]

    def _work(self, count):
        self._work_remaining -= count
        if self._work_remaining < 0:
            self._fail('render_work_bound_exceeded')
            return False
        return True

    def _consume(self, char):
        if not self._work(1):
            return
        if self._state == 'esc':
            self._state = 'text'
            if char == '[':
                self._state, self._sequence = 'csi', ''
            elif char in '78':
                self._save() if char == '7' else self._restore()
            elif char in 'DEM':
                if char == 'E':
                    self._x = 0
                self._line(-1 if char == 'M' else 1)
            else:
                self._fail('unsupported_escape')
            return
        if self._state == 'csi':
            self._sequence += char
            if len(self._sequence) > 128:
                self._fail('sequence_bound_exceeded')
            elif '@' <= char <= '~':
                sequence = self._sequence
                self._state, self._sequence = 'text', ''
                self._csi(sequence[:-1], char)
            elif not ' ' <= char <= '?':
                self._fail('invalid_csi')
            return
        if char == '\x1b':
            self._state = 'esc'
        elif char == '\r':
            self._x, self._pending_wrap = 0, False
        elif char in '\n\x0b\x0c':
            self._line(1)
        elif char == '\b':
            self._x, self._pending_wrap = max(0, self._x - 1), False
        elif char == '\t':
            self._x, self._pending_wrap = min(self.columns - 1, (self._x // 8 + 1) * 8), False
        elif char == '\x07':
            pass  # BEL changes no cells; retained in raw.
        elif ord(char) < 32 or 0x7f <= ord(char) <= 0x9f:
            self._fail('unsupported_control')
        else:
            self._put(char)

    def _width(self, char):
        n = ord(char)
        if 0x300 <= n <= 0x36f and unicodedata.combining(char):
            return 0
        if unicodedata.category(char).startswith('M'):
            self._fail('unsupported_grapheme')
            return None
        if 0x20 <= n <= 0x7e or 0x2500 <= n <= 0x257f:
            return 1
        if (0x3000 <= n <= 0x30ff or 0x3400 <= n <= 0x9fff or
                0xff01 <= n <= 0xff60 or 0xffe0 <= n <= 0xffe6):
            if unicodedata.category(char)[0] != 'C' and unicodedata.east_asian_width(char) in ('W', 'F'):
                return 2
        self._fail('unsupported_grapheme')
        return None

    def _clear_cell(self, y, x):
        if not self._work(1):
            return
        row = self._grid[y]
        if row[x].width == 0 and x:
            row[x - 1] = Cell(style=self._style)
        elif row[x].width == 2 and x + 1 < self.columns:
            row[x + 1] = Cell(style=self._style)
        row[x] = Cell(style=self._style)

    def _put(self, char):
        width = self._width(char)
        if width is None:
            return
        if width == 0:
            x = self._x if self._pending_wrap else self._x - 1
            if x >= 0 and self._grid[self._y][x].width == 0:
                x -= 1
            if x < 0 or self._grid[self._y][x].text == ' ':
                self._fail('unattached_combining_mark')
                return
            cell = self._grid[self._y][x]
            if len(cell.text) >= 5:
                self._fail('combining_bound_exceeded')
                return
            self._grid[self._y][x] = replace(cell, text=cell.text + char)
            return
        if self._pending_wrap or self._x + width > self.columns:
            if not self._wrap:
                if width == 2:
                    self._fail('wide_character_at_margin')
                    return
            else:
                self._x = 0
                self._line(1)
        for x in range(self._x, self._x + width):
            self._clear_cell(self._y, x)
            if self.reason:
                return
        self._grid[self._y][self._x] = Cell(char, width, self._style)
        if width == 2:
            self._grid[self._y][self._x + 1] = Cell('', 0, self._style)
        self._pending_wrap = self._x + width == self.columns
        self._x = min(self.columns - 1, self._x + width)

    def _scroll(self, count):
        height = self._bottom - self._top + 1
        if abs(count) > height:
            self._fail('scroll_bound_exceeded')
            return
        if not self._work(height * self.columns):
            return
        region = self._grid[self._top:self._bottom + 1]
        blank = lambda: [Cell(style=self._style) for _ in range(self.columns)]
        if count > 0:
            region = region[count:] + [blank() for _ in range(count)]
        elif count < 0:
            region = [blank() for _ in range(-count)] + region[:count]
        self._grid[self._top:self._bottom + 1] = region

    def _line(self, direction):
        self._pending_wrap = False
        if direction == 1 and self._y == self._bottom:
            self._scroll(1)
        elif direction == -1 and self._y == self._top:
            self._scroll(-1)
        else:
            self._y = min(self.rows - 1, max(0, self._y + direction))

    def _save(self):
        self._saved = (self._y, self._x, self._style, self._pending_wrap)

    def _restore(self):
        if self._saved is None:
            self._fail('restore_without_save')
        else:
            self._y, self._x, self._style, self._pending_wrap = self._saved

    def _csi(self, body, final):
        private = body.startswith('?')
        body = body[1:] if private else body
        if body and any(c not in '0123456789;' for c in body):
            self._fail('unsupported_csi_parameters')
            return
        parts = body.split(';') if body else []
        if len(parts) > 32 or any(len(p) > 5 for p in parts):
            self._fail('parameter_bound_exceeded')
            return
        p = [int(s) if s else 0 for s in parts]
        n = (p[0] or 1) if p else 1
        if private:
            if final not in 'hl' or len(p) != 1 or p[0] not in (7, 25, 1049, 2004):
                self._fail('unsupported_private_mode')
            elif p[0] == 7:
                self._wrap = final == 'h'
            elif p[0] == 25:
                self._visible = final == 'h'
            elif p[0] == 1049:
                if final == 'h' and self._primary is None:
                    alternate = self._blank_grid()
                    if alternate is None:
                        return
                    self._primary = (self._grid, self._y, self._x, self._style,
                                     self._top, self._bottom, self._pending_wrap, self._saved)
                    self._grid = alternate
                    self._x = self._y = 0
                    self._top, self._bottom, self._pending_wrap = 0, self.rows - 1, False
                    self._saved = None
                elif final == 'l' and self._primary is not None:
                    (self._grid, self._y, self._x, self._style, self._top,
                     self._bottom, self._pending_wrap, self._saved) = self._primary
                    self._primary = None
                else:
                    self._fail('unpaired_alternate_screen')
            return  # bracketed paste mode has no output-grid effect
        if final == 'm':
            self._sgr(p or [0])
            return
        if final in 'Hf' and len(p) <= 2:
            self._y = min(self.rows - 1, max(0, (p[0] if p else 1) - 1))
            self._x = min(self.columns - 1, max(0, (p[1] if len(p) > 1 else 1) - 1))
        elif final in 'ABCDEFGd' and len(p) <= 1:
            if final in 'ABEF':
                self._y = min(self.rows - 1, max(0, self._y + (n if final in 'BE' else -n)))
            if final in 'CD':
                self._x = min(self.columns - 1, max(0, self._x + (n if final == 'C' else -n)))
            if final in 'EF':
                self._x = 0
            if final in 'Gd':
                if final == 'G':
                    self._x = min(self.columns - 1, n - 1)
                else:
                    self._y = min(self.rows - 1, n - 1)
        elif final in 'JK' and len(p) <= 1 and (p or [0])[0] in (0, 1, 2):
            mode = (p or [0])[0]
            origin = self._y * self.columns if final == 'K' else 0
            end = origin + self.columns if final == 'K' else self.rows * self.columns
            cursor = self._y * self.columns + self._x
            start = cursor if mode == 0 else origin
            end = cursor + 1 if mode == 1 else end
            for position in range(start, end):
                self._clear_cell(*divmod(position, self.columns))
                if self.reason:
                    return
        elif final in 'ST' and len(p) <= 1:
            self._scroll(n if final == 'S' else -n)
        elif final == 'r' and len(p) <= 2:
            top, bottom = (p[0] or 1) if p else 1, (p[1] or self.rows) if len(p) > 1 else self.rows
            if not 1 <= top < bottom <= self.rows:
                self._fail('invalid_scroll_region')
            else:
                self._top, self._bottom, self._x, self._y = top - 1, bottom - 1, 0, 0
        elif final in 'su' and not p:
            self._save() if final == 's' else self._restore()
            return
        elif final == 'n' and p == [6]:
            if len(self._queries) >= 64:
                self._fail('query_bound_exceeded')
            else:
                self._queries.append(('cursor_position', self._decode_offset, self._y, self._x))
            return
        else:
            self._fail('unsupported_csi')
        self._pending_wrap = False

    def _sgr(self, p):
        flags = {1: ('bold', True), 2: ('dim', True), 3: ('italic', True),
                 4: ('underline', True), 5: ('blink', True), 7: ('inverse', True),
                 8: ('hidden', True), 9: ('strike', True), 23: ('italic', False),
                 24: ('underline', False), 25: ('blink', False), 27: ('inverse', False),
                 28: ('hidden', False), 29: ('strike', False)}
        i = 0
        while i < len(p):
            code = p[i]
            if code == 0:
                self._style = Style()
            elif code == 22:
                self._style = replace(self._style, bold=False, dim=False)
            elif code in flags:
                key, value = flags[code]
                self._style = replace(self._style, **{key: value})
            elif code in (39, 49):
                self._style = replace(self._style, **{('foreground' if code == 39 else 'background'): ()})
            elif 30 <= code <= 37 or 40 <= code <= 47 or 90 <= code <= 97 or 100 <= code <= 107:
                fg = 30 <= code <= 37 or 90 <= code <= 97
                self._style = replace(self._style, **{('foreground' if fg else 'background'): ('ansi', code)})
            elif code in (38, 48):
                length = 2 if i + 1 < len(p) and p[i + 1] == 5 else 4
                args = p[i + 1:i + 1 + length]
                if (len(args) != length or args[0] not in (2, 5) or
                        any(v > 255 for v in args[1:])):
                    self._fail('unsupported_sgr_color')
                    return
                self._style = replace(self._style, **{('foreground' if code == 38 else 'background'): tuple(args)})
                i += length
            else:
                self._fail('unsupported_sgr')
                return
            i += 1
