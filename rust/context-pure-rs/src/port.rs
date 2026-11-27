//! Rust port of `src/zkc/context.py`'s recordable pure helpers.
//!
//! The bridge uses a process-only alias module in the spike-06 research directory
//! (`pure_bridge.py`) because `_clean_title` is private and `rust-anything` only
//! exports public functions. Both aliases delegate verbatim to `zkc.context`, so
//! the Python original remains the sole recording oracle. `ContextNamer`,
//! `ContextAssembler` and `HigherDimProposal` stay in Python (callable / Storage /
//! dataclass boundary).

#![forbid(unsafe_code)]

use std::collections::BTreeMap;

/// Python `str.splitlines()` boundaries; `\r\n` is a single break. Rust's
/// `str::lines()` only splits on `\n`/`\r\n`, so the wider set is reproduced here.
fn is_line_break(c: char) -> bool {
    matches!(
        c,
        '\n' | '\r'
            | '\u{000b}'
            | '\u{000c}'
            | '\u{001c}'
            | '\u{001d}'
            | '\u{001e}'
            | '\u{2028}'
            | '\u{2029}'
    )
}

fn first_nonempty_line(raw: &str) -> Option<String> {
    let chars: Vec<char> = raw.chars().collect();
    let mut i = 0usize;
    let mut line = String::new();
    while i < chars.len() {
        let c = chars[i];
        if is_line_break(c) {
            if c == '\r' && chars.get(i + 1) == Some(&'\n') {
                i += 1;
            }
            let trimmed = line.trim();
            if !trimmed.is_empty() {
                return Some(trimmed.to_string());
            }
            line.clear();
        } else {
            line.push(c);
        }
        i += 1;
    }
    let trimmed = line.trim();
    (!trimmed.is_empty()).then(|| trimmed.to_string())
}

/// Port of `clean_title`, the public alias of `_clean_title`
/// (`src/zkc/context.py:51`). The source strips only ASCII `"` and `'` —
/// Chinese curly quotes are deliberately preserved.
pub fn clean_title(raw: String) -> Result<String, String> {
    let Some(first) = first_nonempty_line(&raw) else {
        return Ok(String::new());
    };
    let trimmed = first.trim_matches(|c| c == '"' || c == '\'');
    Ok(trimmed.chars().take(32).collect())
}

const STOPCHARS: &str =
    "的了一是在不有我他这中大为上和是与就都也要会能可去你那它此该等之其为以于对其或"; // recorded-literal: context.py _STOPCHARS

fn tokenize(text: &str, counts: &mut BTreeMap<String, usize>) {
    let mut token = String::new();
    let flush = |token: &mut String, counts: &mut BTreeMap<String, usize>| {
        if !token.is_empty() {
            *counts.entry(std::mem::take(token)).or_insert(0) += 1;
        }
    };
    for c in text.to_lowercase().chars() {
        if c.is_ascii_alphanumeric() {
            token.push(c);
        } else if ('\u{4e00}'..='\u{9fff}').contains(&c) {
            flush(&mut token, counts);
            *counts.entry(c.to_string()).or_insert(0) += 1;
        } else {
            flush(&mut token, counts);
        }
    }
    flush(&mut token, counts);
}

/// Port of `fallback_name` (`src/zkc/context.py:61`): deterministic degradation
/// path using token frequency, with lexicographic tie-break.
pub fn fallback_name(member_texts: Vec<String>, n_members: i64) -> Result<String, String> {
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for text in &member_texts {
        tokenize(text, &mut counts);
    }
    counts.retain(|token, _| {
        !STOPCHARS.chars().any(|c| c.to_string() == *token)
            && !(token.len() == 1 && token.is_ascii())
    });
    let mut ranked: Vec<(String, usize)> = counts.into_iter().collect();
    ranked.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let top: Vec<&str> = ranked.iter().take(2).map(|(t, _)| t.as_str()).collect();
    if top.is_empty() {
        Ok(format!("未命名聚合（{n_members}条）")) // recorded-literal: context.py fallback label
    } else {
        Ok(format!("聚合：{}（{n_members}条）", top.join("/"))) // recorded-literal: context.py fallback label
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clean_title_takes_first_nonempty_line_and_ascii_quotes() {
        assert_eq!(clean_title("\n  \"标题\" \n尾部".into()).unwrap(), "标题");
        assert_eq!(clean_title("“中文引号”".into()).unwrap(), "“中文引号”");
    }

    #[test]
    fn clean_title_truncates_to_32_chars() {
        let got = clean_title("12345678901234567890123456789012末位".into()).unwrap();
        assert_eq!(got, "12345678901234567890123456789012");
    }

    #[test]
    fn fallback_drops_ascii_singletons_but_keeps_cjk() {
        assert_eq!(
            fallback_name(vec!["a b c".into()], 3).unwrap(),
            "未命名聚合（3条）"
        );
        assert_eq!(
            fallback_name(vec!["中 文 中 文".into()], 4).unwrap(),
            "聚合：文（4条）"
        );
    }

    #[test]
    fn fallback_lowercases_before_tokenizing() {
        assert_eq!(
            fallback_name(vec!["İstanbul İstanbul".into()], 2).unwrap(),
            "聚合：stanbul（2条）"
        );
    }
}
