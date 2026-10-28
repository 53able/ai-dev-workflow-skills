"""Synthetic bytes only: no PTY, native binary, fixture or model execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

SPEC = importlib.util.spec_from_file_location('question_terminal', Path(__file__).with_name('question_terminal.py'))
t = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = t
SPEC.loader.exec_module(t)


class TerminalTests(unittest.TestCase):
    def feed(self, terminal, data):
        start = terminal.receipts[-1].read_end if terminal.receipts else 1.0
        return terminal.feed(data, read_start=start, read_end=start + 0.1)

    def test_prefix_receipts_independently_reproduce_chain(self):
        terminal = t.Terminal(3, 12)
        chunks = [b'abc', '\r\n日本'.encode(), b'\x1b[1;1H!']
        chain, raw = '0' * 64, b''
        previous = 0
        for chunk in chunks:
            frame = self.feed(terminal, chunk)
            receipt = terminal.receipts[-1]
            raw += chunk
            metadata = [previous, len(raw), receipt.read_start, receipt.read_end,
                        hashlib.sha256(chunk).hexdigest(), hashlib.sha256(raw).hexdigest()]
            chain = hashlib.sha256(bytes.fromhex(chain) + json.dumps(metadata, separators=(',', ':')).encode()).hexdigest()
            self.assertEqual(receipt.chain_sha256, chain)
            self.assertEqual(frame.raw_end, len(raw))
            self.assertEqual(frame.raw_sha256, hashlib.sha256(raw).hexdigest())
            previous = len(raw)
        self.assertEqual(terminal.raw, b''.join(chunks))
        self.assertEqual(frame.lines[:2], ('!bc         ', '日本        '))
        self.assertTrue(frame.complete)
        self.assertIn('unicode-', frame.parserVersion)

    def test_every_split_utf8_and_ansi_has_same_grid(self):
        payload = '┌─日本─┐\r\nA\u0301\x1b[2;7H\x1b[1;38;2;1;2;3mB\x1b[0m'.encode()
        expected = self.feed(t.Terminal(4, 14), payload)
        for split in range(len(payload) + 1):
            terminal = t.Terminal(4, 14)
            self.feed(terminal, payload[:split])
            actual = self.feed(terminal, payload[split:])
            self.assertTrue(actual.complete, (split, actual.reason))
            self.assertEqual(actual.cells, expected.cells)
            self.assertEqual(actual.cursor, expected.cursor)
        self.assertEqual(expected.cells[1][0].text, 'A\u0301')
        self.assertEqual(expected.cells[1][6].style.foreground, (2, 1, 2, 3))
        self.assertTrue(expected.cells[1][6].style.bold)

    def test_one_byte_chunks(self):
        terminal = t.Terminal(3, 10)
        for byte in '日本\x1b[2;1Hok'.encode():
            self.feed(terminal, bytes([byte]))
        self.assertEqual(terminal.frame().lines[:2], ('日本      ', 'ok        '))
        self.assertTrue(terminal.finish().complete)

    def test_wide_overwrite_and_erase_do_not_leave_half_cells(self):
        terminal = t.Terminal(2, 8)
        self.feed(terminal, '日本'.encode())
        frame = self.feed(terminal, b'\x1b[1;2HX')
        self.assertEqual(frame.cells[0][0].text, ' ')
        self.assertEqual(frame.cells[0][1].text, 'X')
        frame = self.feed(terminal, b'\x1b[1;4H\x1b[K')
        self.assertEqual(frame.lines[0], ' X      ')
        self.assertTrue(all(c.width == 1 for c in frame.cells[0]))

    def test_wrap_crlf_backspace_tab(self):
        terminal = t.Terminal(3, 10)
        frame = self.feed(terminal, b'abcdefghijK\b!\rX\tZ\r\nQ')
        self.assertEqual(frame.lines, ('abcdefghij', 'X       Z ', 'Q         '))
        self.assertEqual(frame.cursor, (2, 1))

    def test_cursor_moves_and_save_restore(self):
        terminal = t.Terminal(4, 12)
        frame = self.feed(terminal, b'\x1b[2;3H\x1b7\x1b[2B\x1b[3CX\x1b8Y\x1b[s\x1b[1GZ\x1b[u!')
        self.assertEqual(frame.lines[1], 'Z Y!        ')
        self.assertEqual(frame.cells[3][5].text, 'X')
        frame = self.feed(terminal, b'\x1b[1F\x1b[2C*\x1b[3d\x1b[2D#\x1b[1E?')
        self.assertTrue(frame.complete)
        self.assertEqual(frame.cells[0][2].text, '*')
        self.assertEqual(frame.cells[2][1].text, '#')
        self.assertEqual(frame.cells[3][0].text, '?')

    def test_erase_screen_modes(self):
        for command, expected in [(b'0J', ('abcd', 'e   ', '    ')),
                                  (b'1J', ('    ', '  gh', 'ijkl')),
                                  (b'2J', ('    ', '    ', '    '))]:
            terminal = t.Terminal(3, 4)
            self.feed(terminal, b'abcd\r\nefgh\r\nijkl\x1b[2;2H')
            self.assertEqual(self.feed(terminal, b'\x1b[' + command).lines, expected)

    def test_scroll_region_up_down_and_reverse_index(self):
        terminal = t.Terminal(4, 4)
        self.feed(terminal, b'1111\r\n2222\r\n3333\r\n4444')
        frame = self.feed(terminal, b'\x1b[2;3r\x1b[1S')
        self.assertEqual(frame.lines, ('1111', '3333', '    ', '4444'))
        frame = self.feed(terminal, b'\x1b[2;1H\x1bM')
        self.assertEqual(frame.lines, ('1111', '    ', '3333', '4444'))
        self.assertFalse(self.feed(terminal, b'\x1b[3T').complete)
        self.assertEqual(terminal.reason, 'scroll_bound_exceeded')

    def test_alternate_screen_restores_primary_and_attributes(self):
        terminal = t.Terminal(2, 10)
        self.feed(terminal, b'\x1b[7mprimary')
        frame = self.feed(terminal, b'\x1b[?1049h\x1b[2Jother')
        self.assertTrue(frame.alternate)
        self.assertTrue(frame.lines[0].startswith('other'))
        frame = self.feed(terminal, b'\x1b[?1049l!')
        self.assertFalse(frame.alternate)
        self.assertEqual(frame.lines[0], 'primary!  ')
        self.assertTrue(frame.cells[0][7].style.inverse)

    def test_sgr_reset_and_highlight_are_retained(self):
        terminal = t.Terminal(2, 8)
        frame = self.feed(terminal, b'\x1b[1;2;3;4;5;7;8;9;91;48;5;200mA\x1b[22;23;24;25;27;28;29;39;49mB\x1b[0mC')
        first = frame.cells[0][0].style
        self.assertTrue(first.bold and first.dim and first.inverse and first.hidden)
        self.assertEqual(first.background, (5, 200))
        self.assertEqual(frame.cells[0][1].style, t.Style())
        self.assertEqual(frame.cells[0][2].style, t.Style())

    def test_query_intents_do_not_generate_input(self):
        terminal = t.Terminal(2, 8)
        frame = self.feed(terminal, b'A\x1b[6n\x1b[?25l\x1b[?2004h')
        self.assertEqual(frame.query_intents, (('cursor_position', 5, 0, 1),))
        self.assertFalse(frame.cursor_visible)
        self.assertEqual(terminal.raw, b'A\x1b[6n\x1b[?25l\x1b[?2004h')

    def test_unknown_and_ambiguous_sequences_fail_closed_preserving_bytes(self):
        cases = [b'\x1b]0;title\x07', b'\x1b[?1000h', b'\x1b[1P', b'\x1b[4 q',
                 '😀'.encode(), '\u200d'.encode(), '\ufe0f'.encode(), 'é'.encode(),
                 b'\x00', b'\x9b', b'\xff', b'\x1b[999999A']
        for payload in cases:
            terminal = t.Terminal(3, 8)
            frame = self.feed(terminal, b'valid' + payload + b'untouched')
            self.assertFalse(frame.complete, payload)
            self.assertEqual(terminal.raw, b'valid' + payload + b'untouched')
            self.assertNotIn('untouched', ''.join(frame.lines))
            old = terminal.raw
            self.feed(terminal, b'late')
            self.assertEqual(terminal.raw, old)

    def test_incomplete_prefix_is_not_render_proof_and_eof_is_sticky(self):
        for payload in [b'\x1b[', b'\xe6\x97']:
            terminal = t.Terminal(2, 8)
            self.assertEqual(self.feed(terminal, payload).reason, 'incomplete_sequence')
            self.assertEqual(terminal.finish().reason, 'truncated_output')

    def test_capture_and_receipt_limits_keep_previous_prefix(self):
        for kwargs in [dict(max_bytes=3), dict(max_receipts=1)]:
            terminal = t.Terminal(2, 8, **kwargs)
            self.feed(terminal, b'abc')
            frame = self.feed(terminal, b'd')
            self.assertEqual(terminal.raw, b'abc')
            self.assertEqual(frame.reason, 'capture_bound_exceeded')
            self.assertEqual(terminal.rejected_chunk, (1, hashlib.sha256(b'd').hexdigest()))

    def test_time_resize_and_constructor_bounds(self):
        terminal = t.Terminal(2, 8)
        terminal.feed(b'a', read_start=2, read_end=3)
        self.assertEqual(terminal.feed(b'b', read_start=2.9, read_end=4).reason, 'nonmonotonic_read_interval')
        self.assertEqual(terminal.raw, b'a')
        self.assertEqual(t.Terminal(2, 8).resize(3, 8).reason, 'resize_not_admitted')
        for kwargs in [dict(rows=True, columns=8), dict(rows=201, columns=8),
                       dict(rows=2, columns=401), dict(rows=2, columns=8, max_bytes=0)]:
            with self.assertRaises(ValueError):
                t.Terminal(**kwargs)
        for value in [float('nan'), float('inf'), True, -1]:
            terminal = t.Terminal(2, 8)
            self.assertFalse(terminal.feed(b'a', read_start=value, read_end=3).complete)

    def test_combining_and_autowrap_limits(self):
        for payload, reason in [('\u0301', 'unattached_combining_mark'),
                                ('a' + '\u0301' * 5, 'combining_bound_exceeded')]:
            terminal = t.Terminal(2, 8)
            self.assertEqual(self.feed(terminal, payload.encode()).reason, reason)
        terminal = t.Terminal(2, 4)
        frame = self.feed(terminal, 'abc日本'.encode())
        self.assertEqual(frame.lines, ('abc ', '日本'))
        terminal = t.Terminal(2, 4)
        self.assertEqual(self.feed(terminal, b'\x1b[?7labcdZ').lines[0], 'abcZ')
        self.assertEqual(self.feed(terminal, '日'.encode()).reason, 'wide_character_at_margin')

    def test_render_work_budget_and_ideographic_space(self):
        terminal = t.Terminal(2, 8)
        frame = self.feed(terminal, '日　A'.encode())
        self.assertTrue(frame.complete)
        self.assertEqual(frame.cells[0][2].width, 2)
        # Repeated full clears consume a finite amount of grid work.
        terminal = t.Terminal(200, 400)
        frame = self.feed(terminal, b'\x1b[2J' * 101)
        self.assertEqual(frame.reason, 'render_work_bound_exceeded')
        self.assertEqual(terminal.raw, b'\x1b[2J' * 101)

    def test_synthetic_question_labels_are_only_grid_contents(self):
        terminal = t.Terminal(6, 40)
        frame = self.feed(terminal, b'Question 1\r\nOption A\r\nQuestion 2\r\nOption B\r\nQuestion 3\r\nOption C')
        self.assertTrue(frame.complete)
        self.assertEqual(len(frame.cells), 6)
        self.assertFalse(hasattr(frame, 'question_authenticated'))
        self.assertFalse(hasattr(frame, 'answer_delivered'))

    def test_review_out_of_profile_marks_fail_closed(self):
        for mark in ('\u3099', '\u309a', '\u302a'):
            with self.subTest(mark=mark):
                terminal = t.Terminal(2, 8)
                frame = self.feed(terminal, ('か' + mark + 'X').encode())
                self.assertFalse(frame.complete)
                self.assertEqual(frame.reason, 'unsupported_grapheme')

    def test_review_queries_and_saved_cursor_preserve_margin_wrap(self):
        for control in (b'\x1b[6n', b'\x1b[s\r\x1b[u', b'\x1b7\r\x1b8'):
            with self.subTest(control=control):
                terminal = t.Terminal(2, 4)
                frame = self.feed(terminal, b'abcd' + control + b'X')
                self.assertTrue(frame.complete)
                self.assertEqual(frame.lines, ('abcd', 'X   '))

    def test_review_alternate_grid_allocations_exhaust_work_budget(self):
        terminal = t.Terminal(200, 400)
        payload = (b'\x1b[?1049h\x1b[?1049l') * 101
        frame = self.feed(terminal, payload)
        self.assertEqual(frame.reason, 'render_work_bound_exceeded')
        self.assertEqual(terminal.raw, payload)

    def test_review_huge_timestamp_is_sticky_hold(self):
        for timestamp in (10**1000, -(10**1000)):
            with self.subTest(sign=timestamp > 0):
                terminal = t.Terminal(2, 4)
                frame = terminal.feed(b'A', read_start=timestamp, read_end=timestamp)
                self.assertFalse(frame.complete)
                self.assertEqual(frame.reason, 'nonmonotonic_read_interval')
                self.assertFalse(self.feed(terminal, b'B').complete)


if __name__ == '__main__':
    unittest.main()
