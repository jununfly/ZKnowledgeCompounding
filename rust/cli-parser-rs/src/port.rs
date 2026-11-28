//! The Rust port of `spikes/spike-28-cli-parser/pure_bridge.py`.
//!
//! `parse_argv(argv)` = the **valid-argv → namespace-dict** mapping of `zkc.cli.parse_args`, a
//! table-driven fold of the `cli.py` subparser grammar (defaults, `store_true`, nested `tombstone`).
//! BOUNDED to valid argv: argparse's `SystemExit`/usage and unique-prefix matching are library seams
//! (finding 26) and out of scope; unrecognised tokens return `Err`. Option VALUES come from input
//! tokens; only per-subcommand defaults are `recorded-literal` quotes from `cli.py`.

#![forbid(unsafe_code)]

use std::collections::HashMap;

use serde_json::{Map, Value, json};

#[derive(Clone, Copy)]
enum D {
    Pg,
    Null,
    Sweep,
    False,
}
impl D {
    fn v(self) -> Value {
        match self {
            D::Pg => json!("pg"), // recorded-literal: cli.py --storage default
            D::Null => Value::Null,
            D::Sweep => json!("daily-automation"), // recorded-literal: cli.py sweep --operator default
            D::False => json!(false),              // store_true default
        }
    }
}

#[derive(Clone, Copy)]
struct Opt {
    flag: &'static str,
    dest: &'static str,
    value: bool,
    d: D,
}
const fn with(flag: &'static str, dest: &'static str, d: D) -> Opt {
    Opt {
        flag,
        dest,
        value: true,
        d,
    }
}
const fn flag(flag: &'static str, dest: &'static str) -> Opt {
    Opt {
        flag,
        dest,
        value: false,
        d: D::False,
    }
}

const STORAGE: Opt = with("--storage", "storage", D::Pg);
const JSON: Opt = flag("--json", "json");
const SUBS: &[(Option<&str>, &[Opt], &[&str])] = &[
    (None, &[STORAGE], &["command", "storage"]), // daily
    (None, &[STORAGE, JSON], &["command", "storage", "json"]), // meter/p64
    (
        None,
        &[
            STORAGE,
            with("--id", "id", D::Null),
            with("--verdict", "verdict", D::Null),
            with("--content", "content", D::Null),
            with("--stale-branch", "stale_branch", D::Null),
            flag("--list", "list"),
            JSON,
        ],
        &[
            "command",
            "storage",
            "id",
            "verdict",
            "content",
            "stale_branch",
            "list",
            "json",
        ],
    ), // decide
    (
        None,
        &[
            STORAGE,
            flag("--corpus", "corpus"),
            flag("--dry-run", "dry_run"),
            JSON,
        ],
        &["command", "storage", "corpus", "dry_run", "json"],
    ), // archive
    (
        None,
        &[STORAGE, flag("--dry-run", "dry_run"), JSON],
        &["command", "storage", "dry_run", "json"],
    ), // embed
    (
        Some("mark"),
        &[
            with("--id", "id", D::Null),
            with("--operator", "operator", D::Null),
            with("--reason", "reason", D::Null),
            STORAGE,
            JSON,
        ],
        &[
            "command",
            "tombstone_action",
            "id",
            "operator",
            "reason",
            "storage",
            "json",
        ],
    ),
    (
        Some("sweep"),
        &[
            with("--operator", "operator", D::Sweep),
            flag("--dry-run", "dry_run"),
            STORAGE,
            JSON,
        ],
        &[
            "command",
            "tombstone_action",
            "operator",
            "dry_run",
            "storage",
            "json",
        ],
    ),
];

// Subcommand / action → index into SUBS.
fn pick(
    cmd: &str,
    action: Option<&str>,
) -> Option<&'static (
    Option<&'static str>,
    &'static [Opt],
    &'static [&'static str],
)> {
    let i = match (cmd, action) {
        ("daily", _) => 0,
        ("meter", _) | ("p64", _) => 1,
        ("decide", _) => 2,
        ("archive", _) => 3,
        ("embed", _) => 4,
        ("tombstone", Some("mark")) | ("tombstone", Some("restore")) => 5,
        ("tombstone", Some("sweep")) => 6,
        _ => return None,
    };
    Some(&SUBS[i])
}

fn parse_opts(
    toks: &[Value],
    specs: &[Opt],
    order: &[&str],
    out: &mut Map<String, Value>,
) -> Result<(), String> {
    let mut m: HashMap<&str, Value> = specs.iter().map(|s| (s.dest, s.d.v())).collect();
    let mut i = 0;
    while i < toks.len() {
        let tok = toks[i]
            .as_str()
            .ok_or("TypeError: argv token is not a string")?;
        if !tok.starts_with("--") {
            return Err(format!("unexpected positional argument: {tok}"));
        }
        let (name, inline) = match tok.split_once('=') {
            Some((n, v)) => (n, Some(v)),
            None => (tok, None),
        };
        let spec = specs
            .iter()
            .find(|s| s.flag == name)
            .ok_or(format!("unrecognized arguments: {tok}"))?;
        if spec.value {
            let val = match inline {
                Some(v) => v.to_string(),
                None => {
                    i += 1;
                    toks.get(i)
                        .and_then(Value::as_str)
                        .ok_or(format!("argument {name}: expected one argument"))?
                        .to_string()
                }
            };
            m.insert(spec.dest, json!(val));
        } else {
            m.insert(spec.dest, json!(true));
        }
        i += 1;
    }
    for key in order {
        if let Some(v) = m.remove(*key) {
            out.insert((*key).to_string(), v);
        } else if !out.contains_key(*key) {
            out.insert((*key).to_string(), Value::Null);
        }
    }
    Ok(())
}

/// Port of `parse_argv` (`spikes/spike-28-cli-parser/pure_bridge.py:26`).
pub fn parse_argv(argv: Value) -> Result<Value, String> {
    let toks = argv.as_array().ok_or("TypeError: argv is not a list")?;
    let cmd = toks
        .first()
        .and_then(Value::as_str)
        .ok_or("error: a subcommand is required")?;
    let action = if cmd == "tombstone" {
        toks.get(1).and_then(Value::as_str)
    } else {
        None
    };
    let (is_tomb, specs, order) =
        pick(cmd, action).ok_or(format!("error: invalid choice: {cmd}"))?;

    let mut out = Map::new();
    out.insert("command".to_string(), json!(cmd)); // echoed from input, not a literal
    if is_tomb.is_some() {
        out.insert(
            "tombstone_action".to_string(),
            json!(action.unwrap_or_default()),
        );
    }
    let rest = if is_tomb.is_some() {
        &toks[2..]
    } else {
        &toks[1..]
    };
    parse_opts(rest, specs, order, &mut out)?;
    Ok(Value::Object(out))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn argv(v: &[&str]) -> Value {
        Value::Array(v.iter().map(|s| json!(s)).collect())
    }

    #[test]
    fn defaults_and_order() {
        assert_eq!(
            parse_argv(argv(&["daily"])).unwrap(),
            json!({"command": "daily", "storage": "pg"})
        );
        assert_eq!(
            parse_argv(argv(&["meter", "--json"])).unwrap(),
            json!({"command": "meter", "storage": "pg", "json": true})
        );
        let d = parse_argv(argv(&["decide", "--id", "X", "--verdict", "stale"])).unwrap();
        assert_eq!(d["stale_branch"], Value::Null);
        assert_eq!(d["list"], json!(false));
    }

    #[test]
    fn nested_tombstone() {
        let s = parse_argv(argv(&["tombstone", "sweep", "--dry-run"])).unwrap();
        assert_eq!(s["operator"], json!("daily-automation"));
        assert_eq!(s["dry_run"], json!(true));
        let m = parse_argv(argv(&[
            "tombstone",
            "mark",
            "--id",
            "X",
            "--operator",
            "zj",
        ]))
        .unwrap();
        assert_eq!(m["reason"], Value::Null);
    }
}
