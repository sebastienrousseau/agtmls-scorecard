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

import json  # noqa: E402  (sys.path is set above)

from agtmls_scorecard import checks  # noqa: E402  (sys.path is set above)
from agtmls_scorecard.checks import (  # noqa: E402  (sys.path is set above)
    documentation,
    dx,
    interoperability,
    maintainability,
    observability,
    performance,
    release,
    security,
)
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


class RefinementTests(unittest.TestCase):
    """Cases the checks got wrong when first run across the ecosystem."""

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_refine"
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

    def outcome(self, results: list[Result], criterion: str) -> Result:
        return next(r for r in results if r.criterion == criterion)

    def test_dropping_argv_zero_is_not_a_skipped_test(self) -> None:
        from agtmls_scorecard.checks import correctness

        self.write("main.rs", "let args: Vec<String> = std::env::args().skip(1).collect();\n")
        self.assertIs(self.outcome(correctness.run(Repo(self.tmp)), "1.6").status, Status.PASS)

    def test_a_disabled_test_is_still_caught(self) -> None:
        from agtmls_scorecard.checks import correctness

        self.write("a.test.mjs", "test.skip('later', () => {});\n")
        self.assertIs(self.outcome(correctness.run(Repo(self.tmp)), "1.6").status, Status.FAIL)

    def test_generated_code_is_not_judged_on_its_shape(self) -> None:
        self.write("gen.js", "// @generated by a tool. Do not edit.\n" + "x\n" * 900)
        self.assertIs(self.outcome(maintainability.run(Repo(self.tmp)), "9.7").status, Status.PASS)

    def test_an_oversized_authored_file_is_still_caught(self) -> None:
        self.write("big.py", "x = 1\n" * 900)
        self.assertIs(self.outcome(maintainability.run(Repo(self.tmp)), "9.7").status, Status.FAIL)

    def test_a_pattern_defining_skip_detection_is_not_a_skipped_test(self) -> None:
        from agtmls_scorecard.checks import correctness

        self.write("c.py", 'pattern = re.compile(r"\\\\b(it|test)\\\\.(skip|todo)\\\\s*\\\\(")\n')
        self.assertIs(self.outcome(correctness.run(Repo(self.tmp)), "1.6").status, Status.PASS)


class NewCategoryTests(unittest.TestCase):
    """The four categories that were whole-category placeholders.

    Each was 0.0 at zero coverage, which was honest and useless: a repository
    could read 9.3/10 while nothing had ever asked whether it was fast,
    diagnosable, scriptable or conformant.
    """

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_cat"
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

    # -- performance -------------------------------------------------------

    def test_a_benchmark_with_no_durations_is_not_a_benchmark(self) -> None:
        # The exact state agtmls' own bench.py was in: it re-ran three
        # validators and printed a quality score.
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.write("benchmarks/results/run.json", '{"suites": 3, "quality": 100}')
        outcome = self.result(performance.run(Repo(self.tmp)), "3.1")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    def test_a_benchmark_with_durations_passes(self) -> None:
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.write("benchmarks/results/run.json", '{"workloads": {"a": {"p50_ms": 12.0}}}')
        outcome = self.result(performance.run(Repo(self.tmp)), "3.1")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_a_baseline_nobody_compares_against_is_not_a_gate(self) -> None:
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.write("bench-baseline.json", '{"workloads": {"a": {"ratio_to_calibration": 1.0}}}')
        outcome = self.result(performance.run(Repo(self.tmp)), "3.2")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)
        self.write(".github/workflows/bench.yml", "jobs:\n  b:\n    steps:\n      - run: bench.py --check\n")
        outcome = self.result(performance.run(Repo(self.tmp)), "3.2")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_cold_start_needs_a_declared_budget_and_declared_surfaces(self) -> None:
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.write("bench-baseline.json", '{"workloads": {"a": {"p50_ms": 30.0}}}')
        outcome = self.result(performance.run(Repo(self.tmp)), "3.10")
        self.assertIs(outcome.status, Status.UNVERIFIED, outcome.detail)
        self.write("bench-baseline.json", json.dumps({
            "cold_start_budget_ms": 100,
            "workloads": {"cli": {"p50_ms": 30.0, "interactive": True}},
        }))
        outcome = self.result(performance.run(Repo(self.tmp)), "3.10")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)
        self.write("bench-baseline.json", json.dumps({
            "cold_start_budget_ms": 100,
            "workloads": {"cli": {"p50_ms": 430.0, "interactive": True}},
        }))
        outcome = self.result(performance.run(Repo(self.tmp)), "3.10")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    # -- developer experience ---------------------------------------------

    def test_json_on_a_minority_of_the_surface_is_not_a_machine_interface(self) -> None:
        # agtmls had --json on 10 of 35 subcommands. A presence check would
        # have called that solved.
        commands = "\n".join(f'sub.add_parser("cmd{i}")' for i in range(10))
        self.write("cli.py", commands + '\np.add_argument("--json")\n')
        outcome = self.result(dx.run(Repo(self.tmp)), "4.1")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    def test_a_tally_is_not_an_error_missing_a_remedy(self) -> None:
        # "FAIL: 3 issue(s)" is printed under errors that already explained
        # themselves; demanding a remedy there makes every summary worse.
        body = "\n".join(
            f'print(f"FAIL: {{len(errors)}} configuration problem(s) found here {i}")'
            for i in range(8)
        )
        self.write("m.py", body + '\nprint(f"FAIL: the widget is broken; run repair.py")\n' * 3)
        outcome = self.result(dx.run(Repo(self.tmp)), "4.5")
        self.assertIsNot(outcome.status, Status.FAIL, outcome.detail)

    def test_a_destructive_command_without_dry_run_still_fails(self) -> None:
        self.write("cli.py", 'sub.add_parser("install")\nsub.add_parser("uninstall")\n')
        outcome = self.result(dx.run(Repo(self.tmp)), "4.2")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    # -- observability -----------------------------------------------------

    def test_a_library_is_not_failed_for_having_no_version_flag(self) -> None:
        # Asking a WASM module for --version produces a finding nobody can act
        # on, and a scorer that cries wolf gets switched off.
        self.write("Cargo.toml", '[package]\nname = "lib"\n')
        self.write("src/lib.rs", "pub fn f() {}\n")
        outcome = self.result(observability.run(Repo(self.tmp)), "6.8")
        self.assertIs(outcome.status, Status.NOT_APPLICABLE, outcome.detail)

    def test_a_command_without_a_version_flag_still_fails(self) -> None:
        self.write("Cargo.toml", '[package]\nname = "tool"\n')
        self.write("src/main.rs", "fn main() { Command::new(\"go\"); }\n")
        outcome = self.result(observability.run(Repo(self.tmp)), "6.8")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    def test_no_telemetry_is_not_provable_by_absence(self) -> None:
        self.write("pyproject.toml", "[project]\nname='x'\n")
        self.write("m.py", "print('hello')\n")
        outcome = self.result(observability.run(Repo(self.tmp)), "6.10")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)
        self.assertIn("control", outcome.detail)

    # -- interoperability --------------------------------------------------

    def test_git_plus_https_is_not_an_invented_scheme(self) -> None:
        # A composed standard scheme, emitted by pip, SPDX and Cargo alike.
        self.write("provenance.json", '{"uri": "git+https://example.com/x"}')
        outcome = self.result(interoperability.run(Repo(self.tmp)), "8.2")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_an_undocumented_invented_scheme_is_still_caught(self) -> None:
        self.write("m.py", 'URI = "' + "agtmls" + '://skill/handoff"\n')
        outcome = self.result(interoperability.run(Repo(self.tmp)), "8.2")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    def test_prose_denying_a_deprecation_is_not_a_deprecation(self) -> None:
        # SUPPORT.md said a release is "unsupported, not deprecated", and an
        # earlier version of this check read that as a deprecation.
        self.write("SUPPORT.md", "A release older than the newest patch is\n"
                                 "unsupported, not deprecated.\n")
        outcome = self.result(interoperability.run(Repo(self.tmp)), "8.9")
        self.assertIs(outcome.status, Status.NOT_APPLICABLE, outcome.detail)

    def test_a_marked_deprecation_without_a_removal_still_fails(self) -> None:
        self.write("schema.json", '{"field": {"dep' + 'recated": true}}')
        outcome = self.result(interoperability.run(Repo(self.tmp)), "8.9")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    def test_an_emitted_format_nobody_validates_fails(self) -> None:
        self.write("SBOM.spdx.json", '{"spdxVersion": "SPDX-2.3"}')
        outcome = self.result(interoperability.run(Repo(self.tmp)), "8.1")
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)
        self.write(".github/workflows/ci.yml", "steps:\n  - run: pyspdxtools -i SBOM.spdx.json\n")
        outcome = self.result(interoperability.run(Repo(self.tmp)), "8.1")
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_a_repo_emitting_no_standard_format_is_not_failed_for_it(self) -> None:
        self.write("README.md", "# nothing here\n")
        outcome = self.result(interoperability.run(Repo(self.tmp)), "8.1")
        self.assertIs(outcome.status, Status.NOT_APPLICABLE, outcome.detail)


