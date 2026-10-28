"""Real CPython cache regeneration and rejection tests; no model execution."""
import ast
import importlib.util
import marshal
from pathlib import Path
import py_compile
import struct
import sys
import tempfile
import unittest

import cache_payload_replay as replay
import postclosure_recovery as frozen


class CacheReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'sample.py'
        self.source = b'def value(x):\n    return x + 1\n'
        self.path.write_bytes(self.source)
        self.cache = Path(importlib.util.cache_from_source(str(self.path)))
        self.interpreter = dict(executable=frozen.ref(Path(sys.executable).resolve(), executable=True),
            version='3.14.6', cache_tag=sys.implementation.cache_tag,
            magic=importlib.util.MAGIC_NUMBER.hex(), marshal_version=marshal.version)
        self.profile = dict(source_path=str(self.path), cache_path=str(self.cache),
            mtime_ns=self.path.stat().st_mtime_ns, source_size=len(self.source),
            interpreter=self.interpreter, expected_interpreter=self.interpreter)

    def actual(self, mode=py_compile.PycInvalidationMode.TIMESTAMP):
        py_compile.compile(str(self.path), doraise=True, invalidation_mode=mode)
        return self.cache.read_bytes()

    def test_actual_compiler_cache_accepted_without_decoding(self):
        for mode in py_compile.PycInvalidationMode:
            with self.subTest(mode=mode):
                candidate = self.actual(mode)
                result = replay.validate_cache_replay(candidate, self.source, **self.profile)
                self.assertEqual(result['cache_sha256'], frozen.digest(candidate))
                self.assertFalse(result['business_PASS'])

    def test_reference_ownership_reproduces_original_false_negative(self):
        candidate = self.actual()
        with self.assertRaisesRegex(frozen.Hold, 'full code/source/filename/content'):
            frozen.validate_cache(candidate, self.source, **self.profile)
        replay.validate_cache_replay(candidate, self.source, **self.profile)

    def test_original_single_reference_encoding_also_accepted(self):
        code = compile(self.source, str(self.path), 'exec', dont_inherit=True, optimize=0)
        payload = marshal.dumps(code, marshal.version)
        candidate = self.actual()[:16] + payload
        replay.validate_cache_replay(candidate, self.source, **self.profile)

    def test_payload_truncation_append_and_mutation_rejected(self):
        candidate = self.actual()
        for changed in (candidate[:-1], candidate + b'\x00', candidate[:30] + bytes([candidate[30] ^ 1]) + candidate[31:]):
            with self.subTest(digest=frozen.digest(changed)), self.assertRaises(frozen.Hold):
                replay.validate_cache_replay(changed, self.source, **self.profile)

    def test_wrong_source_filename_magic_flags_and_timestamp_rejected(self):
        candidate = self.actual()
        wrong = compile(self.source, '/other/file.py', 'exec', dont_inherit=True, optimize=0)
        cases = [candidate[:16] + marshal.dumps(wrong, marshal.version),
                 b'xxxx' + candidate[4:], candidate[:4] + struct.pack('<I', 2) + candidate[8:],
                 candidate[:8] + b'\xff' * 8 + candidate[16:]]
        for changed in cases:
            with self.subTest(digest=frozen.digest(changed)), self.assertRaises(frozen.Hold):
                replay.validate_cache_replay(changed, self.source, **self.profile)
        with self.assertRaises(frozen.Hold):
            replay.validate_cache_replay(candidate, b'def value(x):\n    return x - 1\n', **self.profile)

    def test_inventory_guards_identical_except_payload_verifier(self):
        def function(module, name):
            tree = ast.parse(Path(module.__file__).read_text())
            return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        actual = function(replay, 'validate_derived_caches_replay')
        actual.name = 'validate_derived_caches'
        for node in ast.walk(actual):
            if isinstance(node, ast.Name) and node.id == 'validate_cache_replay':
                node.id = 'validate_cache'
        self.assertEqual(ast.dump(actual), ast.dump(function(frozen, 'validate_derived_caches')))


if __name__ == '__main__':
    unittest.main()
