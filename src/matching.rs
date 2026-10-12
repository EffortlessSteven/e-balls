//! Literal matching over raw commit-message bytes, independent of Git and rendering.
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};

/// Compile once per collection, not once per commit. ASCII folding preserves
/// existing e/E counts; other UTF-8 bytes are exact and are never normalized.
#[derive(Debug)]
pub struct LiteralMatcher {
    text: String,
    needle: Vec<u8>,
    prefix: Vec<usize>,
    case_sensitive: bool,
}

impl LiteralMatcher {
    pub fn new(text: impl Into<String>, case_sensitive: bool) -> Result<Self> {
        let text = text.into();
        if text.is_empty() {
            bail!("text must be a nonempty literal string");
        }
        let mut needle = text.as_bytes().to_vec();
        if !case_sensitive {
            needle.make_ascii_lowercase();
        }
        // Prefix table makes repeated-prefix needles linear-time, without a
        // lowercase copy of every message or a regex interpretation of text.
        let mut prefix = vec![0; needle.len()];
        let mut matched = 0;
        for index in 1..needle.len() {
            while matched > 0 && needle[index] != needle[matched] {
                matched = prefix[matched - 1];
            }
            if needle[index] == needle[matched] {
                matched += 1;
            }
            prefix[index] = matched;
        }
        Ok(Self {
            text,
            needle,
            prefix,
            case_sensitive,
        })
    }

    pub fn count(&self, message: &[u8]) -> u64 {
        if self.needle.len() == 1 {
            let needle = self.needle[0];
            return message
                .iter()
                .filter(|byte| {
                    let byte = if self.case_sensitive {
                        **byte
                    } else {
                        byte.to_ascii_lowercase()
                    };
                    byte == needle
                })
                .count() as u64;
        }
        let mut matched = 0;
        let mut count = 0;
        for &byte in message {
            let byte = if self.case_sensitive {
                byte
            } else {
                byte.to_ascii_lowercase()
            };
            while matched > 0 && byte != self.needle[matched] {
                matched = self.prefix[matched - 1];
            }
            if byte == self.needle[matched] {
                matched += 1;
            }
            if matched == self.needle.len() {
                count += 1;
                matched = 0; // Non-overlapping occurrences within this message.
            }
        }
        count
    }

    pub fn metadata(&self) -> Value {
        json!({
            "kind": "literal", "text": self.text,
            "case": if self.case_sensitive { "sensitive" } else { "ascii-insensitive" },
            "overlapping": false,
        })
    }

    /// Retain legacy fields/labels only when they accurately describe the match.
    pub fn legacy_letter(&self) -> Option<String> {
        (!self.case_sensitive && self.needle.len() == 1 && self.needle[0].is_ascii_alphabetic())
            .then(|| (self.needle[0] as char).to_string())
    }

    /// An escaped, bounded label fits the bundled font and cannot add chart rows.
    /// This affects presentation only: the exact text stays in matcher metadata.
    pub fn display(&self) -> String {
        if let Some(letter) = self.legacy_letter() {
            return letter;
        }
        let mut result = String::new();
        for character in self.text.chars() {
            let escaped: String = character.escape_default().collect();
            if result.len() + escaped.len() > 64 {
                result.push_str("...");
                break;
            }
            result.push_str(&escaped);
        }
        result
    }

    pub fn units(&self) -> (String, String) {
        match self.legacy_letter() {
            Some(letter) => (format!("{letter}'s"), letter),
            None => ("matches".into(), "match".into()),
        }
    }

    /// Read both frozen v1 letter snapshots and new self-describing matchers.
    /// Refuse ambiguous or unsupported semantics instead of guessing a count.
    pub fn from_source(source: &Value) -> Result<Self> {
        if let Some(spec) = source.get("matcher") {
            let spec = spec.as_object().context("matcher must be an object")?;
            if spec.len() != 4
                || spec.get("kind") != Some(&json!("literal"))
                || spec.get("overlapping") != Some(&json!(false))
            {
                bail!("unsupported matcher semantics");
            }
            let case_sensitive = match spec.get("case").and_then(Value::as_str) {
                Some("sensitive") => true,
                Some("ascii-insensitive") => false,
                _ => bail!("unsupported matcher case mode"),
            };
            let matcher = Self::new(
                spec.get("text")
                    .and_then(Value::as_str)
                    .context("matcher text must be a string")?,
                case_sensitive,
            )?;
            if let Some(letter) = source.get("letter") {
                if matcher.legacy_letter().as_deref() != letter.as_str() || !letter.is_string() {
                    bail!("legacy letter disagrees with matcher");
                }
            }
            if source.get("case").is_some_and(|case| {
                case != "ASCII-insensitive" || matcher.legacy_letter().is_none()
            }) {
                bail!("legacy case disagrees with matcher");
            }
            return Ok(matcher);
        }
        let letter = source
            .get("letter")
            .and_then(Value::as_str)
            .context("snapshot has no matcher or legacy letter")?;
        if letter.len() != 1
            || !letter.as_bytes()[0].is_ascii_lowercase()
            || source
                .get("case")
                .is_some_and(|case| case != "ASCII-insensitive")
        {
            bail!("invalid legacy letter matching rules");
        }
        Self::new(letter, false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn literal_strings_and_case_modes() -> Result<()> {
        for (needle, body, count) in [
            ("e", "e E é", 2),
            ("fix:", "Fix: fix: FIX:", 3),
            ("aa", "aaaaa", 2),
            ("a.*", "a.* aaa a.*", 2),
            ("\n\n", "title\n\nbody\n\ntrailer", 2),
            (" ", " a b ", 3),
            ("🦀 café", "🦀 café 🦀 CAFÉ 🦀 café", 2),
        ] {
            assert_eq!(
                LiteralMatcher::new(needle, false)?.count(body.as_bytes()),
                count,
                "{needle:?}"
            );
        }
        assert_eq!(
            LiteralMatcher::new("Fix:", true)?.count(b"fix: Fix: FIX:"),
            1
        );
        assert!(LiteralMatcher::new("", false).is_err());
        Ok(())
    }

    #[test]
    fn raw_bytes_message_boundaries_and_no_unicode_normalization() -> Result<()> {
        let matcher = LiteralMatcher::new("fix:", false)?;
        assert_eq!(matcher.count(b"\xffFiX:\x00fix:"), 2);
        assert_eq!(matcher.count(b"fi") + matcher.count(b"x:"), 0);
        assert_eq!(
            LiteralMatcher::new("é", false)?.count("é e\u{301} É".as_bytes()),
            1
        );
        Ok(())
    }

    #[test]
    fn repeated_prefixes_agree_with_a_simple_reference() -> Result<()> {
        for width in 1..=6 {
            for mask in 0..(1 << width) {
                let needle: String = (0..width)
                    .map(|i| if mask & (1 << i) == 0 { 'a' } else { 'B' })
                    .collect();
                for case_sensitive in [false, true] {
                    let matcher = LiteralMatcher::new(&needle, case_sensitive)?;
                    for body in [b"aaBaBaaaaBBabaB".as_slice(), b"BBBBBBBB", b"aaaaaaa", b""] {
                        let folded: Vec<_> = body
                            .iter()
                            .map(|c| {
                                if case_sensitive {
                                    *c
                                } else {
                                    c.to_ascii_lowercase()
                                }
                            })
                            .collect();
                        let mut cursor = 0;
                        let mut expected = 0;
                        while cursor + matcher.needle.len() <= folded.len() {
                            if folded[cursor..].starts_with(&matcher.needle) {
                                expected += 1;
                                cursor += matcher.needle.len();
                            } else {
                                cursor += 1;
                            }
                        }
                        assert_eq!(matcher.count(body), expected);
                    }
                }
            }
        }
        let needle = format!("{}b", "a".repeat(100_000));
        assert_eq!(
            LiteralMatcher::new(needle, false)?.count(&vec![b'a'; 1_000_000]),
            0
        );
        Ok(())
    }

    #[test]
    fn metadata_roundtrips_and_rejects_tampering() -> Result<()> {
        let matcher = LiteralMatcher::new("Fix:\n🦀", true)?;
        let source = json!({"matcher": matcher.metadata()});
        assert_eq!(
            LiteralMatcher::from_source(&source)?.metadata(),
            matcher.metadata()
        );
        for key in ["case", "overlapping", "kind", "text"] {
            let mut bad = source.clone();
            bad["matcher"][key] = json!(true);
            assert!(LiteralMatcher::from_source(&bad).is_err());
        }
        assert_eq!(
            LiteralMatcher::from_source(&json!({"letter":"e"}))?.count(b"eE"),
            2
        );
        assert!(
            LiteralMatcher::from_source(&json!({"matcher":matcher.metadata(),"letter":"e"}))
                .is_err()
        );
        let label = LiteralMatcher::new("\n🦀".repeat(100), false)?.display();
        assert!(label.is_ascii() && label.len() <= 67 && !label.contains('\n'));
        Ok(())
    }
}
