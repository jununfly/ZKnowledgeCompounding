//! Wiring for the `metrics-snapshot` front door plus twelve library-unit commands.
//!
//! Hand-merged after `rust-anything app wire`: the generated `mod.rs` is rewritten
//! on every wire and drops `metrics_report`, so the wire-generated glue modules
//! are kept here together with the hand-written metrics route. The wire command
//! was still run for each unit; it supplied the Cargo dependencies,
//! `rust-anything.json` unit records and the kill-switch names.
//!
//! Kill switch: `RUST_ANYTHING_UNIT_<UNIT>=original` sends a unit to the Python
//! original through `oracle.py` (a process-only adapter, not production code).

use std::ffi::OsString;
use std::path::PathBuf;
use std::process::{Command, ExitCode};

use clap::ArgMatches;
use serde_json::{Value, json};

mod artifact_shaping;
mod cross_source;
mod distill_parse;
mod injection_detection;
mod metrics_report;
mod percentile;
mod r14_judgment;
mod zkc_context_pure;
mod zkc_expiry_pure;
mod zkc_faithfulness_rubric;
mod zkc_routing_tfidf;
mod zkc_scheduling_interval;
mod zkc_transport;

fn sent_to_original(unit: &str) -> bool {
    std::env::var(format!("RUST_ANYTHING_UNIT_{unit}")).is_ok_and(|v| v == "original")
}

/// Parse the uniform library-unit protocol: `<fn> <json-array>`. The raw JSON
/// text is preserved so the kill switch can hand it to the Python oracle.
fn unit_args(matches: &ArgMatches) -> Result<(String, String, Vec<Value>), ExitCode> {
    let raw: Vec<String> = matches
        .get_many::<OsString>("args")
        .into_iter()
        .flatten()
        .map(|word| word.to_string_lossy().into_owned())
        .collect();
    if raw.len() != 2 {
        return Err(fail("usage: <fn> <json-array>"));
    }
    let args: Vec<Value> =
        serde_json::from_str(&raw[1]).map_err(|e| fail(format!("invalid JSON arguments: {e}")))?;
    Ok((raw[0].clone(), raw[1].clone(), args))
}

pub(crate) fn fail(message: impl AsRef<str>) -> ExitCode {
    println!("{}", json!({ "error": message.as_ref() }));
    ExitCode::from(1)
}

pub(crate) fn emit(result: Result<Value, String>) -> ExitCode {
    match result {
        Ok(value) => {
            println!("{}", json!({ "ok": value }));
            ExitCode::SUCCESS
        }
        Err(message) => fail(message),
    }
}

pub(crate) fn arg_value(values: &[Value], index: usize) -> Result<Value, ExitCode> {
    values
        .get(index)
        .cloned()
        .ok_or_else(|| fail(format!("arg {index}: missing")))
}

pub(crate) fn arg_str(values: &[Value], index: usize) -> Result<String, ExitCode> {
    values
        .get(index)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| fail(format!("arg {index}: expected string")))
}

pub(crate) fn arg_i64(values: &[Value], index: usize) -> Result<i64, ExitCode> {
    values
        .get(index)
        .and_then(Value::as_i64)
        .ok_or_else(|| fail(format!("arg {index}: expected integer")))
}

pub(crate) fn arg_f64(values: &[Value], index: usize) -> Result<f64, ExitCode> {
    values
        .get(index)
        .and_then(Value::as_f64)
        .ok_or_else(|| fail(format!("arg {index}: expected number")))
}

pub(crate) fn arg_strings(values: &[Value], index: usize) -> Result<Vec<String>, ExitCode> {
    let array = values
        .get(index)
        .and_then(Value::as_array)
        .ok_or_else(|| fail(format!("arg {index}: expected array of strings")))?;
    array
        .iter()
        .map(|item| {
            item.as_str()
                .map(str::to_string)
                .ok_or_else(|| fail(format!("arg {index}: expected array of strings")))
        })
        .collect()
}

pub(crate) fn arg_values(values: &[Value], index: usize) -> Result<Vec<Value>, ExitCode> {
    values
        .get(index)
        .and_then(Value::as_array)
        .cloned()
        .ok_or_else(|| fail(format!("arg {index}: expected array")))
}

fn original_unit(unit: &str, name: &str, raw: &str) -> ExitCode {
    let oracle = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("oracle.py");
    match Command::new("python3")
        .arg(oracle)
        .arg(unit)
        .arg(name)
        .arg(raw)
        .status()
    {
        Ok(status) => ExitCode::from((status.code().unwrap_or(1) & 0xff) as u8),
        Err(e) => fail(format!("cannot run Python oracle: {e}")),
    }
}

pub fn dispatch(command: &str, matches: &ArgMatches) -> Option<ExitCode> {
    match command {
        "unit-transport" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("ZKC_TRANSPORT") {
                Some(original_unit("transport", &name, &raw))
            } else {
                Some(zkc_transport::run(&name, &args))
            }
        }
        "unit-context" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("ZKC_CONTEXT_PURE") {
                Some(original_unit("context", &name, &raw))
            } else {
                Some(zkc_context_pure::run(&name, &args))
            }
        }
        "unit-expiry" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("ZKC_EXPIRY_PURE") {
                Some(original_unit("expiry", &name, &raw))
            } else {
                Some(zkc_expiry_pure::run(&name, &args))
            }
        }
        "unit-scheduling" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("ZKC_SCHEDULING_INTERVAL") {
                Some(original_unit("scheduling", &name, &raw))
            } else {
                Some(zkc_scheduling_interval::run(&name, &args))
            }
        }
        "unit-faithfulness" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("ZKC_FAITHFULNESS_RUBRIC") {
                Some(original_unit("faithfulness", &name, &raw))
            } else {
                Some(zkc_faithfulness_rubric::run(&name, &args))
            }
        }
        "unit-routing" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("ZKC_ROUTING_TFIDF") {
                Some(original_unit("routing", &name, &raw))
            } else {
                Some(zkc_routing_tfidf::run(&name, &args))
            }
        }
        "unit-cross-source" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("CROSS_SOURCE") {
                Some(original_unit("cross-source", &name, &raw))
            } else {
                Some(cross_source::run(&name, &args))
            }
        }
        "unit-distill" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("DISTILL_PARSE") {
                Some(original_unit("distill", &name, &raw))
            } else {
                Some(distill_parse::run(&name, &args))
            }
        }
        "unit-r14" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("R14_JUDGMENT") {
                Some(original_unit("r14", &name, &raw))
            } else {
                Some(r14_judgment::run(&name, &args))
            }
        }
        "unit-artifact-shaping" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("ARTIFACT_SHAPING") {
                Some(original_unit("artifact-shaping", &name, &raw))
            } else {
                Some(artifact_shaping::run(&name, &args))
            }
        }
        "unit-injection" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("INJECTION_DETECTION") {
                Some(original_unit("injection", &name, &raw))
            } else {
                Some(injection_detection::run(&name, &args))
            }
        }
        "unit-percentile" => {
            let (name, raw, args) = match unit_args(matches) {
                Ok(parsed) => parsed,
                Err(code) => return Some(code),
            };
            if sent_to_original("PERCENTILE") {
                Some(original_unit("percentile", &name, &raw))
            } else {
                Some(percentile::run(&name, &args))
            }
        }
        crate::cli::ROOT => {
            if sent_to_original("METRICS_SNAPSHOT") {
                return None;
            }
            let storage = matches.get_one::<String>("storage")?.as_str();
            let dsn = std::env::var("ZKC_PG_DSN").ok();
            metrics_report::dispatch(storage, dsn.as_deref())
        }
        _ => None,
    }
}
