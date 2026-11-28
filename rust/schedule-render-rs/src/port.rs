//! The Rust port of `spikes/spike-24-schedule-render/pure_bridge.py`.
//!
//! Three pure, JSON-native schtasks render helpers from
//! `scripts/daily_driver_schedule.py`: `build_task_action` (/tr action path
//! quoting + guards), `build_register_command` and `build_unregister_command`.
//! No dataclass / datetime / Storage / tuning / subprocess seam. `main()`,
//! `resolve_paths()` and real Windows registration stay in Python.
//!
//! Porting this slice does NOT resolve DP ticket 13 (scripts dynamic-code
//! blocker): the only real D2 seam is `daily_e1_driver._import_meter`, which is
//! not on any of these functions' import paths.

#![forbid(unsafe_code)]

use serde_json::{Value, json};

/// Python `str.isspace()` set (29 chars); Rust `char::is_whitespace()` omits
/// ASCII FS/GS/RS/US (`\x1c..\x1f`) that CPython treats as whitespace. Same
/// `py_isspace` as `rust/operator-guard-rs/src/port.rs`.
fn py_isspace(c: char) -> bool {
    c.is_whitespace() || matches!(c, '\u{001c}' | '\u{001d}' | '\u{001e}' | '\u{001f}')
}

fn is_blank_py(s: &str) -> bool {
    s.chars().all(py_isspace)
}

/// Port of the `^([01]\d|2[0-3]):([0-5]\d)$` match against
/// `scripts/daily_driver_schedule.py::_TIME_RE`.
///
/// Semantics locked by a Python probe (2026-11-28):
/// - Python `re.$` also matches a single trailing `\n` (but not `\r` or `\n\n`),
///   so a final `\n` is tolerated here; the rest must be exactly 5 ASCII chars.
/// - Hour branch `[01]\d|2[0-3]`: leading `0`/`1` allows any decimal digit,
///   leading `2` only `0..3`; minute branch `[0-5]\d`: leading `0..5` + a digit.
/// - BOUNDARY (not recorded, not proven): Python `\d` is Unicode Nd (e.g.
///   fullwidth digits) while this port accepts only ASCII `0..9`. Real CLI
///   `--time` input is ASCII HH:MM; Unicode-Nd times are out of this slice's
///   evidence and left as a documented boundary, not faked.
fn py_time_match(at: &str) -> bool {
    let core = at.strip_suffix('\n').unwrap_or(at);
    let b = core.as_bytes();
    if b.len() != 5 || b[2] != b':' {
        return false;
    }
    let is_digit = |c: u8| c.is_ascii_digit();
    let hour_ok = match b[0] {
        b'0' | b'1' => is_digit(b[1]),
        b'2' => (b'0'..=b'3').contains(&b[1]),
        _ => false,
    };
    let minute_ok = (b'0'..=b'5').contains(&b[3]) && is_digit(b[4]);
    hour_ok && minute_ok
}

/// `build_task_action(wrapper) -> str`: quote the whole path for `/tr`.
pub fn build_task_action(wrapper: Value) -> Result<Value, String> {
    let path = match wrapper {
        Value::String(s) => s,
        _ => return Err("TypeError: expected string".to_string()),
    };
    if is_blank_py(&path) {
        return Err("ValueError: 驱动包装路径为空".to_string()); // recorded-literal: daily_driver_schedule.py empty-path ValueError
    }
    if path.contains("__") || path.contains("%CD%") || path.contains("%~dp0") {
        return Err(format!(
            "ValueError: 驱动包装路径仍含占位符: {path}" // recorded-literal: daily_driver_schedule.py placeholder-prefix ValueError
        ));
    }
    Ok(Value::String(format!("\"{path}\"")))
}

/// `build_register_command(wrapper, task_name, at) -> list[str]`.
pub fn build_register_command(
    wrapper: Value,
    task_name: Value,
    at: Value,
) -> Result<Value, String> {
    let (wrapper, task_name, at) = match (wrapper, task_name, at) {
        (Value::String(w), Value::String(n), Value::String(t)) => (w, n, t),
        _ => return Err("TypeError: expected string arguments".to_string()),
    };
    if !py_time_match(&at) {
        return Err(format!(
            "ValueError: 时间须为 HH:MM（00:00-23:59），收到: {at}" // recorded-literal: daily_driver_schedule.py invalid-time ValueError
        ));
    }
    if is_blank_py(&task_name) {
        return Err("ValueError: 任务名不能为空".to_string()); // recorded-literal: daily_driver_schedule.py empty-task-name ValueError
    }
    // Inline the action quoting (same rules as build_task_action) so no
    // `unreachable!` is needed: the guards above already prove wrapper is a
    // string, and a quoted path is always a String.
    if is_blank_py(&wrapper) {
        return Err("ValueError: 驱动包装路径为空".to_string()); // recorded-literal: daily_driver_schedule.py empty-path ValueError
    }
    if wrapper.contains("__") || wrapper.contains("%CD%") || wrapper.contains("%~dp0") {
        return Err(format!(
            "ValueError: 驱动包装路径仍含占位符: {wrapper}" // recorded-literal: daily_driver_schedule.py placeholder-prefix ValueError
        ));
    }
    let action = format!("\"{wrapper}\"");
    Ok(json!([
        "schtasks", "/create", "/tn", task_name, "/tr", action, "/sc", "daily", "/st", at, "/f"
    ]))
}

/// `build_unregister_command(task_name) -> list[str]`.
pub fn build_unregister_command(task_name: Value) -> Result<Value, String> {
    let task_name = match task_name {
        Value::String(s) => s,
        _ => return Err("TypeError: expected string".to_string()),
    };
    if is_blank_py(&task_name) {
        return Err("ValueError: 任务名不能为空".to_string()); // recorded-literal: daily_driver_schedule.py empty-task-name ValueError
    }
    Ok(json!(["schtasks", "/delete", "/tn", task_name, "/f"]))
}
