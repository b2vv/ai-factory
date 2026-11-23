#!/usr/bin/env python3
"""Read the skill-routing scenarios and score recorded traces.

This script never launches a model. An operator runs each case in a fresh CLI session
(see README.md), saves the stream-json trace, and passes it here.

  run_routing.py --list                      one line per case: id<TAB>input
  run_routing.py --parse TRACE               the first skill the trace loaded, or "none"
  run_routing.py --score DIR                 score DIR/<case id>.jsonl for every case; prints JSON
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SCENARIOS = HERE / "scenarios.json"


def load_cases(path=SCENARIOS):
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return data["cases"]


def first_skill(lines):
    """Return the skill named by the first Skill tool_use in a stream-json trace, or "none"."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("type") != "assistant":
            continue
        for item in (event.get("message") or {}).get("content") or []:
            if isinstance(item, dict) and item.get("type") == "tool_use" and item.get("name") == "Skill":
                name = str((item.get("input") or {}).get("skill") or "")
                return name.rsplit(":", 1)[-1] or "none"
    return "none"


def trace_model(lines):
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "system" and event.get("subtype") == "init":
            return str(event.get("model") or "unknown")
    return "unknown"


def score(directory, cases):
    results = []
    for case in cases:
        trace = pathlib.Path(directory) / f"{case['id']}.jsonl"
        if not trace.is_file():
            results.append({"id": case["id"], "outcome": "NOT_RUN"})
            continue
        lines = trace.read_text(encoding="utf-8", errors="replace").splitlines()
        got = first_skill(lines)
        if got == case["expected_skill"]:
            outcome = "PASS"
        elif got == "none":
            outcome = "NO_SKILL"
        elif got in case["not_instead"]:
            outcome = "FAIL_NOT_INSTEAD"
        else:
            outcome = "FAIL_OTHER"
        results.append({"id": case["id"], "expected": case["expected_skill"], "first_skill": got,
                        "outcome": outcome, "model": trace_model(lines)})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--parse", metavar="TRACE")
    group.add_argument("--score", metavar="DIR")
    args = parser.parse_args(argv)
    if args.list:
        for case in load_cases():
            print(f"{case['id']}\t{case['input']}")
    elif args.parse:
        print(first_skill(pathlib.Path(args.parse).read_text(encoding="utf-8", errors="replace").splitlines()))
    else:
        json.dump(score(args.score, load_cases()), sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
