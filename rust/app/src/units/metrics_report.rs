//! Rust implementation of the `metrics-snapshot` CLI's computation path.
//!
//! This is the A-path glue wired behind the front door: it replaces
//! `scripts/metrics_snapshot.py` → `metrics_report(store)` → `build_report_dict()`.
//! The oracle is the recorded CLI black-box case (`app record`, Python original),
//! replayed with `app replay --build` against this binary. Constants mirror
//! `zkc.tuning` seed values (1-26 CALIBRATED): four weights = 0.25, method target = 10,
//! ROT threshold = 0.9. They are `recorded-literal` from the tuning registry, not
//! re-calibrated here.

use std::collections::HashSet;
use std::process::ExitCode;

use serde_json::{Map, Value, json};
use sqlx::Row;
use sqlx::postgres::PgPoolOptions;

/// Inputs mirror `zkc.repository.models.MetricInputs` (the storage-agnostic snapshot).
struct MetricInputs {
    nodes: Vec<(String, String, f64, bool)>, // (id, track, decay, archived)
    edges: Vec<(String, String, String)>,    // (src, dst, kind)
    claim_evidence: Vec<Vec<String>>,
    artifact_evidence: Vec<Vec<String>>,
    citations: Vec<String>,
}

impl MetricInputs {
    fn empty() -> Self {
        Self {
            nodes: vec![],
            edges: vec![],
            claim_evidence: vec![],
            artifact_evidence: vec![],
            citations: vec![],
        }
    }
}

/// `Storage.load_metric_inputs()` for the PG backend — the exact 5 queries from
/// `src/zkc/repository/pg.py::load_metric_inputs`, with UUIDs cast to text so we
/// only need sqlx's text decoding (no `uuid` feature) and results stay comparable.
async fn load_pg_inputs(dsn: &str) -> Result<MetricInputs, String> {
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(dsn)
        .await
        .map_err(|e| format!("connect: {e}"))?;

    let node_rows = sqlx::query(
        // decay_score is PG `real` (float32). psycopg decodes it to the exact
        // decimal the client sees (0.9 -> Python 0.9), while `::float8` expands
        // the float32 bits to 0.8999999761581421 and breaks the `>= 0.9` decay
        // boundary. Cast via `numeric` to preserve the displayed decimal, matching
        // the Python oracle (caught by the `decay-boundary` recorded case).
        "SELECT id::text, track::text, COALESCE(decay_score, 0)::numeric::float8, \
         (archived_at IS NOT NULL) \
         FROM public.node",
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| format!("node query: {e}"))?;
    let nodes: Vec<(String, String, f64, bool)> = node_rows
        .iter()
        .map(|r| {
            (
                r.get::<String, _>(0),
                r.get::<String, _>(1),
                r.get::<f64, _>(2),
                r.get::<bool, _>(3),
            )
        })
        .collect();

    let edge_rows = sqlx::query("SELECT src::text, dst::text, kind FROM public.edge")
        .fetch_all(&pool)
        .await
        .map_err(|e| format!("edge query: {e}"))?;
    let edges: Vec<(String, String, String)> = edge_rows
        .iter()
        .map(|r| {
            (
                r.get::<String, _>(0),
                r.get::<String, _>(1),
                r.get::<String, _>(2),
            )
        })
        .collect();

    let claim_rows = sqlx::query(
        "SELECT evidence_refs::text[] FROM public.meta_claim WHERE evidence_refs IS NOT NULL",
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| format!("claim query: {e}"))?;
    // psycopg returns uuid[] as a list; sqlx decodes text[] to Vec<String>. Both are
    // sets of UUID strings for our purposes (evidence_refs is never null here).
    let claim_evidence: Vec<Vec<String>> = claim_rows
        .iter()
        .map(|r| r.get::<Vec<String>, _>(0))
        .collect();

    let artifact_rows = sqlx::query(
        "SELECT ma.evidence_refs::text[] FROM public.modeling_artifact ma \
         JOIN public.transform t ON t.id = ma.produced_by \
         WHERE t.kind = 'combine' AND ma.evidence_refs IS NOT NULL",
    )
    .fetch_all(&pool)
    .await
    .map_err(|e| format!("artifact query: {e}"))?;
    let artifact_evidence: Vec<Vec<String>> = artifact_rows
        .iter()
        .map(|r| r.get::<Vec<String>, _>(0))
        .collect();

    let citation_rows = sqlx::query("SELECT cited_claim_id::text FROM public.citation")
        .fetch_all(&pool)
        .await
        .map_err(|e| format!("citation query: {e}"))?;
    let citations: Vec<String> = citation_rows
        .iter()
        .map(|r| r.get::<String, _>(0))
        .collect();

    pool.close().await;
    Ok(MetricInputs {
        nodes,
        edges,
        claim_evidence,
        artifact_evidence,
        citations,
    })
}

fn connection_density(inp: &MetricInputs) -> f64 {
    let dyn_ids: HashSet<&str> = inp
        .nodes
        .iter()
        .filter(|(_, track, _, _)| track == "dynamic")
        .map(|(id, _, _, _)| id.as_str())
        .collect();
    if dyn_ids.is_empty() {
        return 0.0;
    }
    let mut connected: HashSet<&str> = HashSet::new();
    for (src, dst, kind) in &inp.edges {
        if kind == "reverse_link" || kind == "derived_from" {
            if dyn_ids.contains(src.as_str()) {
                connected.insert(src.as_str());
            }
            if dyn_ids.contains(dst.as_str()) {
                connected.insert(dst.as_str());
            }
        }
    }
    connected.len() as f64 / dyn_ids.len() as f64
}

fn reuse_rate(inp: &MetricInputs) -> (f64, f64) {
    let total = inp.claim_evidence.len();
    if total == 0 {
        return (0.0, 0.0);
    }
    let cited: HashSet<&str> = inp.citations.iter().map(|s| s.as_str()).collect();
    (
        cited.len() as f64 / total as f64,
        inp.citations.len() as f64 / total as f64,
    )
}

fn methodology_output(inp: &MetricInputs) -> i64 {
    inp.artifact_evidence.len() as i64
}

fn decay_controllability(inp: &MetricInputs, rot: f64) -> f64 {
    let expired: HashSet<&str> = inp
        .nodes
        .iter()
        .filter(|(_, track, decay, _)| track == "dynamic" && *decay >= rot)
        .map(|(id, _, _, _)| id.as_str())
        .collect();
    if expired.is_empty() {
        return 0.0;
    }
    let mut handled: HashSet<&str> = HashSet::new();
    for refs in &inp.claim_evidence {
        for r in refs {
            handled.insert(r.as_str());
        }
    }
    for refs in &inp.artifact_evidence {
        for r in refs {
            handled.insert(r.as_str());
        }
    }
    for (id, _, _, archived) in &inp.nodes {
        if *archived {
            handled.insert(id.as_str());
        }
    }
    expired.intersection(&handled).count() as f64 / expired.len() as f64
}

/// Python `round(x, 4)` — round half to even (banker's rounding), byte-identical to
/// CPython's float `__round__` for the finite values this report produces.
fn py_round4(x: f64) -> f64 {
    let scale = 10_000.0_f64;
    let shifted = x * scale;
    let floor = shifted.floor();
    let frac = shifted - floor;
    let rounded = if (frac - 0.5).abs() < f64::EPSILON {
        // half → round to even
        let base = floor as i64;
        if base % 2 == 0 { floor } else { floor + 1.0 }
    } else {
        shifted.round()
    };
    rounded / scale
}

/// `build_report_dict()` output: a JSON object with the original's key order and
/// `round(v, 4)` on the five floats (methodology_output stays int).
fn report_json(inp: &MetricInputs) -> String {
    let cd = py_round4(connection_density(inp));
    let (rr, per) = reuse_rate(inp);
    let rr = py_round4(rr);
    let per = py_round4(per);
    let mo = methodology_output(inp);
    let dc = py_round4(decay_controllability(inp, 0.9)); // recorded-literal: tuning.ROT_THRESHOLD
    // Default weights (0.25 x4) + target 10 are the 1-26 CALIBRATED seed.
    let mo_norm = if 10.0 != 0.0 {
        (mo as f64 / 10.0).min(1.0)
    } else {
        0.0
    }; // recorded-literal: tuning.METRIC_METHOD_TARGET
    let cf =
        py_round4(0.25 * cd_raw(inp) + 0.25 * rr_raw(inp) + 0.25 * mo_norm + 0.25 * dc_raw(inp));
    // recorded-literal: tuning.METRIC_W_DENSITY/REUSE/METHOD/DECAY = 0.25 (1-26 seed)

    let mut obj = Map::new();
    obj.insert("connection_density".into(), json!(cd));
    obj.insert("reuse_rate".into(), json!(rr));
    obj.insert("citations_per_claim".into(), json!(per));
    obj.insert("methodology_output".into(), json!(mo));
    obj.insert("decay_controllability".into(), json!(dc));
    obj.insert("compounding_factor".into(), json!(cf));
    serde_json::to_string_pretty(&Value::Object(obj)).unwrap_or_else(|_| "{}".to_string())
}

// Raw (unrounded) values: Python's `build_report` feeds compounding_factor the
// unrounded cd/rr/dc, then rounds only in build_report_dict.
fn cd_raw(inp: &MetricInputs) -> f64 {
    connection_density(inp)
}
fn rr_raw(inp: &MetricInputs) -> f64 {
    reuse_rate(inp).0
}
fn dc_raw(inp: &MetricInputs) -> f64 {
    decay_controllability(inp, 0.9) // recorded-literal: tuning.ROT_THRESHOLD
}

/// Handle the `--storage <kind>` case. Any other argv declines to the original via
/// `None`, so the front door keeps answering cases we have not ported.
pub fn dispatch(storage: &str, dsn: Option<&str>) -> Option<ExitCode> {
    match storage {
        "memory" => {
            // memory fake is always empty (`get_storage("memory")` fresh instance).
            println!("{}", report_json(&MetricInputs::empty()));
            Some(ExitCode::SUCCESS)
        }
        "pg" => {
            let dsn = dsn?; // no DSN → let original use its default backend
            match tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
            {
                Ok(rt) => match rt.block_on(load_pg_inputs(dsn)) {
                    Ok(inp) => {
                        println!("{}", report_json(&inp));
                        Some(ExitCode::SUCCESS)
                    }
                    Err(e) => {
                        eprintln!("metrics-snapshot (rust): {e}");
                        Some(ExitCode::from(1))
                    }
                },
                Err(e) => {
                    eprintln!("metrics-snapshot (rust): runtime: {e}");
                    Some(ExitCode::from(1))
                }
            }
        }
        _ => None,
    }
}
