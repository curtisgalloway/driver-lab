// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0
//! Evaluation prelude: a register-bus trait, a recording mock, and the `SpecGap` type an
//! answer returns when the spec does not say. Prepended to items that set `use_hw_prelude`.

use std::collections::{BTreeMap, VecDeque};

/// Returned (as the error) when the spec does not give the answer.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SpecGap(pub &'static str);

/// One recorded bus operation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum BusOp {
    Read8(u64),
    Write8(u64, u8),
    Read16(u64),
    Write16(u64, u16),
    Read32(u64),
    Write32(u64, u32),
    Read64(u64),
    Write64(u64, u64),
    DelayUs(u32),
}

/// Register access by byte offset, at four widths, plus a delay.
pub trait RegBus {
    fn read8(&mut self, off: u64) -> u8;
    fn write8(&mut self, off: u64, v: u8);
    fn read16(&mut self, off: u64) -> u16;
    fn write16(&mut self, off: u64, v: u16);
    fn read32(&mut self, off: u64) -> u32;
    fn write32(&mut self, off: u64, v: u32);
    fn read64(&mut self, off: u64) -> u64;
    fn write64(&mut self, off: u64, v: u64);
    fn delay_us(&mut self, us: u32);
}

/// A register file with scripted reads and a log of every operation.
#[derive(Debug, Clone, Default)]
pub struct MockBus {
    /// Stored value per offset (zero-extended).
    pub regs: BTreeMap<u64, u64>,
    /// Scripted read values per offset; a read pops the front while the queue is non-empty.
    pub queues: BTreeMap<u64, VecDeque<u64>>,
    /// Every operation, in order.
    pub ops: Vec<BusOp>,
}

impl MockBus {
    pub fn new() -> Self {
        Self::default()
    }

    fn read_raw(&mut self, off: u64) -> u64 {
        if let Some(q) = self.queues.get_mut(&off) {
            if let Some(v) = q.pop_front() {
                return v;
            }
        }
        self.regs.get(&off).copied().unwrap_or(0)
    }

    pub fn delays_us(&self) -> Vec<u32> {
        self.ops
            .iter()
            .filter_map(|op| match op {
                BusOp::DelayUs(us) => Some(*us),
                _ => None,
            })
            .collect()
    }

    pub fn total_delay_us(&self) -> u64 {
        self.delays_us().iter().map(|&us| us as u64).sum()
    }

    pub fn last_write32(&self, off: u64) -> Option<u32> {
        self.writes32_to(off).last().copied()
    }

    pub fn with_reg8(mut self, off: u64, v: u8) -> Self {
        self.set_reg8(off, v);
        self
    }

    pub fn set_reg8(&mut self, off: u64, v: u8) {
        self.regs.insert(off, v as u64);
    }

    pub fn get_reg8(&self, off: u64) -> u8 {
        self.regs.get(&off).copied().unwrap_or(0) as u8
    }

    pub fn queue_reads8(&mut self, off: u64, vals: &[u8]) {
        let q = self.queues.entry(off).or_default();
        q.extend(vals.iter().map(|&v| v as u64));
    }

    pub fn writes8_to(&self, off: u64) -> Vec<u8> {
        self.ops
            .iter()
            .filter_map(|op| match op {
                BusOp::Write8(o, v) if *o == off => Some(*v),
                _ => None,
            })
            .collect()
    }

    pub fn with_reg16(mut self, off: u64, v: u16) -> Self {
        self.set_reg16(off, v);
        self
    }

    pub fn set_reg16(&mut self, off: u64, v: u16) {
        self.regs.insert(off, v as u64);
    }

    pub fn get_reg16(&self, off: u64) -> u16 {
        self.regs.get(&off).copied().unwrap_or(0) as u16
    }

    pub fn queue_reads16(&mut self, off: u64, vals: &[u16]) {
        let q = self.queues.entry(off).or_default();
        q.extend(vals.iter().map(|&v| v as u64));
    }

    pub fn writes16_to(&self, off: u64) -> Vec<u16> {
        self.ops
            .iter()
            .filter_map(|op| match op {
                BusOp::Write16(o, v) if *o == off => Some(*v),
                _ => None,
            })
            .collect()
    }

    pub fn with_reg32(mut self, off: u64, v: u32) -> Self {
        self.set_reg32(off, v);
        self
    }

    pub fn set_reg32(&mut self, off: u64, v: u32) {
        self.regs.insert(off, v as u64);
    }

    pub fn get_reg32(&self, off: u64) -> u32 {
        self.regs.get(&off).copied().unwrap_or(0) as u32
    }

    pub fn queue_reads32(&mut self, off: u64, vals: &[u32]) {
        let q = self.queues.entry(off).or_default();
        q.extend(vals.iter().map(|&v| v as u64));
    }

    pub fn writes32_to(&self, off: u64) -> Vec<u32> {
        self.ops
            .iter()
            .filter_map(|op| match op {
                BusOp::Write32(o, v) if *o == off => Some(*v),
                _ => None,
            })
            .collect()
    }

    pub fn with_reg64(mut self, off: u64, v: u64) -> Self {
        self.set_reg64(off, v);
        self
    }

    pub fn set_reg64(&mut self, off: u64, v: u64) {
        self.regs.insert(off, v as u64);
    }

    pub fn get_reg64(&self, off: u64) -> u64 {
        self.regs.get(&off).copied().unwrap_or(0) as u64
    }

    pub fn queue_reads64(&mut self, off: u64, vals: &[u64]) {
        let q = self.queues.entry(off).or_default();
        q.extend(vals.iter().map(|&v| v as u64));
    }

    pub fn writes64_to(&self, off: u64) -> Vec<u64> {
        self.ops
            .iter()
            .filter_map(|op| match op {
                BusOp::Write64(o, v) if *o == off => Some(*v),
                _ => None,
            })
            .collect()
    }
}

impl RegBus for MockBus {
    fn read8(&mut self, off: u64) -> u8 {
        let v = self.read_raw(off) as u8;
        self.ops.push(BusOp::Read8(off));
        v
    }

    fn write8(&mut self, off: u64, v: u8) {
        self.regs.insert(off, v as u64);
        self.ops.push(BusOp::Write8(off, v));
    }

    fn read16(&mut self, off: u64) -> u16 {
        let v = self.read_raw(off) as u16;
        self.ops.push(BusOp::Read16(off));
        v
    }

    fn write16(&mut self, off: u64, v: u16) {
        self.regs.insert(off, v as u64);
        self.ops.push(BusOp::Write16(off, v));
    }

    fn read32(&mut self, off: u64) -> u32 {
        let v = self.read_raw(off) as u32;
        self.ops.push(BusOp::Read32(off));
        v
    }

    fn write32(&mut self, off: u64, v: u32) {
        self.regs.insert(off, v as u64);
        self.ops.push(BusOp::Write32(off, v));
    }

    fn read64(&mut self, off: u64) -> u64 {
        let v = self.read_raw(off) as u64;
        self.ops.push(BusOp::Read64(off));
        v
    }

    fn write64(&mut self, off: u64, v: u64) {
        self.regs.insert(off, v as u64);
        self.ops.push(BusOp::Write64(off, v));
    }

    fn delay_us(&mut self, us: u32) {
        self.ops.push(BusOp::DelayUs(us));
    }
}

// ---- end of prelude: test module below is not prepended ----
#[cfg(test)]
mod prelude_tests {
    use super::*;

    // Invented device: all offsets and bit positions below are made up.
    const STATUS: u64 = 0x10;
    const ST_DONE: u32 = 1 << 0;
    const ST_ERR: u32 = 1 << 1;

    fn clear_done<B: RegBus>(bus: &mut B) {
        // Write-1-to-clear: write only the bit to clear, never read-modify-write.
        bus.write32(STATUS, ST_DONE);
    }

    #[test]
    fn w1c_rmw() {
        let mut bus = MockBus::new().with_reg32(STATUS, ST_DONE | ST_ERR);
        clear_done(&mut bus);
        assert_eq!(bus.writes32_to(STATUS), vec![ST_DONE]);
        assert_eq!(bus.last_write32(STATUS).unwrap() & ST_ERR, 0);
    }

    const CTRL: u64 = 0x00;
    const CTRL_RESET: u32 = 1 << 31;
    const BUSY_REG: u64 = 0x04;
    const BUSY: u32 = 1 << 0;

    fn reset<B: RegBus>(bus: &mut B) -> bool {
        bus.write32(CTRL, CTRL_RESET);
        bus.delay_us(5);
        for _ in 0..10 {
            if bus.read32(BUSY_REG) & BUSY == 0 {
                return true;
            }
        }
        false
    }

    #[test]
    fn ordered_sequence() {
        let mut bus = MockBus::new();
        bus.queue_reads32(BUSY_REG, &[BUSY, BUSY, 0]);
        assert!(reset(&mut bus));
        assert_eq!(
            bus.ops,
            vec![
                BusOp::Write32(CTRL, CTRL_RESET),
                BusOp::DelayUs(5),
                BusOp::Read32(BUSY_REG),
                BusOp::Read32(BUSY_REG),
                BusOp::Read32(BUSY_REG),
            ]
        );
        assert_eq!(bus.total_delay_us(), 5);
    }

    const VERSION: u64 = 0x20;
    const VER_HAS_DMA: u32 = 1 << 8;
    const DMA_EN: u64 = 0x24;

    fn enable_dma<B: RegBus>(bus: &mut B) -> Result<(), SpecGap> {
        if bus.read32(VERSION) & VER_HAS_DMA == 0 {
            return Err(SpecGap("no DMA on this revision"));
        }
        bus.write32(DMA_EN, 1);
        Ok(())
    }

    #[test]
    fn capability_gating() {
        let mut absent = MockBus::new().with_reg32(VERSION, 0x0001);
        assert_eq!(enable_dma(&mut absent), Err(SpecGap("no DMA on this revision")));
        assert!(absent.writes32_to(DMA_EN).is_empty());
        let mut present = MockBus::new().with_reg32(VERSION, 0x0101);
        assert_eq!(enable_dma(&mut present), Ok(()));
        assert_eq!(present.writes32_to(DMA_EN), vec![1]);
    }

    // Descriptor word: length in bits 0..=11, channel in 12..=15, flags in 16..=31.
    fn pack_desc(len: u32, chan: u32, flags: u32) -> u32 {
        (len & 0xfff) | ((chan & 0xf) << 12) | ((flags & 0xffff) << 16)
    }

    fn unpack_desc(w: u32) -> (u32, u32, u32) {
        (w & 0xfff, (w >> 12) & 0xf, w >> 16)
    }

    #[test]
    fn bitfield_codec() {
        let w = pack_desc(0x123, 0x5, 0xabcd);
        assert_eq!(w, 0xabcd_5123);
        assert_eq!(unpack_desc(w), (0x123, 0x5, 0xabcd));
        assert_eq!(unpack_desc(pack_desc(0xfff, 0xf, 0xffff)), (0xfff, 0xf, 0xffff));
    }

    // Divider rounded to nearest: the invented block runs at src / (2 * (div + 1)).
    fn divider(src_hz: u32, target_hz: u32) -> u32 {
        let d = (src_hz + target_hz) / (2 * target_hz);
        d.saturating_sub(1)
    }

    fn timeout_ticks(us: u32, clk_hz: u32) -> u32 {
        ((us as u64 * clk_hz as u64 + 999_999) / 1_000_000) as u32
    }

    #[test]
    fn hardware_math() {
        assert_eq!(divider(100_000_000, 400_000), 124);
        assert_eq!(divider(100_000_000, 3_000_000), 16);
        assert_eq!(timeout_ticks(1500, 1_000_000), 1500);
        assert_eq!(timeout_ticks(1, 1_500_000), 2);
    }

    #[test]
    fn mockbus_semantics() {
        let mut bus = MockBus::new()
            .with_reg8(0x10, 0xab)
            .with_reg16(0x20, 0xbeef)
            .with_reg32(0x00, 0x1234_5678)
            .with_reg64(0x30, 0x0123_4567_89ab_cdef);
        // Reads truncate the stored value to the access width; an absent offset reads 0.
        assert_eq!(bus.read8(0x00), 0x78);
        assert_eq!(bus.read16(0x00), 0x5678);
        assert_eq!(bus.read32(0x00), 0x1234_5678);
        assert_eq!(bus.read8(0x10), 0xab);
        assert_eq!(bus.read16(0x20), 0xbeef);
        assert_eq!(bus.read64(0x30), 0x0123_4567_89ab_cdef);
        assert_eq!(bus.read32(0x99), 0);
        assert_eq!(bus.get_reg8(0x10), 0xab);
        assert_eq!(bus.get_reg16(0x20), 0xbeef);
        assert_eq!(bus.get_reg32(0x00), 0x1234_5678);
        assert_eq!(bus.get_reg64(0x30), 0x0123_4567_89ab_cdef);
        // Queued reads win over the stored value, then the stored value returns.
        bus.queue_reads32(0x00, &[1, 2]);
        assert_eq!((bus.read32(0x00), bus.read32(0x00)), (1, 2));
        assert_eq!(bus.read32(0x00), 0x1234_5678);
        bus.queue_reads8(0x10, &[0x11]);
        bus.queue_reads16(0x20, &[0x2222]);
        bus.queue_reads64(0x30, &[0x3333_3333_3333_3333]);
        assert_eq!(bus.read8(0x10), 0x11);
        assert_eq!(bus.read16(0x20), 0x2222);
        assert_eq!(bus.read64(0x30), 0x3333_3333_3333_3333);
        assert_eq!(bus.read8(0x10), 0xab);
        // A narrower write replaces the whole stored value.
        bus.write8(0x00, 0xff);
        assert_eq!(bus.get_reg32(0x00), 0xff);
        // Writes neither drain nor change a pending read queue.
        bus.queue_reads32(0x40, &[7]);
        bus.write32(0x40, 9);
        assert_eq!(bus.read32(0x40), 7);
        assert_eq!(bus.read32(0x40), 9);
        // Setters, and per-width write logs (a write at another width is not listed).
        bus.set_reg8(0x50, 1);
        bus.set_reg16(0x52, 2);
        bus.set_reg32(0x54, 3);
        bus.set_reg64(0x58, 4);
        assert_eq!(
            (bus.get_reg8(0x50), bus.get_reg16(0x52), bus.get_reg32(0x54), bus.get_reg64(0x58)),
            (1, 2, 3, 4)
        );
        bus.write8(0x60, 1);
        bus.write16(0x60, 2);
        bus.write32(0x60, 3);
        bus.write64(0x60, 4);
        bus.write8(0x60, 5);
        assert_eq!(bus.writes8_to(0x60), vec![1, 5]);
        assert_eq!(bus.writes16_to(0x60), vec![2]);
        assert_eq!(bus.writes32_to(0x60), vec![3]);
        assert_eq!(bus.writes64_to(0x60), vec![4]);
        assert_eq!(bus.last_write32(0x60), Some(3));
        assert_eq!(bus.last_write32(0x61), None);
        bus.delay_us(3);
        bus.delay_us(4);
        assert_eq!(bus.delays_us(), vec![3, 4]);
        assert_eq!(bus.total_delay_us(), 7);
    }
}
