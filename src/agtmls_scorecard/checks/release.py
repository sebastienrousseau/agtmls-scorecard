# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 7 — Release Engineering."""

from __future__ import annotations

import re

from ..model import Result, Status
from ..repo import Repo

TITLE = "Release Engineering"

#: A version that appears in many files is a version that will disagree with
#: itself. Generated artifacts legitimately restate it, so they are excluded.
GENERATED = ("sbom", "provenance", "index.json", "agent-card", "mcp-resources", "catalog", "lock")
#: A changelog states which version *was* released. That is a record, and a
#: record is supposed to accumulate versions -- counting it as a place the
#: current version can drift asks a project to rewrite its own history.
RECORDS = ("changelog", "history", "releases", "news")


def _generator_outputs(repo: Repo) -> set[str]:
    """Repo-relative paths that a script in this repository writes.

    A per-provider manifest restates the version because a generator put it
    there, so it cannot drift independently -- regenerating fixes it. Asking
    which paths the repository's own code names is a cheap way to tell an
    authored carrier from a generated one, without this tool needing a list of
    any particular project's artifacts.
    """
    sources = "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in repo.by_suffix(".py", ".rs", ".js", ".ts", ".sh")
    )
    return {
        str(p.relative_to(repo.root))
        for p in repo.files
        if f'"{p.relative_to(repo.root)}"' in sources
        or f"'{p.relative_to(repo.root)}'" in sources
    }


def _tag_triggered(repo: Repo) -> Result:
    release = repo.workflows.get("release.yml", "")
    if not release:
        return Result("7.1", "Releases are automated from a tag", Status.FAIL,
                      "no release workflow: releasing by hand is a process, not a pipeline")
    if re.search(r"tags:\s*\n?\s*-", release) or "refs/tags/" in release:
        return Result("7.1", "Releases are automated from a tag", Status.PASS, "tag-triggered")
    return Result("7.1", "Releases are automated from a tag", Status.FAIL,
                  "release workflow is not triggered by a tag")


def _version_single_source(repo: Repo) -> Result:
    manifest = {
        "rust": ("Cargo.toml", r'^version\s*=\s*"([^"]+)"'),
        "python": ("pyproject.toml", r'^version\s*=\s*"([^"]+)"'),
        "node": ("package.json", r'"version"\s*:\s*"([^"]+)"'),
    }.get(repo.kind)
    if manifest is None:
        return Result("7.2", "Version lives in one place", Status.NOT_APPLICABLE,
                      "no package manifest")
    text = repo.read(manifest[0]) or ""
    match = re.search(manifest[1], text, re.MULTILINE)
    if not match:
        return Result("7.2", "Version lives in one place", Status.FAIL,
                      f"no version in {manifest[0]}")
    version = match.group(1)
    if version.count(".") < 2:
        return Result("7.2", "Version lives in one place", Status.FAIL,
                      f"{version!r} is not a semver triple")

    written_by_a_generator = _generator_outputs(repo)
    carriers = [
        str(p.relative_to(repo.root))
        for p in repo.by_suffix(".toml", ".json", ".py", ".rs", ".md")
        if not any(g in p.name.lower() for g in GENERATED)
        and not any(r in p.name.lower() for r in RECORDS)
        and str(p.relative_to(repo.root)) not in written_by_a_generator
        and re.search(rf'["\s=]{re.escape(version)}["\s,]', p.read_text(encoding="utf-8", errors="replace"))
    ]
    if len(carriers) > 6:
        return Result("7.2", "Version lives in one place", Status.FAIL,
                      f"{version} appears in {len(carriers)} authored files; each is a place it can drift")
    return Result("7.2", "Version lives in one place", Status.PASS,
                  f"{version} in {len(carriers)} authored file(s)")


def _dry_run(repo: Repo) -> Result:
    release = repo.workflows.get("release.yml", "")
    if not release:
        return Result("7.5", "A dry run exercises the release without publishing", Status.NOT_APPLICABLE,
                      "no release workflow")
    if "dry_run" in release or "--dry-run" in release:
        return Result("7.5", "A dry run exercises the release without publishing", Status.PASS,
                      "dry-run path present")
    return Result("7.5", "A dry run exercises the release without publishing", Status.FAIL,
                  "no rehearsal: the first real run would be the first run")


def _tag_matches_version(repo: Repo) -> Result:
    release = repo.workflows.get("release.yml", "")
    if not release:
        return Result("7.7", "Tag is checked against the declared version", Status.NOT_APPLICABLE,
                      "no release workflow")
    if re.search(r"(does not match|GITHUB_REF_NAME|tag.*version|version.*tag)", release, re.IGNORECASE):
        return Result("7.7", "Tag is checked against the declared version", Status.PASS,
                      "the workflow compares them")
    return Result("7.7", "Tag is checked against the declared version", Status.FAIL,
                  "a mistyped tag would publish the wrong thing under the right name")


def run(repo: Repo) -> list[Result]:
    return [
        _tag_triggered(repo),
        _version_single_source(repo),
        Result("7.3", "Builds are reproducible", Status.UNVERIFIED,
               "needs two builds and a byte comparison; not attempted from a static read"),
        Result("7.4", "Every generated artifact has a --check mode in CI", Status.UNVERIFIED,
               "requires knowing which artifacts are generated, which varies by project"),
        _dry_run(repo),
        Result("7.6", "Release assets verified after publication", Status.UNVERIFIED,
               "needs a published release to inspect"),
        _tag_matches_version(repo),
        Result("7.8", "Rollback documented and rehearsed", Status.UNVERIFIED,
               "a documented rollback is checkable; a rehearsed one is not"),
        Result("7.9", "Pre-release smoke-tested before the stable tag", Status.UNVERIFIED,
               "needs release history"),
        Result("7.10", "Cross-repository compatibility validated", Status.UNVERIFIED,
               "cross-repository; this tool scores one repository at a time"),
    ]
