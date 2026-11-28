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

/// pg.py `search_by_embedding`: cosine `<=>` top-k over the whitelisted vector column.
async fn run_embedding(dsn: &str, p: &Value) -> Result<Vec<Value>, String> {
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect: {e}"))?;

    // EMBEDDING_COLUMNS whitelist (interpolated into SQL, matching pg.py).
    let column = match p.get("column").and_then(Value::as_str) {
        Some(c @ ("embedding" | "embedding_4096")) => c.to_string(), // recorded-literal: pg.py EMBEDDING_COLUMNS
        _ => {
            let shown = p.get("column").and_then(Value::as_str).unwrap_or_default();
            pool.close().await;
            return Err(format!("invalid embedding column: '{shown}'"));
        }
    };
    let vector = p.get("vector").and_then(Value::as_array).cloned().unwrap_or_default();
    let vsql = format!(
        "[{}]",
        vector.iter().filter_map(as_num).map(|x| x.to_string()).collect::<Vec<_>>().join(",")
    );
    let include_archived = p.get("include_archived").and_then(Value::as_bool).unwrap_or(false);
    let arch = if include_archived { "" } else { "AND archived_at IS NULL" };
    let k = p.get("k").and_then(as_num_i64).unwrap_or(1).max(1);

    let sql = format!(
        "SELECT id::text, round((1 - ({column} <=> $1::vector))::numeric, 4)::float8 AS sim \
         FROM public.node WHERE {column} IS NOT NULL AND deleted_at IS NULL {arch} \
         ORDER BY {column} <=> $1::vector LIMIT $2"
    );
    let rows = sqlx::query(&sql)
        .bind(vsql)
        .bind(k)
        .fetch_all(&pool)
        .await
        .map_err(|e| format!("embedding query: {e}"))?;
    pool.close().await;

    let hits = rows
        .iter()
        .map(|r| {
            let mut o = Map::new();
            o.insert("id".into(), json!(r.get::<String, _>("id")));
            o.insert("sim".into(), json!(r.get::<f64, _>("sim")));
            Value::Object(o)
        })
        .collect();
    Ok(hits)
}

fn as_num(v: &Value) -> Option<f64> {
    v.as_f64().or_else(|| match v {
        Value::Object(o) if o.len() == 1 => {
            let (k, inner) = o.iter().next()?;
            if matches!(k.as_str(), "$float" | "$int") {
                inner.as_str()?.parse::<f64>().ok()
            } else {
                None
            }
        }
        _ => None,
    })
}
fn as_num_i64(v: &Value) -> Option<i64> {
    v.as_f64().map(|x| x as i64)
}

/// `zkc_query` handler business payload: structured search (`pg.py::search`, encoder-less ⇒
/// structured-only, created_desc) joined with each node's evidence_refs union (sorted distinct).
async fn run_mcp_query(dsn: &str, p: &Value) -> Result<Vec<Value>, String> {
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect: {e}"))?;
    let q = p.get("query").and_then(Value::as_str).unwrap_or("").to_string();
    let limit = p.get("limit").and_then(as_num_i64).unwrap_or(20).max(1);

    let sql = "SELECT n.id::text AS node_id, n.title, n.track::text, \
       round(COALESCE(n.decay_score, 0)::numeric, 3)::float8 AS decay, \
       ARRAY(SELECT DISTINCT e FROM (SELECT unnest(mc.evidence_refs::text[]) AS e \
             FROM public.meta_claim mc WHERE n.id = ANY(mc.evidence_refs)) t ORDER BY e) AS refs \
       FROM public.node n WHERE n.deleted_at IS NULL AND n.archived_at IS NULL \
         AND (n.title ILIKE $1 OR n.content ILIKE $1) \
       ORDER BY n.created_at DESC NULLS LAST LIMIT $2";
    let rows = sqlx::query(sql)
        .bind(format!("%{q}%")) // unescaped, matching pg.py's search ILIKE
        .bind(limit)
        .fetch_all(&pool)
        .await
        .map_err(|e| format!("query: {e}"))?;
    pool.close().await;

    let items = rows
        .iter()
        .map(|r| {
            let mut o = Map::new();
            o.insert("node_id".into(), json!(r.get::<String, _>("node_id")));
            o.insert("title".into(), json!(r.get::<Option<String>, _>("title")));
            o.insert("track".into(), json!(r.get::<Option<String>, _>("track")));
            o.insert("decay_score".into(), json!(r.get::<f64, _>("decay")));
            o.insert("source".into(), json!("structured"));
            o.insert("evidence_refs".into(), json!(r.get::<Vec<String>, _>("refs")));
            Value::Object(o)
        })
        .collect::<Vec<_>>();
    Ok(items)
}

/// `zkc_review_queue_list` payload: `pg.py::list_open` (resolved=false ORDER BY created_at), then
/// the handler's `action` filter and `[:limit]`. created_at via UTC `to_char` (matches the contract).
async fn run_rqlist(dsn: &str, p: &Value) -> Result<Vec<Value>, String> {
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect: {e}"))?;
    let rows = sqlx::query(
        "SELECT id::text, node_id::text, action, reason, \
         to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00' AS created_at \
         FROM public.review_queue WHERE resolved=false ORDER BY created_at",
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| format!("rqlist: {e}"))?;
    pool.close().await;

    let action = p.get("action").and_then(Value::as_str).map(str::to_string);
    let limit = p.get("limit").and_then(as_num_i64).unwrap_or(50).max(0) as usize;

    let mut items = Vec::new();
    for r in rows.iter() {
        let act: String = r.get("action");
        if let Some(a) = &action {
            if &act != a {
                continue;
            }
        }
        if items.len() >= limit {
            break;
        }
        let mut o = Map::new();
        o.insert("id".into(), json!(r.get::<String, _>("id")));
        o.insert("node_id".into(), json!(r.get::<Option<String>, _>("node_id")));
        o.insert("action".into(), json!(act));
        o.insert("reason".into(), json!(r.get::<Option<String>, _>("reason")));
        o.insert("resolved".into(), json!(false));
        o.insert("created_at".into(), json!(r.get::<Option<String>, _>("created_at")));
        items.push(Value::Object(o));
    }
    Ok(items)
}

/// `zkc_scheduler_due` payload: `pg.py::list_due_for_review` predicate (decay>=SURFACE & interval
/// & last_reviewed & last_reviewed+interval<=as_of & archived/deleted null), canonicalized by
/// node_id (pg.py has no ORDER BY), then [:limit].
async fn run_due(dsn: &str, p: &Value) -> Result<(Vec<Value>, usize), String> {
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect: {e}"))?;
    let as_of = p.get("as_of").and_then(Value::as_str).unwrap_or_default().to_string();
    let limit = p.get("limit").and_then(as_num_i64).unwrap_or(50).max(0);
    let surface = 0.6; // recorded-literal: tuning.SURFACE_THRESHOLD

    let sql = "SELECT id::text AS node_id, title, track::text, \
         round(COALESCE(decay_score, 0)::numeric, 3)::float8 AS decay, \
         (EXTRACT(EPOCH FROM review_interval) / 86400.0)::float8 AS interval_days, \
         interval_source \
       FROM public.node \
       WHERE decay_score >= $1 AND review_interval IS NOT NULL AND last_reviewed_at IS NOT NULL \
         AND (last_reviewed_at + review_interval) <= $2::timestamptz \
         AND archived_at IS NULL AND deleted_at IS NULL \
       ORDER BY id";
    let rows = sqlx::query(sql)
        .bind(surface)
        .bind(&as_of)
        .fetch_all(&pool)
        .await
        .map_err(|e| format!("due: {e}"))?;
    pool.close().await;

    let all = rows
        .iter()
        .map(|r| {
            let mut o = Map::new();
            o.insert("node_id".into(), json!(r.get::<String, _>("node_id")));
            o.insert("title".into(), json!(r.get::<Option<String>, _>("title")));
            o.insert("track".into(), json!(r.get::<Option<String>, _>("track")));
            o.insert("decay_score".into(), json!(r.get::<f64, _>("decay")));
            o.insert("review_interval_days".into(), json!(r.get::<f64, _>("interval_days")));
            o.insert("interval_source".into(), json!(r.get::<Option<String>, _>("interval_source")));
            Value::Object(o)
        })
        .collect::<Vec<_>>();
    let due_count = all.len();
    let mut items = all;
    items.truncate(limit as usize);
    Ok((items, due_count))
}

/// Front-door entry for `unit-search-sql` / `unit-mcp-query`. `None` → no DSN → original answers.
pub fn run(name: &str, args: &[Value], dsn: Option<&str>) -> Option<ExitCode> {
    let params = args.first().cloned().unwrap_or(Value::Null);
    // private_claims denial needs no DB (allow_private_claims is always false for this entry).
    if name == "query" {
        let scope = params.get("scope").and_then(Value::as_str).unwrap_or("public");
        if scope == "private_claims" {
            let denied = json!({
                "denied": true, "items": [], "scope": scope,
                "reason": "私人 claim 默认脱敏；未获显式授权不返回隐私字段", // recorded-literal: handlers.py
            });
            println!("{}", serde_json::to_string_pretty(&denied).unwrap_or_default());
            return Some(ExitCode::SUCCESS);
        }
    }
    let dsn = dsn?;
    let rt = match tokio::runtime::Builder::new_current_thread().enable_all().build() {
        Ok(rt) => rt,
        Err(e) => return Some(emit_err(format!("runtime: {e}"))),
    };
    match name {
        "structured" => match rt.block_on(run_query(dsn, &params)) {
            Ok(hits) => {
                let count = hits.len();
                let out = json!({
                    "hits": hits, "structured_count": count, "embedding_count": 0,
                    "degraded": false, "degrade_reason": Value::Null,
                });
                println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
                Some(ExitCode::SUCCESS)
            }
            Err(e) => Some(emit_err(e)),
        },
        "embedding" => match rt.block_on(run_embedding(dsn, &params)) {
            Ok(hits) => {
                let count = hits.len();
                let out = json!({ "hits": hits, "count": count });
                println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
                Some(ExitCode::SUCCESS)
            }
            Err(e) => Some(emit_err(e)),
        },
        "query" => {
            let scope = params.get("scope").and_then(Value::as_str).unwrap_or("public").to_string();
            match rt.block_on(run_mcp_query(dsn, &params)) {
                Ok(items) => {
                    let count = items.len();
                    let out = json!({
                        "items": items, "count": count, "scope": scope, "degraded": false,
                        "privacy": "node.content / meta_claim.statement 不出现在响应体", // recorded-literal: handlers.py
                    });
                    println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
                    Some(ExitCode::SUCCESS)
                }
                Err(e) => Some(emit_err(e)),
            }
        }
        "list" => match rt.block_on(run_rqlist(dsn, &params)) {
            Ok(items) => {
                let count = items.len();
                let out = json!({ "items": items, "count": count, "include_resolved": false });
                println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
                Some(ExitCode::SUCCESS)
            }
            Err(e) => Some(emit_err(e)),
        },
        "due" => {
            let as_of = params.get("as_of").and_then(Value::as_str).unwrap_or("").to_string();
            match rt.block_on(run_due(dsn, &params)) {
                Ok((items, due_count)) => {
                    let out = json!({
                        "as_of": as_of, "items": items, "due_count": due_count,
                        "semantics": "注意力预算：该关注清单（decay 到期且需投入注意力）", // recorded-literal: handlers.py
                    });
                    println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
                    Some(ExitCode::SUCCESS)
                }
                Err(e) => Some(emit_err(e)),
            }
        }
        other => Some(emit_err(format!("unknown search-sql fn: {other}"))),
    }
}

fn emit_err(message: String) -> ExitCode {
    println!("{}", json!({ "error": message }));
    ExitCode::from(1)
}
