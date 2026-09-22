# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 2 — Security & Supply Chain."""

from __future__ import annotations

import json
import re

from ..model import Result, Status
from ..repo import Repo

TITLE = "Security & Supply Chain"

#: A local action (`./`) has no SHA to pin; a docker:// reference is pinned by
#: its own digest rules. Neither is a finding.
LOCAL = re.compile(r"^(\./|docker://)")
SHA_PINNED = re.compile(r"@[0-9a-f]{40}$")


def _pinned_actions(repo: Repo) -> Result:
    uses = [(f, u) for f, u in repo.action_uses if not LOCAL.match(u)]
    if not uses:
        return Result("2.1", "Actions pinned to a commit SHA", Status.NOT_APPLICABLE,
                      "no third-party actions used")
    unpinned = [f"{f}: {u}" for f, u in uses if not SHA_PINNED.search(u)]
    if unpinned:
        return Result("2.1", "Actions pinned to a commit SHA", Status.FAIL,
                      f"{len(unpinned)} unpinned, e.g. {unpinned[0]}")
    return Result("2.1", "Actions pinned to a commit SHA", Status.PASS,
                  f"all {len(uses)} pinned")


def _secrets_off_pull_request(repo: Repo) -> Result:
    """Secrets reachable from a workflow that runs on pull_request.

    Fork pull requests get no secrets, but a branch in the same repository
    does -- including a branch that edits the workflow. This is the check that
    found six LLM API keys on the PR path of the repository this tool was
    written for.
    """
    exposed: list[str] = []
    for name, text in repo.workflows.items():
        triggers = text.split("jobs:", 1)[0]
        if not re.search(r"^\s*pull_request:?\s*$", triggers, re.MULTILINE):
            continue
        for secret in re.findall(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", text):
            if secret != "GITHUB_TOKEN":
                exposed.append(f"{name}:{secret}")
    if not repo.workflows:
        return Result("2.2", "No secret reachable from pull_request", Status.NOT_APPLICABLE,
                      "no workflows")
    if exposed:
        return Result("2.2", "No secret reachable from pull_request", Status.FAIL,
                      f"{len(set(exposed))} exposed: {', '.join(sorted(set(exposed))[:3])}")
    return Result("2.2", "No secret reachable from pull_request", Status.PASS,
                  "only GITHUB_TOKEN, if any")


def _lockfile(repo: Repo) -> Result:
    expected = {"rust": "Cargo.lock", "node": "package-lock.json", "python": None, "docs": None}[repo.kind]
    if expected is None:
        return Result("2.3", "Dependencies pinned, lockfile committed", Status.NOT_APPLICABLE,
                      f"{repo.kind} project; no lockfile convention enforced here")
    if repo.exists(expected):
        return Result("2.3", "Dependencies pinned, lockfile committed", Status.PASS, expected)
    manifest = repo.read({"rust": "Cargo.toml", "node": "package.json"}[repo.kind]) or ""
    if repo.kind == "node" and '"dependencies"' not in manifest:
        return Result("2.3", "Dependencies pinned, lockfile committed", Status.NOT_APPLICABLE,
                      "no runtime dependencies to lock")
    return Result("2.3", "Dependencies pinned, lockfile committed", Status.FAIL,
                  f"no {expected}")


def _provenance(repo: Repo) -> Result:
    if "attest-build-provenance" in repo.workflow_text:
        return Result("2.4", "Release artifacts carry SLSA provenance", Status.PASS,
                      "attest-build-provenance in a workflow")
    release = repo.workflows.get("release.yml", "")
    if not release:
        return Result("2.4", "Release artifacts carry SLSA provenance", Status.NOT_APPLICABLE,
                      "no release workflow; nothing is published from here")
    # A release that ships only a git tag and generated notes produces no
    # artifact to attest. Provenance is a statement about a built thing.
    import re as _re
    builds = _re.search(r"(cargo publish|npm publish|python3? -m build|twine|upload-artifact|"
                        r"release create .*dist|wasm-pack build)", release, _re.IGNORECASE)
    if not builds:
        return Result("2.4", "Release artifacts carry SLSA provenance", Status.NOT_APPLICABLE,
                      "the release produces no built artifact, only a tag and notes")
    return Result("2.4", "Release artifacts carry SLSA provenance", Status.FAIL,
                  "release workflow does not attest its artifacts")


def _trusted_publishing(repo: Repo) -> Result:
    release = repo.workflows.get("release.yml", "")
    if not release:
        return Result("2.5", "Published via OIDC, no long-lived token", Status.NOT_APPLICABLE,
                      "no release workflow")
    # A workflow that publishes to no registry has no token to avoid. A
    # GitHub Action releases by moving a tag.
    if not re.search(r"(pypi|crates|npm publish|cargo publish|twine)", release, re.IGNORECASE):
        return Result("2.5", "Published via OIDC, no long-lived token", Status.NOT_APPLICABLE,
                      "release workflow publishes to no package registry")
    has_oidc = "id-token: write" in release
    has_env = re.search(r"environment:\s*\S", release) is not None
    token = re.findall(r"\$\{\{\s*secrets\.(\w*TOKEN\w*)\s*\}\}", release)
    long_lived = [t for t in token if t != "GITHUB_TOKEN"]
    if has_oidc and has_env and not long_lived:
        return Result("2.5", "Published via OIDC, no long-lived token", Status.PASS,
                      "id-token: write, gated by an environment")
    problems = []
    if not has_oidc:
        problems.append("no id-token: write")
    if not has_env:
        problems.append("no environment gate")
    if long_lived:
        problems.append(f"long-lived token(s): {', '.join(sorted(set(long_lived)))}")
    return Result("2.5", "Published via OIDC, no long-lived token", Status.FAIL, "; ".join(problems))


def _sbom(repo: Repo) -> Result:
    candidates = [p for p in repo.files if "sbom" in p.name.lower()]
    if not candidates:
        # Generating one at release time is equivalent, and for a project whose
        # lockfile moves it is better: a committed SBOM goes stale silently.
        if re.search(r"(cyclonedx|sbom|spdx)", repo.workflows.get("release.yml", ""), re.IGNORECASE):
            return Result("2.6", "SBOM validates and covers every shipped path", Status.PASS,
                          "generated by the release workflow")
        return Result("2.6", "SBOM validates and covers every shipped path", Status.FAIL,
                      "no SBOM, committed or generated at release")
    for path in candidates:
        if path.suffix != ".json":
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return Result("2.6", "SBOM validates and covers every shipped path", Status.FAIL,
                          f"{path.name} is not valid JSON")
        if document.get("spdxVersion"):
            missing = [k for k in ("creationInfo", "packages", "relationships") if k not in document]
            if missing:
                return Result("2.6", "SBOM validates and covers every shipped path", Status.FAIL,
                              f"{path.name} omits mandatory {', '.join(missing)}")
    return Result("2.6", "SBOM validates and covers every shipped path", Status.PASS,
                  f"{len(candidates)} document(s), structurally valid")


def _signature_gate(repo: Repo) -> Result:
    text = repo.workflow_text
    verifies = "%G?" in text or "verify-commit" in text or "verify-signatures" in text
    claims = bool(repo.exists("KEYS.asc"))
    if verifies:
        return Result("2.7", "Commit signatures verified in CI", Status.PASS,
                      "a workflow checks signatures")
    if claims:
        return Result("2.7", "Commit signatures verified in CI", Status.FAIL,
                      "KEYS.asc is published but nothing verifies against it: a policy, not a control")
    return Result("2.7", "Commit signatures verified in CI", Status.FAIL, "no signature gate")


def _security_policy(repo: Repo) -> Result:
    text = repo.read("SECURITY.md")
    if not text:
        return Result("2.10", "SECURITY.md with a disclosure channel and an SLA", Status.FAIL,
                      "no SECURITY.md")
    has_channel = "advisor" in text.lower() or "@" in text
    has_sla = re.search(r"\b\d+\s*(hours?|days?)\b", text, re.IGNORECASE) is not None
    if has_channel and has_sla:
        return Result("2.10", "SECURITY.md with a disclosure channel and an SLA", Status.PASS,
                      "channel and response window stated")
    missing = []
    if not has_channel:
        missing.append("no disclosure channel")
    if not has_sla:
        missing.append("no response window: 'we take security seriously' is not an SLA")
    return Result("2.10", "SECURITY.md with a disclosure channel and an SLA", Status.FAIL,
                  "; ".join(missing))


def run(repo: Repo) -> list[Result]:
    return [
        _pinned_actions(repo),
        _secrets_off_pull_request(repo),
        _lockfile(repo),
        _provenance(repo),
        _trusted_publishing(repo),
        _sbom(repo),
        _signature_gate(repo),
        Result("2.8", "Untrusted input is size-capped, symlink-safe, fail-closed", Status.UNVERIFIED,
               "requires reading the parser; no static check distinguishes a cap from its absence"),
        Result("2.9", "Analyzer conformance corpus green, including evasions", Status.UNVERIFIED,
               "would mean running another repository's test suite; the corpus runner does this"),
        # Written, and until now never called: criterion 2.10 was absent from
        # every report this tool produced, which is the defect it exists to
        # catch, in itself.
        _security_policy(repo),
    ]
