# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Tests for scorecard rubric enforcement and capability declarations."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from agtmls_scorecard import checks  # noqa: E402  (sys.path is set above)
from agtmls_scorecard.checks import (  # noqa: E402  (sys.path is set above)
    interoperability,
    performance,
    release,
)
from agtmls_scorecard.model import Result, Status  # noqa: E402  (sys.path is set above)
from agtmls_scorecard.repo import Repo  # noqa: E402  (sys.path is set above)


class EveryCategoryIsImplementedTests(unittest.TestCase):
    def test_no_category_is_a_placeholder(self) -> None:
        """PENDING is the mechanism for declaring an unwritten checker.

        It stays in the code so the next omission is counted rather than
        silent, but it must be empty: a whole category scored 0.0 at zero
        coverage is a category nobody is measuring.
        """
        self.assertEqual(checks.PENDING, [])
        self.assertEqual(len(checks.IMPLEMENTED), 10)

    #: category id -> its number in the rubric.
    NUMBERS = {
        "correctness": 1, "security": 2, "performance": 3, "dx": 4,
        "documentation": 5, "observability": 6, "release": 7,
        "interoperability": 8, "maintainability": 9, "governance": 10,
    }

    def test_every_rubric_criterion_is_decided(self) -> None:
        """All ten of each category's criteria, one way or another.

        Sub-criteria like 1.0 and 9.1b are fine; a *missing* one is not. This
        caught criterion 2.10, whose checker had been written and never called
        from run() -- so it was absent from every report this tool had ever
        produced, which is the defect it exists to catch.
        """
        repo = Repo(Path(__file__).resolve().parent.parent)
        for identifier, module in checks.IMPLEMENTED:
            number = self.NUMBERS[identifier]
            decided = {r.criterion for r in module.run(repo)}
            missing = sorted(
                c for c in (f"{number}.{i}" for i in range(1, 11)) if c not in decided
            )
            self.assertEqual(missing, [], f"{identifier} decides nothing for {missing}")


class ScalingDeclarationTests(unittest.TestCase):
    """Superlinear growth is a defect on a hot path and a fact everywhere else."""

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_scale"
        self.tmp.mkdir(exist_ok=True)
        (self.tmp / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (self.tmp / "benchmarks").mkdir(exist_ok=True)
        self.addCleanup(self._clean)

    def _clean(self) -> None:
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.tmp.rmdir()

    def scaling(self, **extra) -> Result:
        payload = {"growth": {"size": 10.0, "digest": 9.5, "pairwise": 73.4}, **extra}
        (self.tmp / "benchmarks" / "scaling.json").write_text(
            json.dumps(payload), encoding="utf-8")
        results = performance.run(Repo(self.tmp))
        return next(r for r in results if r.criterion == "3.5")

    def test_undeclared_superlinear_growth_fails(self) -> None:
        outcome = self.scaling()
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)
        self.assertIn("pairwise", outcome.detail)

    def test_a_path_declared_cold_is_not_a_defect(self) -> None:
        outcome = self.scaling(cold_paths=["pairwise"])
        self.assertIs(outcome.status, Status.PASS, outcome.detail)

    def test_declaring_a_path_cold_does_not_excuse_the_others(self) -> None:
        # The escape hatch must not be a blanket one.
        outcome = self.scaling(
            growth={"size": 10.0, "digest": 95.0, "pairwise": 73.4},
            cold_paths=["pairwise"],
        )
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)
        self.assertIn("digest", outcome.detail)


class VersionCarrierTests(unittest.TestCase):
    """A version in many authored files is a version that disagrees with itself.

    But a per-provider manifest restates it because a generator put it there,
    and a changelog restates every version it ever shipped. Counting either
    asks a project to fix something regenerating already fixes.
    """

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_ver"
        self.tmp.mkdir(exist_ok=True)
        (self.tmp / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")
        self.addCleanup(self._clean)

    def _clean(self) -> None:
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.tmp.rmdir()

    def write(self, name: str, text: str) -> None:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def outcome(self) -> Result:
        return next(r for r in release.run(Repo(self.tmp)) if r.criterion == "7.2")

    def test_a_version_hardcoded_across_authored_files_still_fails(self) -> None:
        for i in range(8):
            self.write(f"pkg{i}/meta.json", '{"version": "1.2.3"}')
        self.assertIs(self.outcome().status, Status.FAIL, self.outcome().detail)

    def test_files_a_generator_writes_are_not_authored_carriers(self) -> None:
        for i in range(8):
            self.write(f"pkg{i}/meta.json", '{"version": "1.2.3"}')
        # A script in the repository names each path, so regenerating fixes
        # any drift and they cannot disagree independently.
        named = "\n".join(f'TARGETS = "pkg{i}/meta.json"' for i in range(8))
        self.write("generate.py", named + "\n")
        self.assertIs(self.outcome().status, Status.PASS, self.outcome().detail)

    def test_a_changelog_listing_old_versions_is_not_a_carrier(self) -> None:
        self.write("CHANGELOG.md", "## 1.2.3 - 2026-01-01\n## 1.2.2 - 2025-12-01\n")
        self.assertIs(self.outcome().status, Status.PASS, self.outcome().detail)


class ClaimedStandardTests(unittest.TestCase):
    """A document is judged against the standard it claims.

    A2A's `url` is a live service endpoint. A project without one cannot
    publish a truthful A2A card, and a rubric that demands one is a rubric
    that rewards inventing the URL.
    """

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_card"
        self.tmp.mkdir(exist_ok=True)
        self.addCleanup(self._clean)

    def _clean(self) -> None:
        for path in sorted(self.tmp.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        self.tmp.rmdir()

    def card(self, payload: dict) -> Result:
        (self.tmp / "agent-card.json").write_text(json.dumps(payload), encoding="utf-8")
        return next(r for r in interoperability.run(Repo(self.tmp)) if r.criterion == "8.4")

    def test_a_card_claiming_a2a_is_held_to_a2a(self) -> None:
        outcome = self.card({"protocolVersion": "0.3.0", "name": "x"})
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)
        self.assertIn("url", outcome.detail)

    def test_a_card_declaring_another_kind_is_not_held_to_a2a(self) -> None:
        outcome = self.card({"kind": "registry-card", "name": "x"})
        self.assertIs(outcome.status, Status.NOT_APPLICABLE, outcome.detail)

    def test_a_card_claiming_nothing_fails(self) -> None:
        # The loophole closed: silence is not an exemption.
        outcome = self.card({"name": "x", "capabilities": ["a", "b"]})
        self.assertIs(outcome.status, Status.FAIL, outcome.detail)

    def test_a_complete_a2a_card_passes(self) -> None:
        outcome = self.card({
            "protocolVersion": "0.3.0", "name": "x", "description": "d",
            "url": "https://example.com/a2a", "version": "1.0.0",
            "capabilities": {"streaming": False},
            "defaultInputModes": ["text/plain"], "defaultOutputModes": ["text/plain"],
            "provider": {"organization": "o", "url": "https://example.com"},
        })
        self.assertIs(outcome.status, Status.PASS, outcome.detail)
