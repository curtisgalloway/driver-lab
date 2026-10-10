# SPDX-FileCopyrightText: 2026 contributors
# SPDX-License-Identifier: Apache-2.0
"""Seeded C comparison: every reported integer must agree with a real compiler."""

from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inventory


class InventoryDifferentialTests(unittest.TestCase):
    def test_random_whitelist_and_review_examples_against_c(self):
        compiler = next((path for name in ("cc", "gcc", "clang")
                         if (path := shutil.which(name))), None)
        if compiler is None:
            self.skipTest("inventory differential: no cc, gcc or clang on PATH")
        started = time.monotonic()
        rng = random.Random(0x5f27a3)

        def literal(value):
            digits = rng.choice((str(value), hex(value), "0" + format(value, "o")))
            return digits + rng.choice(("U", "UL", "ULL"))

        def expression(depth):
            if depth == 0 or rng.randrange(4) == 0:
                if rng.randrange(5) == 0:
                    return rng.choice(("KNOWN", "ENUM_SMALL"))
                return literal(rng.choice((rng.randrange(256), rng.getrandbits(32))))
            choice = rng.randrange(6)
            if choice == 0:
                return rng.choice(("+", "-", "~")) + "(" + expression(depth - 1) + ")"
            if choice == 1:
                return "BIT(" + str(rng.randrange(32)) + ")"
            if choice == 2:
                high = rng.randrange(32)
                return f"GENMASK({high}, {rng.randrange(high + 1)})"
            op = rng.choice(("+", "-", "*", "/", "%", "<<", ">>", "&", "|", "^"))
            right = (literal(rng.randrange(1, 256)) if op in ("/", "%") else
                     str(rng.randrange(32)) if op in ("<<", ">>") else expression(depth - 1))
            return f"({expression(depth - 1)} {op} {right})"

        expressions = [expression(rng.randrange(1, 5)) for _ in range(384)]
        headers = [f"#define RANDOM_{i} {expr}" for i, expr in enumerate(expressions)]
        outputs = [f'printf("%llu\\n", (unsigned long long)(RANDOM_{i}));'
                   for i in range(len(expressions))]
        review = ("#define COMMENT 1 /* a\nb */ + 2\n"
                  "#define PASTE 1 ## 2\n"
                  "#define WRAP ((0xffffffffU + 2U) >> 1)\n"
                  "enum { FIRST = sizeof(struct { int x; }), LAST = 7 };\n")
        review_names = ("COMMENT", "PASTE", "WRAP", "FIRST", "LAST")
        outputs.extend(f'printf("%llu\\n", (unsigned long long)({name}));'
                       for name in review_names)
        header = "#define KNOWN 17U\nenum { ENUM_SMALL = 17U };\n" + "\n".join(headers) + "\n" + review
        values, _ = inventory.extract(header)
        source = ('#include <stdio.h>\n'
                  '#define BIT(n) (1ULL << (n))\n'
                  '#define GENMASK(h,l) (((1ULL << ((h)-(l)+1))-1) << (l))\n'
                  + header + "\nint main(void) {\n" + "\n".join(outputs) + "\nreturn 0;\n}\n")
        with tempfile.TemporaryDirectory(prefix="inventory-c-diff-") as scratch:
            directory = Path(scratch)
            path, binary = directory / "expressions.c", directory / "expressions"
            path.write_text(source)
            compiled = subprocess.run([compiler, "-std=c11", "-w", str(path), "-o", str(binary)],
                                      capture_output=True, text=True, timeout=20)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 0, run.stderr)
        expected = [int(line) for line in run.stdout.splitlines()]
        names = [f"RANDOM_{i}" for i in range(len(expressions))] + list(review_names)
        self.assertEqual(len(expected), len(names))
        for name, number in zip(names, expected):
            with self.subTest(name=name):
                self.assertIn(name, values)
                self.assertTrue(values[name] is None or values[name] == number,
                                f"{name}: inventory {values[name]}, C {number}")
        self.assertEqual(expected[-5:-2], [3, 12, 0])
        self.assertEqual(values["COMMENT"], 3)
        self.assertTrue(all(values[name] is None for name in review_names[1:]))
        matches = sum(values[name] is not None for name in names)
        self.assertGreater(matches, 100, "differential must exercise numeric matches")
        self.assertLess(time.monotonic() - started, 30)
        print(f"inventory differential: 384 random expressions + 4 review inputs; "
              f"{len(names)} values checked, {matches} matches, {len(names) - matches} unknown")


if __name__ == "__main__":
    unittest.main()
