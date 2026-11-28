//! Hand-written glue (wire generated the stub): `unit-schedule-render <fn> <json-array>`.
//! Calls `schedule_render_rs::port` for the three recorded functions from
//! `scripts/daily_driver_schedule.py` through the spike-24 alias.
//!
//! No encoding seam: every argument is a JSON string and returns are
//! str/list[str]; the port's error text already carries the `ValueError: `
//! prefix, matching the oracle verbatim. `main()`, `resolve_paths()` and real
//! Windows schtasks registration stay in Python (not covered by this door).

use std::process::ExitCode;

use serde_json::Value;

use super::{arg_value, emit};

fn take(args: &[Value], index: usize) -> Result<Value, ExitCode> {
    arg_value(args, index)
}

pub fn run(name: &str, args: &[Value]) -> ExitCode {
    let result = match name {
        "build_task_action" => {
            let wrapper = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            schedule_render_rs::port::build_task_action(wrapper)
        }
        "build_register_command" => {
            let wrapper = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let task_name = match take(args, 1) {
                Ok(value) => value,
                Err(code) => return code,
            };
            let at = match take(args, 2) {
                Ok(value) => value,
                Err(code) => return code,
            };
            schedule_render_rs::port::build_register_command(wrapper, task_name, at)
        }
        "build_unregister_command" => {
            let task_name = match take(args, 0) {
                Ok(value) => value,
                Err(code) => return code,
            };
            schedule_render_rs::port::build_unregister_command(task_name)
        }
        _ => return super::fail(format!("unknown schedule-render fn: {name}")),
    };
    emit(result)
}
