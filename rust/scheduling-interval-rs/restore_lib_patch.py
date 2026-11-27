"""Restore hand-maintained bits after `bridge` / `refresh` regenerate this crate.

Two tool behaviors are known:
- `refresh` regenerates `src/lib.rs` from `port.rs` and forgets `use serde_json::Value;`
  when a port function returns `Value` (two functions here do).
- a fresh `bridge` rewrites `Cargo.toml` and drops the hand-added `regex` dependency.

Run this script after either command, then `rust-anything gate <crate>`. It is
idempotent: nothing changes when both pieces are already present.
"""
from pathlib import Path

CRATE = Path(__file__).resolve().parent
IMPORT = "use serde_json::Value;"
REGEX = 'regex = "1"'
JSON_LINE = 'serde_json = { version = "1", features = ["preserve_order", "float_roundtrip", "unbounded_depth"] }\n'


def main() -> int:
    changed = False
    lib = CRATE / "src" / "lib.rs"
    source = lib.read_text()
    if IMPORT not in source:
        anchor = "use pyo3::prelude::*;\n"
        if anchor not in source:
            raise SystemExit(f"unexpected generated bindings in {lib}")
        source = source.replace(anchor, anchor + IMPORT + "\n", 1)
        lib.write_text(source)
        changed = True
    cargo = CRATE / "Cargo.toml"
    manifest = cargo.read_text()
    if REGEX not in manifest:
        if JSON_LINE not in manifest:
            raise SystemExit(f"unexpected generated manifest in {cargo}")
        manifest = manifest.replace(JSON_LINE, JSON_LINE + REGEX + "\n", 1)
        cargo.write_text(manifest)
        changed = True
    print("patched" if changed else "already patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
