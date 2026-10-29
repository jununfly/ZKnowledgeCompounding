"""Spike 03 labelled data — reuses Spike 02's ground truth, adds a VAGUE route.

Single source of truth for the eval/calib sets is Spike 02's samples.py; we import
it so the two spikes never drift. Spike 03 only ADDS:
  - VAGUE_ROUTE utterances (the explicit "vague" home the router lacked),
  - a 3-way calibration set (None labels become "vague"),
  - the same ADVERSARIAL long-vague probes as Spike 02.

Labels in Spike 03 are one of: "static" | "dynamic" | "vague".
A Spike 02 label of None (router should abstain) maps to "vague" here — because in
the 3-way design "vague" IS the safe sink that replaces forced-abstain.
"""

import os
import sys

# import Spike 02's samples (single source of truth) via explicit path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "spike-02-dual-track-routing"))
from samples import ROUTES, EVAL_SET, CALIB_SET  # noqa: E402

# --- The explicit "vague" route: utterances covering uncertainty / hedging ---
VAGUE_ROUTE = [
    "这个先放一放，等忙完再处理",
    "我还在犹豫，需要再讨论一下才能定",
    "具体情况再看看再决定",
    "下周再看看情况再说",
    "还没完全想清楚",
    "到时候再定吧",
    "先看看情况",
    "这个先搁着",
    "再想想",
    "等下周再决定",
    "暂时不确定",
    "留到后面再说",
]

# Route definitions for the 3-way router
ROUTES_3WAY = dict(ROUTES)
ROUTES_3WAY["vague"] = VAGUE_ROUTE

# --- 3-way calibration set: None -> "vague" ---
CALIB_SET_3WAY = [(t, ("vague" if y is None else y)) for t, y in CALIB_SET]


def eval_3way():
    """EVAL_SET with None labels mapped to 'vague' (the safe sink)."""
    return [(t, ("vague" if y is None else y)) for t, y in EVAL_SET]


# Long-vague adversarial probes: genuinely vague but lexically "dynamic-sounding".
# Spike 02 found the 2-signal router commits all 3 to dynamic (the failure to fix).
ADVERSARIAL = [
    "这个事情我现在还没完全想清楚，可能要等到下周再看看具体情况再决定",
    "关于那个方案我目前还在犹豫，需要和团队再讨论一下才能定下来",
    "这份材料我先放一放，等手头的事情忙完了之后再回头处理",
]
