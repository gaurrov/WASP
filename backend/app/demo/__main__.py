"""Demo tooling. Run inside the backend container:

  python -m app.demo prefetch              # before going offline: documents + embedding model
  python -m app.demo preflight             # is everything the demo needs up?
  python -m app.demo reset                 # wipe applications (dev only)
  python -m app.demo load --stage STAGE    # jump to a point in the story (resets first)
  python -m app.demo rehearse --times 5    # run the whole story N times, asserting each step
  python -m app.demo metrics               # measured pitch numbers (writes /data/METRICS.md)

Stages: draft, submitted, clarification, resubmitted, approved, renewed.
"""

import argparse
import sys
import time
import traceback
from pathlib import Path

from app.demo import ops, scenario
from app.demo.client import DemoError


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.demo",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("prefetch")
    sub.add_parser("preflight")
    sub.add_parser("reset")
    load_cmd = sub.add_parser("load")
    load_cmd.add_argument("--stage", choices=scenario.STAGES, default="submitted")
    load_cmd.add_argument("--keep", action="store_true", help="don't reset first")
    rehearse_cmd = sub.add_parser("rehearse")
    rehearse_cmd.add_argument("--times", type=int, default=1)
    metrics_cmd = sub.add_parser("metrics")
    metrics_cmd.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    if args.command == "prefetch":
        ops.prefetch()
    elif args.command == "preflight":
        return 0 if ops.preflight() else 1
    elif args.command == "reset":
        ops.reset()
        print("Reset: applications, documents, findings, alerts and workflow state removed.")
    elif args.command == "load":
        ops.require_dev()
        if not args.keep:
            ops.reset()
        demo = scenario.run(until=args.stage)
        print(f"Loaded stage '{args.stage}': http://localhost:5173/applications/{demo.app_id}")
    elif args.command == "rehearse":
        return rehearse(args.times)
    elif args.command == "metrics":
        ops.require_dev()
        report = ops.metrics(args.runs)
        Path("/data/METRICS.md").write_text(report)
        print(report)
    return 0


def rehearse(times: int) -> int:
    ops.require_dev()
    runs = []
    for i in range(1, times + 1):
        ops.reset()
        start = time.perf_counter()
        try:
            demo = scenario.run()
        except (DemoError, Exception) as exc:  # noqa: BLE001 — report which run/stage broke
            print(f"Run {i}/{times}: FAILED — {exc}")
            traceback.print_exc()
            return 1
        runs.append(demo)
        steps = " · ".join(f"{k} {v:.1f}s" for k, v in demo.timings.items())
        print(f"Run {i}/{times}: passed in {time.perf_counter() - start:.1f}s  ({steps})")
    caught, total = sum(runs[-1].detected.values()), len(runs[-1].detected)
    print(f"\n{times}/{times} rehearsals passed; {caught}/{total} planted issues caught.")
    ops.reset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
