// SPDX-FileCopyrightText: 2026 contributors
// SPDX-License-Identifier: Apache-2.0

//! Claim-to-citation binding checks run by `hwspecs resolve`.
//!
//! The older `claim hex values absent from cited lines` warning accepts a claim whose hex value
//! appears anywhere in the union of the fact's cited lines, and it ignores identifier ranges and
//! counts. These checks tighten that:
//!
//! - **Binding** (`RES-CLAIM-HEX-UNBOUND`, warning; error under `--strict-claims`): each hex
//!   literal in a claim must appear on a line of a single citation, and that line, the nearest
//!   preceding line ending in `{`, or the anchor's `symbol` must share an identifier token with
//!   the claim sentence that holds the literal.
//! - **Identifier ranges** (`RES-CLAIM-RANGE-END`, `RES-CLAIM-RANGE-SUCCESSOR`, errors): for a
//!   range `PREFIX<n><suffix>..PREFIX<m><suffix>`, the end identifier must appear in the cited
//!   text and `PREFIX<m+1>` must not, unless another range in the claim starts there.
//! - **GPIO counts** (`RES-CLAIM-NGPIOS`, error): `ngpios = <N>` in a claim must appear in the
//!   cited text.

use regex::Regex;
use std::collections::BTreeSet;
use std::sync::OnceLock;

/// Finding code for a claim hex literal no single cited line binds to its sentence.
pub const CODE_HEX_UNBOUND: &str = "RES-CLAIM-HEX-UNBOUND";
/// Finding code for an identifier range whose end identifier is absent from the cited text.
pub const CODE_RANGE_END: &str = "RES-CLAIM-RANGE-END";
/// Finding code for an identifier range whose successor identifier is present in the cited text.
pub const CODE_RANGE_SUCCESSOR: &str = "RES-CLAIM-RANGE-SUCCESSOR";
/// Finding code for a claim `ngpios = <N>` absent from the cited text.
pub const CODE_NGPIOS: &str = "RES-CLAIM-NGPIOS";

/// English function words that would bind any prose line to any sentence.
const STOPWORDS: &[&str] = &[
    "the", "and", "for", "with", "from", "that", "this", "these", "those", "are", "was", "were",
    "has", "have", "had", "its", "not", "but", "into", "onto", "per", "via", "all", "any", "each",
    "when", "which", "also", "then", "than", "both", "only", "will", "can", "may", "must", "shall",
    "should", "does", "use", "uses", "used", "one", "two",
];

/// One resolved citation of a fact: its cited lines and the anchor's `symbol`, if any.
#[derive(Debug, Clone, Default)]
pub struct CitedSpan {
    /// Each cited line, with the nearest preceding line ending in `{` (in the whole file).
    pub lines: Vec<(String, Option<String>)>,
    /// The anchor's `symbol`.
    pub symbol: Option<String>,
}

impl CitedSpan {
    /// Builds a span from a file's lines and a 1-based inclusive range.
    pub fn from_file(file: &[String], start: usize, end: usize, symbol: Option<&str>) -> Self {
        let first = start.saturating_sub(1).min(file.len());
        let last = end.min(file.len());
        // One forward pass: the nearest line ending in `{` before each cited line.
        let mut brace = file[..first]
            .iter()
            .rposition(|l| l.trim_end().ends_with('{'));
        let mut lines = Vec::new();
        for idx in first..last {
            lines.push((file[idx].clone(), brace.map(|j| file[j].clone())));
            if file[idx].trim_end().ends_with('{') {
                brace = Some(idx);
            }
        }
        CitedSpan {
            lines,
            symbol: symbol.map(str::to_string),
        }
    }

    /// Builds a span from lines that carry no block context (document text).
    pub fn from_lines(lines: &[String]) -> Self {
        CitedSpan {
            lines: lines.iter().map(|l| (l.clone(), None)).collect(),
            symbol: None,
        }
    }
}

/// A claim check result: stable code, message (without the record id) and whether it is an
/// error regardless of `--strict-claims`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClaimFinding {
    pub code: &'static str,
    pub message: String,
    pub always_error: bool,
}

fn hex_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r"(?i)\b0x([0-9a-f](?:[0-9a-f_']*[0-9a-f])?)(?:u(?:ll|l)?|(?:ll|l)u?)?\b")
            .unwrap()
    })
}

/// Hex literals in `text` as `(byte offset, value)`, in the notation `resolve::hex_values` reads.
pub fn hex_occurrences(text: &str) -> Vec<(usize, u64)> {
    let mut out = Vec::new();
    for cap in hex_re().captures_iter(text) {
        let (Some(whole), Some(digits)) = (cap.get(0), cap.get(1)) else {
            continue;
        };
        let s = digits.as_str().replace(['_', '\''], "");
        if let Ok(v) = u64::from_str_radix(&s, 16) {
            out.push((whole.start(), v));
        }
    }
    out
}

fn split_camel(word: &str) -> Vec<String> {
    let chars: Vec<char> = word.chars().collect();
    let mut parts = Vec::new();
    let mut cur = String::new();
    for i in 0..chars.len() {
        let c = chars[i];
        if i > 0 {
            let prev = chars[i - 1];
            let lower_to_upper = prev.is_ascii_lowercase() && c.is_ascii_uppercase();
            let acronym_end = prev.is_ascii_uppercase()
                && c.is_ascii_uppercase()
                && chars.get(i + 1).is_some_and(char::is_ascii_lowercase);
            if (lower_to_upper || acronym_end) && !cur.is_empty() {
                parts.push(std::mem::take(&mut cur));
            }
        }
        cur.push(c);
    }
    if !cur.is_empty() {
        parts.push(cur);
    }
    parts
}

/// Identifier tokens of `text`: split on non-alphanumerics (underscores included) and on
/// camelCase boundaries, lowercased, at least three characters, not starting with a digit,
/// and not an English function word.
pub fn identifier_tokens(text: &str) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    for chunk in text.split(|c: char| !c.is_ascii_alphanumeric()) {
        for part in split_camel(chunk) {
            let lower = part.to_ascii_lowercase();
            if lower.len() >= 3
                && !lower.starts_with(|c: char| c.is_ascii_digit())
                && !STOPWORDS.contains(&lower.as_str())
            {
                out.insert(lower);
            }
        }
    }
    out
}

/// Abbreviations whose trailing `.` does not end a sentence.
const ABBREVIATIONS: &[&str] = &["e.g", "i.e", "vs", "cf", "approx", "fig"];

fn ends_with_abbreviation(text: &str) -> bool {
    let word = text
        .rsplit(|c: char| c.is_whitespace() || c == '(')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();
    ABBREVIATIONS.contains(&word.as_str())
}

/// Byte spans of the sentences of `claim`. A sentence ends at `.`, `!` or `?` followed by
/// whitespace or the end of the claim.
pub fn sentence_spans(claim: &str) -> Vec<(usize, usize)> {
    let bytes = claim.as_bytes();
    let mut spans = Vec::new();
    let mut start = 0;
    for (i, &b) in bytes.iter().enumerate() {
        if matches!(b, b'.' | b'!' | b'?')
            && bytes.get(i + 1).is_none_or(|n| n.is_ascii_whitespace())
            && !(b == b'.' && ends_with_abbreviation(&claim[start..i]))
        {
            spans.push((start, i + 1));
            start = i + 1;
        }
    }
    if start < claim.len() {
        spans.push((start, claim.len()));
    }
    spans
}

/// Hex values of `claim` that appear in some cited line but in no cited line bound to the
/// claim sentence holding the literal. Values absent from every cited line are left to the
/// `claim hex values absent from cited lines` warning.
pub fn unbound_hex(claim: &str, citations: &[CitedSpan]) -> Vec<u64> {
    let spans = sentence_spans(claim);
    let mut unbound = BTreeSet::new();
    for (pos, value) in hex_occurrences(claim) {
        let sentence = spans
            .iter()
            .find(|(s, e)| *s <= pos && pos < *e)
            .map(|(s, e)| &claim[*s..*e])
            .unwrap_or(claim);
        let sentence_tokens = identifier_tokens(sentence);
        let mut present = false;
        let mut bound = false;
        'cites: for cite in citations {
            let symbol_tokens = cite
                .symbol
                .as_deref()
                .map(identifier_tokens)
                .unwrap_or_default();
            for (line, context) in &cite.lines {
                if !hex_occurrences(line).iter().any(|(_, v)| *v == value) {
                    continue;
                }
                present = true;
                let mut tokens = identifier_tokens(line);
                if let Some(ctx) = context {
                    tokens.extend(identifier_tokens(ctx));
                }
                tokens.extend(symbol_tokens.iter().cloned());
                if !tokens.is_disjoint(&sentence_tokens) {
                    bound = true;
                    break 'cites;
                }
            }
        }
        if present && !bound {
            unbound.insert(value);
        }
    }
    unbound.into_iter().collect()
}

/// An identifier range `PREFIX<n><suffix>..PREFIX<m><suffix>` in a claim.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IdRange {
    pub start: String,
    pub end: String,
    pub prefix: String,
    pub suffix: String,
    pub n: u64,
    pub m: u64,
    /// Digit count of the end index when it is zero-padded (`PIN07`), else 0.
    pub width: usize,
}

impl IdRange {
    /// `PREFIX<m+1><suffix>`, zero-padded like the end index.
    pub fn successor(&self) -> String {
        format!(
            "{}{:0width$}{}",
            self.prefix,
            self.m + 1,
            self.suffix,
            width = self.width
        )
    }
}

fn norm(s: &str) -> String {
    s.chars()
        .filter(|c| *c != '_' && !c.is_whitespace())
        .flat_map(char::to_lowercase)
        .collect()
}

/// Splits `start..end` into a shared prefix and suffix around differing decimal indexes.
pub fn parse_range(start: &str, end: &str) -> Option<IdRange> {
    let a = start.as_bytes();
    let mut runs = Vec::new();
    let mut i = 0;
    while i < a.len() {
        if a[i].is_ascii_digit() {
            let s = i;
            while i < a.len() && a[i].is_ascii_digit() {
                i += 1;
            }
            runs.push((s, i));
        } else {
            i += 1;
        }
    }
    let end_lower = end.to_ascii_lowercase();
    for &(s, e) in runs.iter().rev() {
        let prefix = &start[..s];
        let suffix = &start[e..];
        if prefix.len() < 2 || end.len() <= prefix.len() + suffix.len() {
            continue;
        }
        if !end_lower.starts_with(&prefix.to_ascii_lowercase())
            || !end_lower.ends_with(&suffix.to_ascii_lowercase())
        {
            continue;
        }
        let middle = &end[prefix.len()..end.len() - suffix.len()];
        if middle.is_empty() || !middle.bytes().all(|b| b.is_ascii_digit()) {
            continue;
        }
        let (Ok(n), Ok(m)) = (start[s..e].parse::<u64>(), middle.parse::<u64>()) else {
            continue;
        };
        if m <= n {
            continue;
        }
        return Some(IdRange {
            start: start.to_string(),
            end: end.to_string(),
            prefix: prefix.to_string(),
            suffix: suffix.to_string(),
            n,
            m,
            width: if middle.len() > 1 && middle.starts_with('0') {
                middle.len()
            } else {
                0
            },
        });
    }
    None
}

/// Identifier ranges in `claim`, written bare or in backticks.
pub fn identifier_ranges(claim: &str) -> Vec<IdRange> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re = RE.get_or_init(|| {
        Regex::new(r"`?([A-Za-z_][A-Za-z0-9_]*)`?[ \t]*\.\.[ \t]*`?([A-Za-z_][A-Za-z0-9_]*)`?")
            .unwrap()
    });
    let mut out = Vec::new();
    for cap in re.captures_iter(claim) {
        let whole = cap.get(0).unwrap();
        let before = claim[..whole.start()].chars().next_back();
        if before.is_some_and(|c| c.is_ascii_alphanumeric() || c == '_' || c == '.') {
            continue;
        }
        if let Some(r) = parse_range(&cap[1], &cap[2]) {
            out.push(r);
        }
    }
    out
}

/// Normalized identifier windows of cited text: whitespace-separated words within runs of
/// letters, digits, underscores and whitespace, joined in groups of one to three, lowercased
/// with `_` removed (so `GPIO_15`, `gpio15` and `GPIO 15` all read `gpio15`).
pub fn identifier_windows(text: &str) -> BTreeSet<String> {
    let mut out = BTreeSet::new();
    for segment in
        text.split(|c: char| !(c.is_ascii_alphanumeric() || c == '_' || c.is_whitespace()))
    {
        let words: Vec<String> = segment.split_whitespace().map(norm).collect();
        for i in 0..words.len() {
            let mut joined = String::new();
            for word in words.iter().skip(i).take(3) {
                joined.push_str(word);
                if !joined.is_empty() {
                    out.insert(joined.clone());
                }
            }
        }
    }
    out
}

/// Whether some window is `key` or starts with `key` followed by a non-digit (so `gpio7`
/// matches `gpio7cfg` but not `gpio70`).
fn window_starts_with(windows: &BTreeSet<String>, key: &str) -> bool {
    windows.iter().any(|w| {
        w.strip_prefix(key)
            .is_some_and(|rest| !rest.starts_with(|c: char| c.is_ascii_digit()))
    })
}

/// Range findings for `claim` against the fact's cited text.
pub fn range_findings(claim: &str, cited_text: &str) -> Vec<ClaimFinding> {
    let ranges = identifier_ranges(claim);
    if ranges.is_empty() {
        return Vec::new();
    }
    let windows = identifier_windows(cited_text);
    let mut out = Vec::new();
    for r in &ranges {
        let shown = format!("{}..{}", r.start, r.end);
        if !window_starts_with(&windows, &norm(&r.end)) {
            out.push(ClaimFinding {
                code: CODE_RANGE_END,
                message: format!(
                    "claim identifier range {shown}: end identifier {} absent from cited text",
                    r.end
                ),
                always_error: true,
            });
        }
        let successor = r.successor();
        let continued = ranges.iter().any(|o| {
            norm(&o.prefix) == norm(&r.prefix)
                && norm(&o.suffix) == norm(&r.suffix)
                && o.n == r.m + 1
        });
        if continued {
            continue;
        }
        if window_starts_with(&windows, &norm(&successor)) {
            out.push(ClaimFinding {
                code: CODE_RANGE_SUCCESSOR,
                message: format!(
                    "claim identifier range {shown}: successor {successor} present in cited text"
                ),
                always_error: true,
            });
        }
    }
    out
}

/// `ngpios = <N>` findings for `claim` against the fact's cited text.
pub fn ngpios_findings(claim: &str, cited_text: &str) -> Vec<ClaimFinding> {
    static RE: OnceLock<Regex> = OnceLock::new();
    let re =
        RE.get_or_init(|| Regex::new(r"(?i)\bngpios\s*=\s*<\s*(0x[0-9a-f]+|[0-9]+)\s*>").unwrap());
    let mut out = Vec::new();
    let mut seen = BTreeSet::new();
    for cap in re.captures_iter(claim) {
        let value = cap[1].to_string();
        if !seen.insert(value.to_ascii_lowercase()) {
            continue;
        }
        let literal = Regex::new(&format!(
            r"(?i)\bngpios\s*=\s*<\s*{}\s*>",
            regex::escape(&value)
        ))
        .unwrap();
        if !literal.is_match(cited_text) {
            out.push(ClaimFinding {
                code: CODE_NGPIOS,
                message: format!("claim ngpios = <{value}> absent from cited text"),
                always_error: true,
            });
        }
    }
    out
}

/// All claim findings for one fact, in a stable order: binding, ranges, `ngpios`.
pub fn claim_findings(claim: &str, citations: &[CitedSpan]) -> Vec<ClaimFinding> {
    let mut out = Vec::new();
    let unbound = unbound_hex(claim, citations);
    if !unbound.is_empty() {
        let shown: Vec<String> = unbound.iter().map(|v| format!("0x{v:x}")).collect();
        out.push(ClaimFinding {
            code: CODE_HEX_UNBOUND,
            message: format!(
                "claim hex values not bound to a cited line sharing an identifier with their sentence: {}",
                shown.join(", ")
            ),
            always_error: false,
        });
    }
    let cited_text = citations
        .iter()
        .flat_map(|c| c.lines.iter().map(|(l, _)| l.as_str()))
        .collect::<Vec<_>>()
        .join("\n");
    out.extend(range_findings(claim, &cited_text));
    out.extend(ngpios_findings(claim, &cited_text));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn span(lines: &[&str], symbol: Option<&str>) -> CitedSpan {
        let file: Vec<String> = lines.iter().map(|s| s.to_string()).collect();
        CitedSpan::from_file(&file, 1, file.len(), symbol)
    }

    #[test]
    fn tokens_split_camel_and_underscores() {
        let t = identifier_tokens("WIDGET_CTRL_reg widgetIrqEnable HTTPServer 0x20 i2c2 the");
        for want in [
            "widget", "ctrl", "reg", "irq", "enable", "http", "server", "i2c2",
        ] {
            assert!(t.contains(want), "missing {want}: {t:?}");
        }
        assert!(!t.contains("0x20"));
        assert!(!t.contains("the"));
    }

    #[test]
    fn unrelated_hex_is_unbound() {
        let cite = span(
            &["#define WIDGET_RESET 0x40", "#define GADGET_MODE 0x10"],
            None,
        );
        assert_eq!(
            unbound_hex(
                "The widget reset value is 0x10.",
                std::slice::from_ref(&cite)
            ),
            [0x10]
        );
        assert!(unbound_hex("The gadget mode is 0x10.", &[cite]).is_empty());
    }

    #[test]
    fn block_context_and_symbol_bind() {
        let file: Vec<String> = [
            "static const struct widget_cfg cfg = {",
            "\t.limit = 0x7f,",
            "};",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
        let cite = CitedSpan::from_file(&file, 2, 2, None);
        assert!(unbound_hex("The widget default ceiling is 0x7f.", &[cite]).is_empty());
        let cite = span(&["\treturn 0x3;"], Some("widget_probe"));
        assert!(unbound_hex("Probe returns 0x3 for a widget.", &[cite]).is_empty());
    }

    #[test]
    fn binding_uses_the_literal_sentence() {
        let cite = span(&["#define GADGET_LEVEL 0x10"], None);
        let claim = "The gadget is present. Its widget mode is 0x10.";
        assert_eq!(unbound_hex(claim, &[cite]), [0x10]);
    }

    #[test]
    fn ranges_parse() {
        let r = identifier_ranges("Pins `WGPIO_PIN0`..`WGPIO_PIN7` and IRQ_0_EN..IRQ_3_EN.");
        assert_eq!(r.len(), 2);
        assert_eq!((r[0].prefix.as_str(), r[0].n, r[0].m), ("WGPIO_PIN", 0, 7));
        assert_eq!(
            (r[1].prefix.as_str(), r[1].suffix.as_str(), r[1].n, r[1].m),
            ("IRQ_", "_EN", 0, 3)
        );
        assert!(identifier_ranges("bits 0..7 and 0x0..0x7").is_empty());
    }

    #[test]
    fn range_end_and_successor() {
        let cited = "WPIN0 WPIN1 WPIN2 WPIN3";
        assert!(range_findings("Pins WPIN0..WPIN3.", cited).is_empty());
        let f = range_findings("Pins WPIN0..WPIN2.", cited);
        assert_eq!(f.len(), 1);
        assert_eq!(f[0].code, CODE_RANGE_SUCCESSOR);
        let f = range_findings("Pins WPIN0..WPIN4.", cited);
        assert_eq!(f.len(), 1);
        assert_eq!(f[0].code, CODE_RANGE_END);
        assert!(range_findings("Pins WPIN0..WPIN1 and WPIN2..WPIN3.", cited).is_empty());
        assert!(range_findings("Pins WPIN0..WPIN3.", "w_pin_0 W PIN 3").is_empty());
        assert!(range_findings("Pins WPIN0..WPIN1.", "WPIN0 WPIN1 WPIN10").is_empty());
    }

    #[test]
    fn range_suffix_zero_padding_and_short_prefix() {
        let f = range_findings("IRQ_0_EN..IRQ_3_EN.", "IRQ_3_EN IRQ_4_STATUS");
        assert!(f.is_empty(), "{f:?}");
        let f = range_findings("IRQ_0_EN..IRQ_3_EN.", "IRQ_3_EN IRQ_4_EN");
        assert_eq!(f[0].code, CODE_RANGE_SUCCESSOR);
        let f = range_findings("PIN00..PIN07.", "PIN07 PIN08");
        assert_eq!(f[0].code, CODE_RANGE_SUCCESSOR);
        assert!(f[0].message.contains("PIN08"));
        assert!(range_findings("GPIO0..GPIO7.", "GPIO7_CFG").is_empty());
        assert!(identifier_ranges("lanes x1..x4").is_empty());
    }

    #[test]
    fn sentences_skip_abbreviations() {
        let claim = "Some widget modes (e.g. turbo) are 0x5. Gadget mode is 0x6.";
        assert_eq!(sentence_spans(claim).len(), 2);
        let cite = span(&["#define WIDGET_TURBO 0x5"], None);
        assert!(unbound_hex(claim, &[cite]).is_empty());
    }

    #[test]
    fn binding_picks_the_citation_holding_the_literal() {
        let a = span(&["#define GADGET_LEVEL 0x10"], None);
        let b = span(&["#define WIDGET_MODE 0x10"], None);
        assert!(unbound_hex("The widget mode is 0x10.", &[a.clone(), b]).is_empty());
        let c = span(&["#define WIDGET_MODE 0x20"], None);
        assert_eq!(unbound_hex("The widget mode is 0x10.", &[a, c]), [0x10]);
    }

    #[test]
    fn context_scan_is_linear_and_tracks_nearest_brace() {
        let file: Vec<String> = [
            "struct widget {",
            "	int a;",
            "};",
            "enum gadget {",
            "	X = 0x1,",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
        let s = CitedSpan::from_file(&file, 2, 5, None);
        assert_eq!(s.lines[0].1.as_deref(), Some("struct widget {"));
        assert_eq!(s.lines[3].1.as_deref(), Some("enum gadget {"));
    }

    #[test]
    fn ngpios_literal() {
        assert!(ngpios_findings("Has ngpios = <16>.", "\tngpios = <16>;").is_empty());
        let f = ngpios_findings("Has ngpios = <16>.", "\tngpios = <18>;");
        assert_eq!(f[0].code, CODE_NGPIOS);
    }
}
