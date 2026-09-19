# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Tests for the scorer.

Two things are being defended here.

The first is arithmetic: an unverified criterion must never become a pass.
That is the whole reason this tool exists rather than a spreadsheet, and it is
one `or` away from being wrong.

The second is false positives. A scorecard that flags prose as a broken link,
or a documented suppression as an undocumented one, gets switched off -- and a
switched-off scorecard scores nothing while looking like it scores everything.
Each case below is one this tool actually got wrong on its first run.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agtmls_scorecard.checks import documentation, maintainability, security  # noqa: E402  (sys.path is set above)
from agtmls_scorecard.model import CategoryReport, Report, Result, Status  # noqa: E402  (sys.path is set above)
from agtmls_scorecard.repo import Repo  # noqa: E402  (sys.path is set above)


class ScoringTests(unittest.TestCase):
    def category(self, *statuses: Status) -> CategoryReport:
        return CategoryReport(
            id="t",
            title="T",
            results=[
                Result(f"t.{i}", "x", s, "reason" if s in (Status.UNVERIFIED, Status.NOT_APPLICABLE) else "")
                for i, s in enumerate(statuses)
            ],
        )

    def test_unverified_is_not_a_pass(self) -> None:
        # The failure this tool exists to prevent: scoring only what you can
        # check, and calling the result a grade.
        category = self.category(Status.PASS, Status.UNVERIFIED, Status.UNVERIFIED)
        self.assertEqual(category.score, 10.0, "one of one evaluated criteria passed")
        self.assertEqual(category.evaluated, 1)
        self.assertAlmostEqual(category.coverage, 1 / 3, places=3)

    def test_not_applicable_leaves_the_denominator(self) -> None:
        # Unlike unverified: a criterion that cannot apply should not drag
        # coverage down, or every small repository looks unmeasured.
        category = self.category(Status.PASS, Status.NOT_APPLICABLE)
        self.assertEqual(category.score, 10.0)
        self.assertEqual(category.coverage, 1.0)

    def test_a_category_nobody_can_check_scores_zero_not_ten(self) -> None:
        category = self.category(Status.UNVERIFIED, Status.UNVERIFIED)
        self.assertEqual(category.score, 0.0, "no evidence is not good evidence")

    def test_exemptions_require_a_reason(self) -> None:
        with self.assertRaises(ValueError):
            Result("1.1", "x", Status.UNVERIFIED)
        with self.assertRaises(ValueError):
            Result("1.1", "x", Status.NOT_APPLICABLE)

    def test_report_reports_both_numbers(self) -> None:
        report = Report(repo="r", path="/r", categories=[
            self.category(Status.PASS, Status.FAIL),
            self.category(Status.UNVERIFIED),
        ])
        self.assertEqual(report.score, 5.0)
        self.assertAlmostEqual(report.coverage, 2 / 3, places=3)
        self.assertIn("coverage", report.to_dict())


class FalsePositiveTests(unittest.TestCase):
    """Each of these was a real false positive on the first run."""

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_fixture"
        self.tmp.mkdir(exist_ok=True)
        self.addCleanup(self._clean)

    def _clean(self) -> None:
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.tmp.rmdir()

    def write(self, name: str, text: str) -> None:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def result(self, results: list[Result], criterion: str) -> Result:
        return next(r for r in results if r.criterion == criterion)

    def test_a_link_inside_a_code_span_is_not_a_link(self) -> None:
        self.write("README.md", "Intra-doc links via `[`Foo`](crate::Foo)`. Not a file.\n")
        outcome = self.result(documentation.run(Repo(self.tmp)), "5.5")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_prose_with_brackets_is_not_a_link(self) -> None:
        self.write("README.md", "Nothing yet — [vX.Y.Z] is the cut (see below).\n")
        outcome = self.result(documentation.run(Repo(self.tmp)), "5.5")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_a_genuinely_broken_link_is_still_caught(self) -> None:
        # The above two must not have been bought by blinding the check.
        self.write("README.md", "See [the guide](docs/missing.md).\n")
        outcome = self.result(documentation.run(Repo(self.tmp)), "5.5")
        self.assertIs(outcome.status, Status.FAIL, "a real broken link must still fail")

    def test_a_suppression_with_a_trailing_reason_is_accepted(self) -> None:
        self.write("m.py", "import os  # noqa: E402  (needs ROOT on the path first)\n")
        outcome = self.result(maintainability.run(Repo(self.tmp)), "9.1b")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_a_bare_suppression_is_still_caught(self) -> None:
        self.write("m.py", "import os  # noqa: E402\n")
        outcome = self.result(maintainability.run(Repo(self.tmp)), "9.1b")
        self.assertIs(outcome.status, Status.FAIL, "a bare suppression must still fail")

    def test_a_rubric_describing_todos_is_not_a_todo(self) -> None:
        self.write("docs/RUBRIC.md", "| 9.10 | Every TODO links to a tracked issue | Scan |\n")
        outcome = self.result(maintainability.run(Repo(self.tmp)), "9.10")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_a_real_todo_in_source_is_still_caught(self) -> None:
        self.write("m.py", "# TODO: fix this later\n")
        outcome = self.result(maintainability.run(Repo(self.tmp)), "9.10")
        self.assertIs(outcome.status, Status.FAIL)


class SecurityCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_sec"
        (self.tmp / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._clean)

    def _clean(self) -> None:
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.tmp.rmdir()

    def workflow(self, name: str, text: str) -> None:
        (self.tmp / ".github" / "workflows" / name).write_text(text, encoding="utf-8")

    def result(self, criterion: str) -> Result:
        return next(r for r in security.run(Repo(self.tmp)) if r.criterion == criterion)

    def test_a_secret_on_the_pull_request_path_is_caught(self) -> None:
        # The check that found six LLM API keys reachable from a pull request.
        self.workflow("ci.yml", "on:\n  pull_request:\njobs:\n  a:\n    steps:\n"
                                "      - env:\n          K: ${{ secrets.OPENAI_API_KEY }}\n")
        outcome = self.result("2.2")
        self.assertIs(outcome.status, Status.FAIL)
        self.assertIn("OPENAI_API_KEY", outcome.detail)

    def test_github_token_on_a_pull_request_is_not_a_finding(self) -> None:
        self.workflow("ci.yml", "on:\n  pull_request:\njobs:\n  a:\n    steps:\n"
                                "      - env:\n          K: ${{ secrets.GITHUB_TOKEN }}\n")
        self.assertIs(self.result("2.2").status, Status.PASS)

    def test_a_secret_on_a_scheduled_workflow_is_not_a_finding(self) -> None:
        # The correct place for provider credentials: no pull request reaches it.
        self.workflow("nightly.yml", "on:\n  schedule:\n    - cron: '0 3 * * *'\njobs:\n  a:\n"
                                     "    steps:\n      - env:\n          K: ${{ secrets.OPENAI_API_KEY }}\n")
        self.assertIs(self.result("2.2").status, Status.PASS)

    def test_an_unpinned_action_is_caught_and_a_local_one_is_not(self) -> None:
        self.workflow("ci.yml", "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n")
        self.assertIs(self.result("2.1").status, Status.FAIL)
        self.workflow("ci.yml", "jobs:\n  a:\n    steps:\n      - uses: ./\n")
        self.assertIs(self.result("2.1").status, Status.NOT_APPLICABLE)


if __name__ == "__main__":
    unittest.main(verbosity=1)


class SelfReferenceTests(unittest.TestCase):
    """The checks must not flag code that merely discusses what they detect.

    Both cases below are ones this tool failed against its own source: the
    TODO check matched the regex that defines it, and the rubric's own row
    describing the rule.
    """

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_self"
        self.tmp.mkdir(exist_ok=True)
        self.addCleanup(self._clean)

    def _clean(self) -> None:
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.tmp.rmdir()

    def outcome(self, name: str, text: str, criterion: str) -> Result:
        (self.tmp / name).write_text(text, encoding="utf-8")
        return next(r for r in maintainability.run(Repo(self.tmp)) if r.criterion == criterion)

    def test_a_pattern_that_mentions_todo_is_not_a_todo(self) -> None:
        source = 'marker = re.compile(r"\\\\b(TODO|FIXME)\\\\b")\n'
        self.assertIs(self.outcome("m.py", source, "9.10").status, Status.PASS)

    def test_a_string_containing_todo_is_not_a_todo(self) -> None:
        self.assertIs(self.outcome("m.py", 'label = "TODO"\n', "9.10").status, Status.PASS)

    def test_a_todo_in_a_comment_is_still_caught(self) -> None:
        self.assertIs(self.outcome("m.py", "x = 1  # TODO: later\n", "9.10").status, Status.FAIL)
