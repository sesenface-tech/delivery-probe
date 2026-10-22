"""Run a generated test against two isolated example receivers.

Run from repository root: python -m examples.regression.demo
This is a synthetic self-integration example, not third-party adoption.
"""

import json
import os
from pathlib import Path
import subprocess
import sys

from delivery_probe.demo import receiver


def main():
    root = Path(__file__).resolve().parents[2]
    test_file = Path(__file__).with_name("test_generated.py")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    results = []
    for robust in (False, True):
        with receiver(robust) as base:
            env["WEBHOOK_TARGET"] = base + "/webhook"
            env["WEBHOOK_STATE_URL"] = base + "/state"
            result = subprocess.run([sys.executable, str(test_file)], env=env,
                                    capture_output=True, timeout=15)
        expected = 0 if robust else 1
        results.append({"receiver": "guarded" if robust else "deliberately_naive",
                        "exit_code": result.returncode, "expected_exit_code": expected,
                        "matched": result.returncode == expected})
    ok = all(item["matched"] for item in results)
    print(json.dumps({"integration_passed": ok, "runs": results,
                      "scope": "Generated test against synthetic loopback receivers; not external adoption"}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
