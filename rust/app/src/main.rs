mod cli;
mod original;
mod units;

use std::ffi::OsString;
use std::process::ExitCode;

fn main() -> ExitCode {
    original::report_fallbacks();
    let argv: Vec<OsString> = std::env::args_os().collect();
    // Unit commands are new front doors for library functions, not recorded CLI
    // cases. Check them first so the parser and routing for `app replay` stay intact.
    if let Some(name) = argv.get(1).and_then(|word| word.to_str())
        && cli::UNIT_COMMANDS.contains(&name)
    {
        // clap would treat argv[1] (the unit command itself) as a positional
        // argument; drop it so `args` holds only `<fn> <json-array>`.
        let unit_argv: Vec<OsString> = std::iter::once(argv[0].clone())
            .chain(argv[2..].iter().cloned())
            .collect();
        if let Ok(matches) = cli::unit_command(name).try_get_matches_from(&unit_argv)
            && let Some(code) = units::dispatch(name, &matches)
        {
            return code;
        }
        return original::run(&argv[1..]);
    }
    if let Ok(matches) = cli::command().try_get_matches_from(&argv) {
        let (command, sub) = matches.subcommand().unwrap_or((cli::ROOT, &matches));
        if let Some(code) = units::dispatch(command, sub) {
            return code;
        }
    }
    original::run(&argv[1..])
}
