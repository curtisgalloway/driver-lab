---
kind: soc
id: widgetsoc
name: Widget SoC
triggers: [widgetsoc]
cache: widget-resources
instances:
  - name: uart0
    ip: widgetuart
    reg: 0xfe201000
    irq: {kind: SPI, number: 121, intid: 153, trigger: level-high, note: shared}
    clocks: [uartclk]
    role: debug console
    note: "quoted: colon inside"
resources:
  repos: []
  docs: []
---

# Widget SoC

## Quick-facts

- **Addressing.** Flat. `[DT]` (`widgetsoc.dtsi`)
- **Timer.** 24 MHz. `[standard]`, `[hardware]`
- **Ordering.** Reset before clock. `[source-observed]` `TODO (verify on hardware)`: confirm the order.
- **GPU.** Widget-G1 per press. `[press]` `TODO (verify on hardware)`: the part number.

## Gotchas

- Enter at EL2. `[doc]` (Widget boot guide)
- **Grant bit.** Reads back set at power-on on the model; the databook's initial value is clear. `[databook]` (Widget TRM 4.2), `[emulated]` (widget-model 1.0, runs widget-q1-01 and widget-q1-02) `TODO (verify on hardware)`: read it after power-on.
- **Reset gap.** Leave at least 10 microseconds between the reset write and the next access. `[inference]` (premises: the databook asks for 1 microsecond `[databook]` (Widget TRM 5.1); gaps of 4 to 8 microseconds were observed `[emulated]` (widget-model 1.0, run widget-q1-01); a posted write cannot be timed, so add margin) `TODO (verify on hardware)`: measure the gap.
