"""Probe: can we actually run semantic-router with a LOCAL FastEmbed encoder?"""
import sys

try:
    from semantic_router import Route, IndexedRouter
    from semantic_router.encoders import FastEmbedEncoder
except Exception as e:
    print(f"IMPORT FAILED: {type(e).__name__}: {e}")
    sys.exit(1)
print("import semantic_router: OK")

for model in ["BAAI/bge-small-zh-v1.5", "BAAI/bge-small-en-v1.5"]:
    try:
        enc = FastEmbedEncoder(name=model)
        vecs = enc(["今天下午和客户对齐一下交付时间", "PostgreSQL 的 MVCC 通过快照实现一致性读"])
        print(f"model={model}: OK  dim={len(vecs[0])}  n={len(vecs)}")
        print("PROBE OK")
        sys.exit(0)
    except Exception as e:
        print(f"model={model} FAILED: {type(e).__name__}: {str(e)[:200]}")

print("ALL MODELS FAILED")
sys.exit(2)
