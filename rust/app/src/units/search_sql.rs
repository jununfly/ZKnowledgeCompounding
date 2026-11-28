//! sqlx A-path for the STRUCTURED search contract (`scripts/zkc_search.py --json`), PG backend.
//! Mirrors `pg.py::PgNodeRepository.search` + the zkc_search.py serialization:
//! deleted/archived visibility, `track` equality, `q` ILIKE `%q%` (unescaped, matching pg.py),
//! decay range via `COALESCE(decay_score,0)`, `_SEARCH_ORDERS` `NULLS LAST`, `max(1,limit)`.
//!
//! Parity decisions (recorded-literal to the Python contract, not re-derived policy):
//!   * `track::text` — the column is a `track_kind` enum; psycopg returns the label str, so compare
//!     and project as text (same result set as pg.py's `track = %(track)s`).
//!   * `created_at` = `to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') || '+00:00'`
//!     → session-tz-independent, byte-matches the contract's UTC `strftime`.
//!   * `decay` = `round(COALESCE(decay_score,0)::numeric, 4)::float8` — collapses PG `real` float32
//!     display noise (cf. metrics_report's `::numeric` workaround).
//! DSN comes from `ZKC_PG_DSN`; unset → `None` → the original answers (like metrics_report).

use std::process::ExitCode;

use serde_json::{Map, Value, json};
use sqlx::Row;
use sqlx::postgres::PgPoolOptions;

const SELECT_COLS: &str =
    "id::text, title, content, track::text, round(COALESCE(decay_score, 0)::numeric, 4)::float8 AS decay, \
     to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00' AS created_at";

/// `pg.py::_SEARCH_ORDERS`.
fn order_clause(order: &str) -> Option<&'static str> {
    match order {
        // recorded-literal: pg.py _SEARCH_ORDERS
        "created_desc" => Some("ORDER BY created_at DESC NULLS LAST"),
        "created_asc" => Some("ORDER BY created_at ASC NULLS LAST"),
        "decay_desc" => Some("ORDER BY decay_score DESC NULLS LAST"),
        _ => None,
    }
}

async fn run_query(dsn: &str, p: &Value) -> Result<Vec<Value>, String> {
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect: {e}"))?;

    let get = |key: &str| p.get(key).cloned().unwrap_or(Value::Null);
    let track = get("track").as_str().map(str::to_string);
    let q = get("q").as_str().filter(|s| !s.is_empty()).map(str::to_string);
    let dmin = get("decay_min").as_f64();
    let dmax = get("decay_max").as_f64();
    let order = get("order").as_str().unwrap_or("created_desc").to_string();
    let include_archived = get("include_archived").as_bool().unwrap_or(false);
    let limit = get("limit").as_f64().unwrap_or(50.0).max(1.0) as i64;

    let mut sql = format!("SELECT {SELECT_COLS} FROM public.node WHERE deleted_at IS NULL");
    if !include_archived {
        sql.push_str(" AND archived_at IS NULL");
    }
    // sqlx binds positionally; distinct params numbered in bind order. `$n` may be reused in SQL
    // (the ILIKE clause references it twice) but is bound once.
    let mut n = 0usize;
    let mut next = || {
        n += 1;
        n
    };
    if track.is_some() {
        sql.push_str(&format!(" AND track::text = ${}", next()));
    }
    if q.is_some() {
        let p1 = next();
        sql.push_str(&format!(" AND (title ILIKE ${p1} OR content ILIKE ${p1})"));
    }
    if dmin.is_some() {
        sql.push_str(&format!(" AND COALESCE(decay_score, 0) >= ${}", next()));
    }
    if dmax.is_some() {
        sql.push_str(&format!(" AND COALESCE(decay_score, 0) <= ${}", next()));
    }
    let ord = order_clause(&order).ok_or_else(|| format!("invalid order: {order}"))?;
    sql.push_str(&format!(" {ord} LIMIT ${}", next()));

    let mut query = sqlx::query(&sql);
    if let Some(t) = &track {
        query = query.bind(t.clone());
    }
    if let Some(needle) = &q {
        query = query.bind(format!("%{needle}%")); // unescaped, matching pg.py
    }
    if let Some(m) = dmin {
        query = query.bind(m);
    }
    if let Some(m) = dmax {
        query = query.bind(m);
    }
    query = query.bind(limit);

    let rows = query
        .fetch_all(&pool)
        .await
        .map_err(|e| format!("search query: {e}"))?;
    pool.close().await;

    let hits = rows
        .iter()
        .map(|r| {
            let mut o = Map::new();
            o.insert("id".into(), json!(r.get::<String, _>("id")));
            o.insert("title".into(), json!(r.get::<Option<String>, _>("title")));
            o.insert("content".into(), json!(r.get::<Option<String>, _>("content")));
            o.insert("track".into(), json!(r.get::<Option<String>, _>("track")));
            o.insert("decay_score".into(), json!(r.get::<f64, _>("decay")));
            o.insert("created_at".into(), json!(r.get::<Option<String>, _>("created_at")));
            o.insert("source".into(), json!("structured"));
            o.insert("sim".into(), Value::Null);
            Value::Object(o)
        })
        .collect();
    Ok(hits)
}

/// Front-door entry for `unit-search-sql`. `None` → no DSN configured → the original answers.
pub fn run(name: &str, args: &[Value], dsn: Option<&str>) -> Option<ExitCode> {
    if name != "structured" {
        return Some(emit_err(format!("unknown search-sql fn: {name}")));
    }
    let dsn = dsn?;
    let params = args.first().cloned().unwrap_or(Value::Null);
    let built = tokio::runtime::Builder::new_current_thread().enable_all().build();
    match built {
        Ok(rt) => match rt.block_on(run_query(dsn, &params)) {
            Ok(hits) => {
                let count = hits.len();
                let out = json!({
                    "hits": hits,
                    "structured_count": count,
                    "embedding_count": 0,
                    "degraded": false,
                    "degrade_reason": Value::Null,
                });
                println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
                Some(ExitCode::SUCCESS)
            }
            Err(e) => Some(emit_err(e)),
        },
        Err(e) => Some(emit_err(format!("runtime: {e}"))),
    }
}

fn emit_err(message: String) -> ExitCode {
    println!("{}", json!({ "error": message }));
    ExitCode::from(1)
}
