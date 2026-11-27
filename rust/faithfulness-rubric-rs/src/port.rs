//! Rust port of `src/zkc/faithfulness.py`'s literal rubric layer, recorded through
//! `spikes/spike-10-model-quality/pure_bridge.py` (process-only alias).
//!
//! Proof boundary: `cases.jsonl` was recorded from the Python original (7 pure
//! functions, no Storage / LLM / dataclass / callable inputs). Router, judge and
//! Storage functions stay in Python. Rubric flags are human-review annotations,
//! never a release decision. See `finding-faithfulness-rubric-boundary.md`.
//!
//! Every numeric / string constant below is a recorded literal from `zkc.tuning`
//! or the original's decision table; none is promoted to CALIBRATED here.

#![forbid(unsafe_code)]

use serde_json::{Value, json};
use std::collections::HashSet;

const VERBATIM_MAX: f64 = 0.5; // recorded-literal: tuning.py FAITH_RUBRIC_VERBATIM_MAX (placeholder)
const OVERLAP_MAX: f64 = 0.7; // recorded-literal: tuning.py FAITH_RUBRIC_OVERLAP_MAX (placeholder)
const LCS_TRUNCATE: usize = 600; // recorded-literal: faithfulness.py _lcs_length truncation
const DEFAULT_NGRAMS: i64 = 3; // recorded-literal: faithfulness.py _ngrams default n
const NO_SOURCE_FLAG: &str = "rubric_no_source_text"; // recorded-literal: faithfulness.py rubric_flags
const FORCED_PREFIX: &str = "forced"; // recorded-literal: faithfulness.py FORCED_ROUTE_PREFIX
const HUMAN_ONLY: &str = "human_only"; // recorded-literal: faithfulness.py HUMAN_ONLY_ROUTE

fn want_str(value: &Value, label: &str) -> Result<String, String> {
    value
        .as_str()
        .map(str::to_string)
        .ok_or_else(|| format!("{label}: expected string"))
}

fn want_str_list(value: &Value, label: &str) -> Result<Vec<String>, String> {
    let array = value
        .as_array()
        .ok_or_else(|| format!("{label}: expected array of strings"))?;
    array
        .iter()
        .map(|item| match item {
            Value::String(text) => Ok(text.clone()),
            Value::Null => Ok(String::new()), // original: `t or ""`
            _ => Err(format!("{label}: expected array of strings")),
        })
        .collect()
}

/// The original `_PUNCT` regex character class, spelled out as a predicate.
fn is_punct(c: char) -> bool {
    c.is_whitespace()
        || matches!(
            c,
            '，' | '。'
                | '；'
                | '：'
                | '、'
                | '！'
                | '？'
                | ','
                | '.'
                | '!'
                | '?'
                | ':'
                | ';'
                | '"'
                | '\''
                | '“'
                | '”'
                | '‘'
                | '’'
                | '（'
                | '）'
                | '('
                | ')'
                | '【'
                | '】'
                | '['
                | ']'
                | '—'
                | '-'
        )
}

fn normalize_text(text: &str) -> String {
    text.chars().filter(|c| !is_punct(*c)).collect()
}

/// Full Python slice semantics for `t[i:i+n]`, needed because `_ngrams` accepts
/// `n <= 0` and the recorded oracle includes `n = 0` and `n = -1`.
fn gram_at(chars: &[char], i: i64, n: i64) -> String {
    let len = chars.len() as i64;
    if n >= 0 {
        let start = i as usize;
        let end = (i + n) as usize;
        if start >= chars.len() {
            return String::new();
        }
        return chars[start..end.min(chars.len())].iter().collect();
    }
    let start = i as usize;
    if start >= chars.len() {
        return String::new();
    }
    let mut end = i + n;
    if end < 0 {
        end += len;
    }
    if end < 0 || (end as usize) < start {
        return String::new();
    }
    chars[start..(end as usize).min(chars.len())]
        .iter()
        .collect()
}

fn ngrams_set(text: &str, n: i64) -> HashSet<String> {
    let normalized = normalize_text(text);
    let chars: Vec<char> = normalized.chars().collect();
    let len = chars.len() as i64;
    if len < n {
        return if normalized.is_empty() {
            HashSet::new()
        } else {
            HashSet::from([normalized])
        };
    }
    (0..=len - n).map(|i| gram_at(&chars, i, n)).collect()
}

fn lcs_len(a: &str, b: &str) -> usize {
    let a: Vec<char> = normalize_text(a).chars().take(LCS_TRUNCATE).collect();
    let b: Vec<char> = normalize_text(b).chars().take(LCS_TRUNCATE).collect();
    if a.is_empty() || b.is_empty() {
        return 0;
    }
    let mut prev = vec![0usize; b.len() + 1];
    let mut best = 0;
    for ca in &a {
        let mut cur = vec![0usize; b.len() + 1];
        for (j, cb) in b.iter().enumerate() {
            if ca == cb {
                cur[j + 1] = prev[j] + 1;
                if cur[j + 1] > best {
                    best = cur[j + 1];
                }
            }
        }
        prev = cur;
    }
    best
}

fn verbatim_rate_value(claim: &str, sources: &[String]) -> f64 {
    let body = normalize_text(claim);
    if body.is_empty() {
        return 0.0;
    }
    let longest = sources.iter().map(|s| lcs_len(claim, s)).max().unwrap_or(0);
    (longest as f64 / body.chars().count() as f64).min(1.0)
}

fn overlap_value(claim: &str, sources: &[String]) -> f64 {
    let grams = ngrams_set(claim, DEFAULT_NGRAMS);
    if grams.is_empty() {
        return 0.0;
    }
    let mut source_grams: HashSet<String> = HashSet::new();
    for source in sources {
        source_grams.extend(ngrams_set(source, DEFAULT_NGRAMS));
    }
    let shared = grams.intersection(&source_grams).count();
    shared as f64 / grams.len() as f64
}

/// Port of `normalize` (`src/zkc/faithfulness.py:169`).
pub fn normalize(text: Value) -> Result<Value, String> {
    Ok(json!(normalize_text(&want_str(&text, "text")?)))
}

/// Port of `ngrams` (`src/zkc/faithfulness.py:173`). The alias returns a sorted
/// list; the port preserves that deterministic JSON encoding.
pub fn ngrams(text: Value, n: i64) -> Result<Value, String> {
    let mut result: Vec<String> = ngrams_set(&want_str(&text, "text")?, n)
        .into_iter()
        .collect();
    result.sort();
    Ok(json!(result))
}

/// Port of `lcs_length` (`src/zkc/faithfulness.py:180`).
pub fn lcs_length(a: Value, b: Value) -> Result<Value, String> {
    Ok(json!(lcs_len(&want_str(&a, "a")?, &want_str(&b, "b")?)))
}

/// Port of `verbatim_rate` (`src/zkc/faithfulness.py:198`).
pub fn verbatim_rate(claim: Value, source_texts: Value) -> Result<Value, String> {
    let sources = want_str_list(&source_texts, "source_texts")?;
    Ok(json!(verbatim_rate_value(
        &want_str(&claim, "claim")?,
        &sources
    )))
}

/// Port of `overlap` (`src/zkc/faithfulness.py:206`).
pub fn overlap(claim: Value, source_texts: Value) -> Result<Value, String> {
    let sources = want_str_list(&source_texts, "source_texts")?;
    Ok(json!(overlap_value(&want_str(&claim, "claim")?, &sources)))
}

/// Port of `rubric_flags` (`src/zkc/faithfulness.py:217`).
pub fn rubric_flags(claim_text: Value, source_texts: Value) -> Result<Value, String> {
    let claim = want_str(&claim_text, "claim_text")?;
    let all = want_str_list(&source_texts, "source_texts")?;
    let texts: Vec<String> = all
        .into_iter()
        .filter(|text| !text.trim().is_empty())
        .collect();
    if texts.is_empty() {
        return Ok(json!([NO_SOURCE_FLAG]));
    }
    let v = verbatim_rate_value(&claim, &texts);
    let o = overlap_value(&claim, &texts);
    let mut flags = Vec::new();
    if v > VERBATIM_MAX {
        flags.push(format!("rubric_verbatim_{v:.2}"));
    }
    if o > OVERLAP_MAX {
        flags.push(format!("rubric_overlap_{o:.2}"));
    }
    Ok(json!(flags))
}

/// Port of `_is_forced` (`src/zkc/faithfulness.py:386`).
pub fn is_forced(route: Value) -> Result<Value, String> {
    if route.is_null() {
        return Ok(json!(false));
    }
    let route = want_str(&route, "route")?;
    Ok(json!(
        route.starts_with(FORCED_PREFIX) || route == HUMAN_ONLY
    ))
}
