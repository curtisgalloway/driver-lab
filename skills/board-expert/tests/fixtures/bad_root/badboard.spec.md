---
kind: board
id: badboard
name: Bad Board
triggers: [bad board]
parts: [missingsoc]
variant_of: nosuchbase
variants:
  - triggers: [nameless]
resources:
  series:
    - title: A series that claims authority
      url: https://example.com/series
      target: linux
      status: pending
      cite: true
      fetch: maybe
  docs:
    - title: Secret TRM
      url: https://intranet.example/trm
      access: internal
      via: skill:acme-board-tools
---

# Bad Board

## Quick-facts

- **Boot media.** An EEPROM with no tag.
- **Ordering.** Reset before clock. `[source-observed]`
- **GPU.** Per press. `[press]`
- **Console.** Per the guide. `[doc]`
- **Mid-prose tag.** The `[DT]` value is 5, and then more prose follows the tag.

## Gotchas

- Fine. `[DT]`
- **Receive hold.** Reception pauses for a second after a control write. `[emulated]` (widget-model 1.0, run widget-q1-01) `TODO (verify on hardware)`: time it on a board.
- **Ring drain.** The transmit ring drains with the link down. `[databook]` (Widget TRM 3), `[emulated]` (widget-model 1.0, run widget-q1-01)
- **Grant bit.** Reads back set. `[databook]` (Widget TRM 4.2), `[emulated]` `TODO (verify on hardware)`: read it on a board.
