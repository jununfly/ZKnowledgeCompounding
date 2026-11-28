use std::ffi::OsString;

use clap::{Arg, Command, value_parser};

/// The command `units::dispatch` gets when argv names no subcommand.
pub const ROOT: &str = "metrics-snapshot";

/// Library units are exposed as isolated front-door commands. `main` checks these
/// before the recorded `metrics-snapshot` command line, so `app replay` is unchanged.
pub const UNIT_COMMANDS: &[&str] = &[
    "unit-transport",
    "unit-context",
    "unit-expiry",
    "unit-scheduling",
    "unit-faithfulness",
    "unit-routing",
    "unit-cross-source",
    "unit-distill",
    "unit-r14",
    "unit-artifact-shaping",
    "unit-injection",
    "unit-percentile",
    "unit-operator-guard",
    "unit-telemetry-validation",
    "unit-schedule-render",
    "unit-review-gate",
    "unit-capture-profile",
    "unit-mcp-exposure",
];

fn rest() -> Arg {
    Arg::new("args")
        .num_args(0..)
        .trailing_var_arg(true)
        .allow_hyphen_values(true)
        .value_parser(value_parser!(OsString))
}

/// Routes argv to a command. Anything this parser rejects runs the original, so it never
/// has to match every way the original accepts its arguments.
///
/// Hand-edited after `app front-door`: the generated parser treated `--storage` as a
/// `Count` flag (`takes_value=false`), but `scripts/metrics_snapshot.py` declares it as
/// `--storage <kind>` with a value. Declaring it as a one-value option lets the wired
/// unit read the backend instead of falling back.
pub fn command() -> Command {
    Command::new(ROOT)
        .disable_help_flag(true)
        .disable_version_flag(true)
        .arg(
            Arg::new("storage")
                .long("storage")
                .num_args(1)
                .value_parser(value_parser!(String)),
        )
        .arg(rest())
}

/// Parser for a library-unit command. `args` carries `<fn> <json-array>`; the glue
/// writes the JSON result to stdout. Only `UNIT_COMMANDS` reach this parser.
pub fn unit_command(name: &str) -> Command {
    // clap's `Command::new` needs a `'static` name; the caller is one of these constants.
    let static_name = UNIT_COMMANDS
        .iter()
        .find(|candidate| **candidate == name)
        .copied()
        .unwrap_or("unit");
    Command::new(static_name)
        .disable_help_flag(true)
        .disable_version_flag(true)
        .arg(rest())
}
