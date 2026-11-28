//! The Rust port of `spikes/spike-30-search-structured/pure_bridge.py`.
//!
//! `filter_sort_nodes` reproduces `MemoryNodeRepository.search` (PG-isomorphic reference for the
//! pg.py SQL path): tombstone/archive visibility, `track` equality, decay range (null→0.0),
//! case-insensitive `q` substring over `title + "\n" + content`, order validation, stable sort, and
//! `max(1, limit)` truncation. `created_at` is canonical UTC-ISO here, so lexicographic == chronological
//! (null → `_MIN_DT`); non-UTC/naive datetimes and non-ASCII `.lower()` casefold edges are out of scope.

#![forbid(unsafe_code)]

use serde_json::{Map, Value, json};

const MIN_DT: &str = "0001-01-01T00:00:00+00:00"; // _MIN_DT sentinel for null created_at

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

fn is_set(node: &Value, key: &str) -> bool {
    node.get(key).and_then(Value::as_bool).unwrap_or(false)
}

fn opt_str<'a>(v: &'a Value, key: &str) -> Option<&'a str> {
    v.get(key).and_then(Value::as_str)
}

/// Port of `filter_sort_nodes` (`spikes/spike-30-search-structured/pure_bridge.py:32`).
pub fn filter_sort_nodes(
    nodes: Value,
    track: Value,
    q: Value,
    decay_min: Value,
    decay_max: Value,
    include_archived: Value,
    order: Value,
    limit: Value,
) -> Result<Value, String> {
    let order = order.as_str().unwrap_or_default();
    if !matches!(order, "created_desc" | "created_asc" | "decay_desc") {
        // recorded-literal: memory.py valid order set ("created_desc"|"created_asc"|"decay_desc")
        return Err(format!("invalid order: {order}"));
    }
    let list = nodes.as_array().ok_or("TypeError: nodes is not a list")?;
    let tf = track.as_str();
    // Python: ql = q.lower() if q else None (empty string → no filter).
    let ql = q.as_str().filter(|s| !s.is_empty()).map(str::to_lowercase);
    let include_archived = include_archived.as_bool().unwrap_or(false);
    let dmin = as_f64(&decay_min);
    let dmax = as_f64(&decay_max);
    let limit = as_f64(&limit).unwrap_or(1.0) as i64;
    let limit = limit.max(1) as usize;

    let rows: Vec<Row> = list
        .iter()
        .filter(|n| {
            !is_set(n, "deleted")
                && (include_archived || !is_set(n, "archived"))
                && tf.is_none_or(|tf| opt_str(n, "track").unwrap_or("unrouted") == tf)
                && (dmin.is_none_or(|m| decay(n) >= m))
                && (dmax.is_none_or(|m| decay(n) <= m))
                && ql.as_ref().is_none_or(|needle| {
                    let title = opt_str(n, "title").unwrap_or("");
                    let content = opt_str(n, "content").unwrap_or("");
                    format!("{title}\n{content}")
                        .to_lowercase()
                        .contains(needle.as_str())
                })
        })
        .map(|n| Row {
            id: opt_str(n, "id").unwrap_or_default().to_string(),
            title: opt_str(n, "title").unwrap_or("").to_string(),
            node_track: opt_str(n, "track").unwrap_or("unrouted").to_string(),
            decay: decay(n),
            created: opt_str(n, "created_at").map(str::to_string),
        })
        .collect();

    let mut rows = rows;
    match order {
        "created_asc" => rows.sort_by(|a, b| key(&a.created).cmp(key(&b.created))),
        "decay_desc" => rows.sort_by(|a, b| {
            b.decay
                .partial_cmp(&a.decay)
                .unwrap_or(std::cmp::Ordering::Equal)
        }),
        _ => rows.sort_by(|a, b| key(&b.created).cmp(key(&a.created))),
    }
    rows.truncate(limit);

    Ok(Value::Array(
        rows.into_iter()
            .map(|r| {
                let mut o = Map::new();
                o.insert("id".into(), json!(r.id));
                o.insert("title".into(), json!(r.title));
                o.insert("track".into(), json!(r.node_track));
                o.insert("decay_score".into(), json!(r.decay));
                o.insert(
                    "created_at".into(),
                    r.created.map_or(Value::Null, |c| json!(c)),
                );
                Value::Object(o)
            })
            .collect(),
    ))
}

// memory: n.decay_score defaults 0.0; the slice maps null→0.0 via `or 0.0`.
fn decay(n: &Value) -> f64 {
    n.get("decay_score")
        .filter(|v| !v.is_null())
        .and_then(as_f64)
        .unwrap_or(0.0)
}

struct Row {
    id: String,
    title: String,
    node_track: String,
    decay: f64,
    created: Option<String>,
}

fn key(created: &Option<String>) -> &str {
    created.as_deref().unwrap_or(MIN_DT)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn filter(nodes: Value, order: &str, limit: Value) -> Vec<String> {
        let r = filter_sort_nodes(
            nodes,
            Value::Null,
            Value::Null,
            Value::Null,
            Value::Null,
            json!(false),
            json!(order),
            limit,
        )
        .unwrap();
        r.as_array()
            .unwrap()
            .iter()
            .map(|x| x["title"].as_str().unwrap().to_string())
            .collect()
    }

    #[test]
    fn created_ordering() {
        let nodes = json!([
            {"id":"a","title":"n1","created_at":"2026-01-01T00:00:00+00:00"},
            {"id":"b","title":"n2","created_at":"2026-03-01T00:00:00+00:00"},
            {"id":"c","title":"n3","created_at":"2026-02-01T00:00:00+00:00"}
        ]);
        assert_eq!(
            filter(nodes.clone(), "created_desc", json!(10)),
            vec!["n2", "n3", "n1"]
        );
        assert_eq!(filter(nodes, "created_asc", json!(2)), vec!["n1", "n3"]);
    }

    #[test]
    fn decay_and_invalid_order() {
        let nodes = json!([{"id":"a","title":"x","decay_score":0.3},{"id":"b","title":"y","decay_score":0.8}]);
        let r = filter_sort_nodes(
            nodes,
            Value::Null,
            Value::Null,
            json!(0.5),
            Value::Null,
            json!(false),
            json!("created_desc"),
            json!(10),
        )
        .unwrap();
        assert_eq!(r.as_array().unwrap().len(), 1);
        assert_eq!(
            filter_sort_nodes(
                json!([]),
                Value::Null,
                Value::Null,
                Value::Null,
                Value::Null,
                json!(false),
                json!("bogus"),
                json!(10)
            )
            .unwrap_err(),
            "invalid order: bogus"
        );
    }
}
