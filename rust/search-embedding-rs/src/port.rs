//! The Rust port of `spikes/spike-29-search-embedding/pure_bridge.py`.
//!
//! `search_embedding_knn` reproduces `MemoryNodeRepository.search_by_embedding` (the PG-isomorphic
//! reference for the pgvector `<=>` path): cosine similarity over each node's embedding column,
//! tombstone/archive visibility, `column` validation, and a stable descending top-k by similarity.
//!
//! The cosine arithmetic mirrors Python's `sum(x*x for x in a)` / `sum(x*y for x,y in zip(a,b))`
//! EXACTLY: left-to-right fold from 0.0 and `zip` truncation to the shorter list, so the resulting
//! `f64` bits (and their JSON repr) match the recorded oracle. `reverse=True` sorting is stable
//! (ties keep original insertion order) — Rust `sort_by` is also stable.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

/// Decode a recorded number: a plain JSON number, or a `{"$float": "..."}` / `{"$int": "..."}`
/// marker emitted by the Python recording bridge.
fn as_f64(v: &Value) -> Option<f64> {
    match v {
        Value::Number(n) => n.as_f64(),
        Value::Bool(b) => Some(if *b { 1.0 } else { 0.0 }),
        Value::Object(o) if o.len() == 1 => {
            let (k, inner) = o.iter().next()?;
            if matches!(k.as_str(), "$float" | "$int") {
                inner.as_str()?.parse::<f64>().ok()
            } else {
                None
            }
        }
        _ => None,
    }
}

fn to_f64_vec(v: &Value) -> Vec<f64> {
    v.as_array()
        .map(|arr| arr.iter().filter_map(as_f64).collect())
        .unwrap_or_default()
}

/// memory.py `_cos`: sqrt(sum sq) norms; zero norm → 0.0; dot via zip (shorter length).
fn cos(a: &[f64], b: &[f64]) -> f64 {
    let na = a.iter().map(|x| x * x).sum::<f64>().sqrt();
    let nb = b.iter().map(|x| x * x).sum::<f64>().sqrt();
    if na == 0.0 || nb == 0.0 {
        return 0.0;
    }
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum::<f64>() / (na * nb)
}

/// Port of `search_embedding_knn` (`spikes/spike-29-search-embedding/pure_bridge.py:37`).
pub fn search_embedding_knn(
    nodes: Value,
    vector: Value,
    k: Value,
    include_archived: Value,
    column: Value,
) -> Result<Value, String> {
    // EMBEDDING_COLUMNS = {"embedding", "embedding_4096"}; invalid → ValueError (bare msg; the
    // PyO3 bridge raises it as ValueError, and column!r in Python is the single-quoted repr).
    let col = column
        .as_str()
        .ok_or_else(|| "TypeError: column must be a str".to_string())?;
    if col != "embedding" && col != "embedding_4096" {
        return Err(format!("invalid embedding column: '{col}'"));
    }

    let query = to_f64_vec(&vector);
    let include_archived = include_archived.as_bool().unwrap_or(false);
    let k = as_f64(&k).map(|v| v as i64).unwrap_or(1).max(1) as usize;

    let list = nodes
        .as_array()
        .ok_or_else(|| "TypeError: nodes is not a list".to_string())?;

    // (id, sim) collected in insertion order, then stable-sorted descending by sim.
    let mut hits: Vec<(String, f64)> = Vec::new();
    for n in list {
        if n.get("deleted").and_then(Value::as_bool).unwrap_or(false) {
            continue; // tombstone hidden regardless of include_archived
        }
        if !include_archived && n.get("archived").and_then(Value::as_bool).unwrap_or(false) {
            continue;
        }
        let id = match n.get("id").and_then(Value::as_str) {
            Some(id) => id.to_string(),
            None => continue,
        };
        let emb = match n.get(col) {
            Some(v) if !v.is_null() => to_f64_vec(v),
            _ => continue, // embedding column null → skipped
        };
        hits.push((id, cos(&query, &emb)));
    }

    hits.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    hits.truncate(k);

    let out = hits
        .into_iter()
        .map(|(id, sim)| {
            let mut o = Map::new();
            o.insert("id".into(), json!(id));
            o.insert("sim".into(), json!(sim));
            Value::Object(o)
        })
        .collect();
    Ok(Value::Array(out))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn sorted_desc_and_zero_norm() {
        let nodes = json!([
            {"id": "a", "embedding": [1.0, 0.0]},
            {"id": "b", "embedding": [0.0, 1.0]}
        ]);
        let r = search_embedding_knn(
            nodes,
            json!([1.0, 0.0]),
            json!(5),
            json!(false),
            json!("embedding"),
        )
        .unwrap();
        assert_eq!(r[0]["id"], json!("a"));
        assert_eq!(r[0]["sim"], json!(1.0));
        assert_eq!(r[1]["sim"], json!(0.0));
    }

    #[test]
    fn visibility_and_column_validation() {
        let nodes = json!([
            {"id": "d", "embedding": [1.0, 0.0], "deleted": true},
            {"id": "a", "embedding": [1.0, 0.0], "archived": true}
        ]);
        let r = search_embedding_knn(
            nodes.clone(),
            json!([1.0, 0.0]),
            json!(5),
            json!(false),
            json!("embedding"),
        )
        .unwrap();
        assert!(r.as_array().unwrap().is_empty()); // tombstone + archived both hidden
        let r = search_embedding_knn(
            nodes,
            json!([1.0, 0.0]),
            json!(5),
            json!(true),
            json!("embedding"),
        )
        .unwrap();
        assert_eq!(r[0]["id"], json!("a")); // archived shown
        assert_eq!(
            search_embedding_knn(
                json!([]),
                json!([1.0]),
                json!(5),
                json!(false),
                json!("bad")
            )
            .unwrap_err(),
            "invalid embedding column: 'bad'"
        );
    }
}
