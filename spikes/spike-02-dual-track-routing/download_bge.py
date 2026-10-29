"""Robustly download + verify the BGE model for Spike 02 real-encoder run.

The environment's access to HuggingFace (and the hf-mirror) is flaky
(SSL EOF / timeout / 502), so we retry with an explicit cache dir until the
model loads AND embeds a probe sentence. Once cached, run_spike_real.py can
reuse it via the same HF_HOME / cache_dir.
"""
import os
import time
import sys

CACHE = "/Users/bilibili/.cache/zkc_hf"
os.environ["HF_HOME"] = CACHE
MODEL = "BAAI/bge-small-zh-v1.5"


def main():
    from fastembed import TextEmbedding
    last = None
    for attempt in range(1, 41):
        try:
            print(f"[attempt {attempt}] loading {MODEL} (cache={CACHE})", flush=True)
            m = TextEmbedding(MODEL, cache_dir=CACHE)
            emb = list(m.embed(["测试句", "PostgreSQL 的 MVCC 通过事务 ID 与快照实现一致性读"]))
            print(f"SUCCESS  shape={emb[0].shape}  attempts={attempt}", flush=True)
            return 0
        except Exception as e:  # noqa: BLE001
            last = e
            msg = str(e).replace("\n", " ")
            print(f"[attempt {attempt}] FAILED: {msg[:160]}", flush=True)
            time.sleep(4)
    print(f"GAVE_UP last={last}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
