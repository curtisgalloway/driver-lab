<!--
SPDX-FileCopyrightText: 2026 contributors
SPDX-License-Identifier: Apache-2.0
-->

# Worked example: the Widget UART against three target roots

Everything here is synthetic. `<skill>` is the `hardware-investigator` directory; `<scratch>` is
an empty directory you create; `<bx>` is `<skill>/../board-expert`. Run the commands as written
and compare. The expected facts files are under `examples/expected/`; write your own from the
sources first and compare after, so the example tests the method and not copying.

**Question:** what is the Widget UART's control register, and in what order does software bring
the block up?

**Fixture:**

- `board-expert` specs: `<bx>/tests/fixtures/good_root` (`widgetuart`, among others).
  `widgetuart` names one repository, `linux`, licensed `GPL-2.0-only`, file
  `drivers/tty/serial/widget.c`.
- Source trees (plain files; you make them git checkouts below): `examples/sources/widget-linux`
  (a Linux-like tree, `GPL-2.0-only`) and `examples/sources/widget-fw` (a firmware tree the caller
  offers, `MIT`; no board spec names it).
- Target roots: `examples/roots/gpl` (accepts `GPL-2.0-only` among others) and
  `examples/roots/permissive` (accepts `Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`).

## Setup

```
mkdir <scratch>/widget-linux <scratch>/widget-fw
cp -r <skill>/examples/sources/widget-linux/. <scratch>/widget-linux/
cp -r <skill>/examples/sources/widget-fw/. <scratch>/widget-fw/
git -C <scratch>/widget-linux init -q
git -C <scratch>/widget-linux add .
git -C <scratch>/widget-linux -c user.name=example -c user.email=example@example.com commit -q -m fixture
git -C <scratch>/widget-fw init -q
git -C <scratch>/widget-fw add .
git -C <scratch>/widget-fw -c user.name=example -c user.email=example@example.com commit -q -m fixture
```

## Run A: target root `examples/roots/gpl` (accepting)

Caller sources: `linux=<scratch>/widget-linux`.

1. Accepts list: `python3 <skill>/scripts/license_gate.py --root <skill>/examples/roots/gpl`
   prints the root, `license: GPL-2.0-only` and the accepts list, and exits 0.
2. Map: `board-expert` on `spec: widgetuart` over `<bx>/tests/fixtures/good_root` says the
   driver is `drivers/tty/serial/widget.c` in repository `linux`, stated license `GPL-2.0-only`,
   and that the databook order is "disable, program, enable; latch by writing LCR".
3. License of the file you will cite: `head -n 1 <scratch>/widget-linux/drivers/tty/serial/widget.c`
   prints `// SPDX-License-Identifier: GPL-2.0-only`.
4. Gate it: `python3 <skill>/scripts/license_gate.py --root <skill>/examples/roots/gpl GPL-2.0-only`
   prints `accepted: GPL-2.0-only` and exits 0.
5. Pin: `git -C <scratch>/widget-linux rev-parse HEAD`. Read `widget.c`, write the facts file
   (compare `examples/expected/answer-linux.md`, whose `@REV` stands for the commit).
6. Check:
   ```
   python3 <skill>/../peripheral-spec/scripts/anchor_check.py <scratch>/facts.md \
       --repo linux=<scratch>/widget-linux --root <skill>/examples/roots/gpl --require-license
   ```
   Expected: `result: PASS (0 errors, 0 warnings)`, exit 0.

## Run B: target root `examples/roots/permissive`, caller sources `linux=…` only (refusing)

1. Accepts list as in A: `Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause`.
2. Map and step 3 as in A: the file is `GPL-2.0-only`.
3. Gate it: `python3 <skill>/scripts/license_gate.py --root <skill>/examples/roots/permissive
   GPL-2.0-only` prints a `refused:` line naming the license, the root and its accepts list, and
   exits 1.
4. The only source that can answer the question is refused. **Stop.** Do not read `widget.c`
   beyond its license line, do not pin it and do not write a facts file. Return the *Refused*
   block from the skill, filled in. The correct answer here is that block and nothing about the
   register.

## Run C: target root `examples/roots/permissive`, caller sources `linux=…` and `fw=…`

1. As in B (including the license line of `widget.c`), `linux` is refused at its gate. Note the
   refusal for the report.
2. License of the offered tree: `head -n 1 <scratch>/widget-fw/uart/widget_uart_init.c` prints
   `/* SPDX-License-Identifier: MIT */`. Gate: `license_gate.py --root
   <skill>/examples/roots/permissive MIT` prints `accepted: MIT`, exit 0. This happens before you
   open the file for evidence.
3. Pin `fw`, read `uart/widget_uart_init.c`, write the facts file (compare
   `examples/expected/answer-fw.md`), then check:
   ```
   python3 <skill>/../peripheral-spec/scripts/anchor_check.py <scratch>/facts.md \
       --repo fw=<scratch>/widget-fw --root <skill>/examples/roots/permissive --require-license
   ```
   Expected: `result: PASS (0 errors, 0 warnings)`.
4. The report's *Sources* section lists `linux` as refused (GPL-2.0-only) and `fw` as accepted
   (MIT); the facts cite `fw` only.

## What a failing run looks like

If, in Run C, the facts file had cited `[src:linux: …]` with a `GPL-2.0-only` pin, step 3's
check would exit 1 with `license gate: … cites source pin 'linux' (GPL-2.0-only), which root …
does not accept`. That is the final backstop, not the method: the method refuses at the gate in
step 1, before the source is read.
