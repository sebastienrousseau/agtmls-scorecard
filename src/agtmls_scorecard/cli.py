# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checks import evaluate
from .model import Report, Status
from .repo import Repo

MARK = {
    Status.PASS: "ok  ",
    Status.FAIL: "FAIL",
    Status.NOT_APPLICABLE: "n/a ",
    Status.UNVERIFIED: "?   ",
}


def score(path: Path) -> Report:
    repo = Repo(path)
    return Report(repo=repo.name, path=str(repo.root), categories=evaluate(repo))


def render(report: Report, verbose: bool) -> None:
    print(f"{report.repo}  {report.path}")
    print()
    for category in report.categories:
        if category.evaluated == 0:
            print(f"  {'--':>4}      {category.title:<34} not evaluated")
        else:
            print(
                f"  {category.score:>4.1f}/10  {category.title:<34}"
                f"{category.passed}/{category.evaluated} checked"
                + (f", {category.unverified} unverified" if category.unverified else "")
            )
        for result in category.results:
            show = verbose or result.status is Status.FAIL
            if show:
                print(f"        {MARK[result.status]} {result.criterion:<7} {result.title}")
                if result.detail:
                    print(f"             {result.detail}")
    print()
    print(f"  SCORE     {report.score}/10   over the criteria that could be evaluated")
    print(f"  COVERAGE  {report.coverage:.0%}    of the rubric could be evaluated at all")
    if report.coverage < 0.6:
        # The number that stops this tool becoming the thing it was built to
        # prevent. Said out loud, every time, not buried in JSON.
        print()
        print(
            f"  A {report.score}/10 at {report.coverage:.0%} coverage is a true statement about "
            f"{report.coverage:.0%} of the rubric\n"
            "  and says nothing about the rest. Treat it as a floor, not a grade."
        )
    if report.weakest:
        print()
        print("  Worst first:")
        for category in report.weakest[:3]:
            print(f"    {category.title}: {len(category.failures)} failing")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agtmls-scorecard",
        description="Score a repository against the AgtMLS rubric.",
        epilog=(
            "The score is over criteria this tool can evaluate; coverage says how many "
            "that is. Both are printed because either alone can mislead."
        ),
    )
    parser.add_argument("paths", nargs="*", type=Path, default=[Path.cwd()])
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--verbose", "-v", action="store_true", help="show passing criteria too")
    parser.add_argument(
        "--fail-under",
        type=float,
        metavar="N",
        help="exit 1 if the score is below N",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        metavar="F",
        help="exit 1 if less than this fraction of the rubric could be evaluated. "
             "Use it with --fail-under, or a high score on three checked criteria passes.",
    )
    args = parser.parse_args(argv)

    reports = [score(path) for path in args.paths]
    if args.json:
        payload = reports[0].to_dict() if len(reports) == 1 else [r.to_dict() for r in reports]
        print(json.dumps(payload, indent=2))
    else:
        for index, report in enumerate(reports):
            if index:
                print("\n" + "-" * 72 + "\n")
            render(report, args.verbose)

    failed = False
    for report in reports:
        if args.fail_under is not None and report.score < args.fail_under:
            print(f"FAIL: {report.repo} scored {report.score}, below {args.fail_under}", file=sys.stderr)
            failed = True
        if args.min_coverage is not None and report.coverage < args.min_coverage:
            print(
                f"FAIL: {report.repo} coverage {report.coverage:.0%} is below "
                f"{args.min_coverage:.0%}",
                file=sys.stderr,
            )
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
