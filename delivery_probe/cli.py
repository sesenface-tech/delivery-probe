import argparse
import json
import pathlib
import sys

from . import __version__
from .core import SCENARIOS, run
from .demo import demo


def read_json(path):
    if pathlib.Path(path).stat().st_size > 1024 * 1024:
        raise ValueError("Input exceeds 1 MiB")
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Replay webhook delivery faults and optionally assert receiver state.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Run eight isolated local cases, including negative controls")
    replay = sub.add_parser("run", help="POST a JSON event array to an authorized test receiver")
    replay.add_argument("events")
    replay.add_argument("--url", required=True)
    replay.add_argument("--scenario", choices=SCENARIOS, default="normal")
    replay.add_argument("--delay", type=float, default=0.1)
    replay.add_argument("--timeout", type=float, default=2)
    replay.add_argument("--state-url")
    replay.add_argument("--expect", help="Path to a non-empty expected JSON object (subset match)")
    replay.add_argument("--wait", type=float, default=0, help="Seconds before the single final-state observation")
    replay.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = demo()
            code = 0 if result["demo_assertions_passed"] else 1
        else:
            result = run(read_json(args.events), args.url, args.scenario, args.delay,
                         args.timeout, args.state_url, read_json(args.expect) if args.expect else None,
                         args.allow_remote, args.wait)
            code = 1 if result["outcome"] == "failed" else 0
        print(json.dumps(result, indent=2, allow_nan=False))
        return code
    except (ValueError, OSError, RecursionError):
        # Never echo request URLs, input contents, credentials or filesystem paths.
        print("Invalid input or file operation; check JSON, paired state options, URL and numeric limits.", file=sys.stderr)
        return 2
