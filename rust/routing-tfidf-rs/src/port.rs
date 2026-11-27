//! Rust port of `src/zkc/routing.py`'s literal lexical TF-IDF layer, recorded
//! through `spikes/spike-15-routing-tfidf/pure_bridge.py` (process-only alias).
//!
//! Proof boundary: `cases.jsonl` came from the Python original for three pure
//! functions (strings / string lists / string-keyed float maps in, no Storage,
//! LLM, dataclass or datetime). Router classes, tuning gates and corpus
//! persistence stay in Python. This is not a routing or safety decision.
//!
//! Every constant below is a recorded literal from the original; none is
//! promoted to a tuned value here.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

const CJK_LO: char = '\u{4e00}'; // recorded-literal: routing.py _TOKEN_RE [\u4e00-\u9fff]
const CJK_HI: char = '\u{9fff}'; // recorded-literal: routing.py _TOKEN_RE [\u4e00-\u9fff]
const ONE: f64 = 1.0; // recorded-literal: routing.py _tfidf_vector tf increment

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
    array.iter().map(|item| want_str(item, label)).collect()
}

fn want_f64_map(value: &Value, label: &str) -> Result<Map<String, Value>, String> {
    let object = value
        .as_object()
        .ok_or_else(|| format!("{label}: expected object of numbers"))?;
    for (key, item) in object {
        if !item.is_number() {
            return Err(format!("{label}.{key}: expected number"));
        }
    }
    Ok(object.clone())
}

fn number(value: &Value) -> f64 {
    value.as_f64().unwrap_or(0.0)
}

/// Port of `_tokenize` (`src/zkc/routing.py:145`).
///
/// Python lowers the whole string first, then `[a-z0-9]+|[\u4e00-\u9fff]`
/// groups ASCII runs and emits each CJK ideograph separately. Rust's
/// `char::to_lowercase` matches Python's full Unicode lowercase mapping for the
/// recorded characters (e.g. `İ` -> `i` + combining dot, which is then dropped).
pub fn tokenize(text: Value) -> Result<Value, String> {
    let text = want_str(&text, "text")?;
    let lowered: String = text.chars().flat_map(char::to_lowercase).collect();
    let mut result: Vec<String> = Vec::new();
    let mut run = String::new();
    for ch in lowered.chars() {
        if ch.is_ascii_lowercase() || ch.is_ascii_digit() {
            run.push(ch);
            continue;
        }
        if !run.is_empty() {
            result.push(std::mem::take(&mut run));
        }
        if (CJK_LO..=CJK_HI).contains(&ch) {
            result.push(ch.to_string());
        }
    }
    if !run.is_empty() {
        result.push(run);
    }
    Ok(json!(result))
}

/// Port of `_tfidf_vector` (`src/zkc/routing.py:149`).
///
/// The recorded output is an insertion-ordered map keyed by token
/// first-occurrence order; `serde_json`'s `preserve_order` feature keeps that
/// order byte for byte. A token missing from `idf` contributes exactly 0.0.
pub fn tfidf_vector(tokens: Value, idf: Value) -> Result<Value, String> {
    let tokens = want_str_list(&tokens, "tokens")?;
    let idf = want_f64_map(&idf, "idf")?;
    let mut tf: Vec<(String, f64)> = Vec::new();
    for token in &tokens {
        match tf.iter_mut().find(|(key, _)| key == token) {
            Some(entry) => entry.1 += ONE,
            None => tf.push((token.clone(), ONE)),
        }
    }
    let n = if tokens.is_empty() {
        ONE
    } else {
        tokens.len() as f64
    };
    let mut result = Map::new();
    for (token, count) in tf {
        let weight = idf.get(&token).map(number).unwrap_or(0.0);
        result.insert(token, json!((count / n) * weight));
    }
    Ok(Value::Object(result))
}

/// Port of `_cosine` (`src/zkc/routing.py:157`).
///
/// Norms are summed in map insertion order, matching Python's dict values.
/// The original intersects with a hash-salted `set`; for three or more common
/// keys the addition order (and thus the last float bit) is not stable across
/// processes, so this port sorts the common keys for a deterministic result.
pub fn cosine(a: Value, b: Value) -> Result<Value, String> {
    let a = want_f64_map(&a, "a")?;
    let b = want_f64_map(&b, "b")?;
    let mut common: Vec<&String> = a.keys().filter(|key| b.contains_key(*key)).collect();
    if common.is_empty() {
        return Ok(json!(0.0));
    }
    common.sort();
    let dot: f64 = common
        .iter()
        .map(|key| number(&a[*key]) * number(&b[*key]))
        .sum();
    let na: f64 = a.values().map(number).map(|v| v * v).sum::<f64>().sqrt();
    let nb: f64 = b.values().map(number).map(|v| v * v).sum::<f64>().sqrt();
    if na == 0.0 || nb == 0.0 {
        return Ok(json!(0.0));
    }
    Ok(json!(dot / (na * nb)))
}
