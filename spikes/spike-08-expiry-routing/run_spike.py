"""Spike 08 runner: apply schema, run the test suite, print a demo decision over the seed."""
import sys
import unittest

from store import connect, apply_schema, truncate_all, seed_routing
from routing import route_and_apply, DECISION_DISTILL, DECISION_ARCHIVE, DECISION_ABSTAIN


def demo():
    apply_schema()
    with connect() as conn, conn.cursor() as cur:
        truncate_all(cur)
        s = seed_routing(cur)
        print("=== Expiry routing demo (ROT_THRESHOLD=0.9) ===")
        for key in ("d1", "d2", "d3", "d4"):
            d = route_and_apply(cur, s[key])
            print(f"  {key}: routable={d['routable']} action={d['action']} :: {d['reason']}")
        conn.commit()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        demo()
    else:
        unittest.main(verbosity=2)
