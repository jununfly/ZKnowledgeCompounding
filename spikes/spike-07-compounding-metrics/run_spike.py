import sys
import unittest

from store import apply_schema, connect, seed_scenario
from metrics import report


if __name__ == "__main__":
    if "--demo" in sys.argv:
        apply_schema()
        with connect() as conn, conn.cursor() as cur:
            seed_scenario(cur)
            r = report(cur)
        print("CompoundingReport:")
        for k, v in r.__dict__.items():
            print(f"  {k} = {v}")
    else:
        unittest.main()
