# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Every spec-format Python file compiles without warnings (an invalid escape is a
SyntaxWarning today and an error in a later Python)."""

from pathlib import Path
import unittest
import warnings

HERE = Path(__file__).resolve().parent


class CompilesCleanly(unittest.TestCase):
    def test_no_compile_warnings(self):
        files = sorted(HERE.glob('*.py')) + sorted((HERE.parent / 'scripts').glob('*.py'))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.name), warnings.catch_warnings():
                warnings.simplefilter('error')
                compile(path.read_text(encoding='utf-8'), str(path), 'exec')


if __name__ == '__main__':
    unittest.main()
