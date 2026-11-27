"""Reapply the hand-written JsonRpcError binding patch after `rust-anything refresh`.

`refresh` regenerates `src/lib.rs` from the signatures in `port.rs` and drops the
patch that reconstructs `JsonRpcError(code, message, data)` from the recorded
`JsonRpcError: <text>` prefix. Without it, 57 recorded exception cases fall back
to `ValueError` and `rust-anything gate` fails. Run this script once after every
refresh:

    python3 rust/transport-rs/restore_lib_patch.py

It is idempotent: no changes when both the helper and the match arm are present.
"""
from pathlib import Path

HELPER = '''/// Map the recorded `JsonRpcError: <text>` prefix back to the original exception
/// class. The generic `named_error` below cannot do it: `JsonRpcError.__init__`
/// takes `(code, message, data)`, while the generated helper passes a single text.
/// This is a local patch to generated bindings; `refresh` overwrites it.
fn jsonrpc_error(text: &str) -> (i64, &str) {
    if text.starts_with("Parse error") {
        (-32700, text) // recorded-literal: protocol.py PARSE_ERROR
    } else if text.starts_with("Invalid Request") {
        (-32600, text) // recorded-literal: protocol.py INVALID_REQUEST
    } else if text.starts_with("Method not found") {
        (-32601, text) // recorded-literal: protocol.py METHOD_NOT_FOUND
    } else if text.starts_with("Invalid params") {
        (-32602, text) // recorded-literal: protocol.py INVALID_PARAMS
    } else {
        (-32603, text) // recorded-literal: protocol.py INTERNAL_ERROR
    }
}

'''

ARM = '''        "JsonRpcError" => Python::attach(|py| {
            let class = py
                .import("zkc.transport.protocol")
                .ok()?
                .getattr("JsonRpcError")
                .ok()?;
            let (code, text) = jsonrpc_error(&text);
            let value = class.call1((code, text)).ok()?;
            Some(PyErr::from_value(value))
        })
        .unwrap_or_else(|| e::PyValueError::new_err(message)),
'''

ERROR_FN = "fn error(message: String) -> PyErr {"
FALLBACK_ARM = (
    "        _ => named_error(kind, &text).unwrap_or_else(|| e::PyValueError::new_err(message)),"
)


def main() -> int:
    path = Path(__file__).resolve().parent / "src" / "lib.rs"
    source = path.read_text()
    if "fn jsonrpc_error" in source and '"JsonRpcError" =>' in source:
        print("already patched")
        return 0
    if ERROR_FN not in source or FALLBACK_ARM not in source:
        raise SystemExit(f"unexpected generated binding layout in {path}")
    source = source.replace(ERROR_FN, HELPER + ERROR_FN, 1)
    source = source.replace(FALLBACK_ARM, ARM + FALLBACK_ARM, 1)
    path.write_text(source)
    print(f"patched {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
