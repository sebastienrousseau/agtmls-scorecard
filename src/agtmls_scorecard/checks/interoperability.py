# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 8 — Interoperability & Standards Conformance.

The previous placeholder said this needed "network access and per-format
validators". Running the validators does. Knowing whether anyone runs them
does not, and that is the part that decides whether a format is conformant or
merely emitted.

The distinction this category turns on: **emitting a format and conforming to
it are different claims.** A file called `SBOM.spdx.json` is an assertion; a
CI step that pipes it through `pyspdxtools` is a check. Every criterion below
looks for the second thing wherever the first is present, and says so plainly
when only the first is there.

A repository that emits none of these formats is `n/a`, not failing — being
graded on an MCP surface you never claimed to have is how a rubric becomes
something to argue with rather than something to satisfy.
"""

from __future__ import annotations

import json
import re

from ..model import Result, Status
from ..repo import Repo

TITLE = "Interoperability & Standards Conformance"

#: (what it is, how to recognise the artifact, what validating it looks like)
FORMATS = {
    "spdx": (re.compile(r"spdx", re.IGNORECASE),
             re.compile(r"pyspdxtools|spdx-tools|spdx.*validat", re.IGNORECASE)),
    "cyclonedx": (re.compile(r"cyclonedx", re.IGNORECASE),
                  re.compile(r"cyclonedx.*validat|cyclonedx-cli", re.IGNORECASE)),
    "sarif": (re.compile(r"\.sarif\b|sarif", re.IGNORECASE),
              re.compile(r"sarif.*(schema|validat)|upload-sarif", re.IGNORECASE)),
    "in-toto": (re.compile(r"in-toto|provenance", re.IGNORECASE),
                re.compile(r"attest|slsa-verifier|in-toto.*validat", re.IGNORECASE)),
}
#: URI schemes a project invented for itself.
CUSTOM_SCHEME = re.compile(r"\b([a-z][a-z0-9+.-]{2,15})://")
KNOWN_SCHEMES = {
    "http", "https", "file", "git", "ssh", "ftp", "data", "mailto", "urn",
    "pkg", "swid", "docker", "oci", "npm", "crates", "pypi", "vscode",
}


def _is_standard(scheme: str) -> bool:
    """`git+https` is two standard schemes composed, which RFC 3986 allows and
    pip, SPDX and Cargo all emit. Splitting on `+` stops the check reporting
    every dependency URL in the repository as an invention."""
    return all(part in KNOWN_SCHEMES for part in scheme.split("+") if part)


A2A_REQUIRED = ("protocolVersion", "url", "capabilities", "defaultInputModes",
                "defaultOutputModes", "provider")
#: A *marked* deprecation, not prose about one. SUPPORT.md saying a release is
#: "unsupported, not deprecated" was read as a deprecation by an earlier
#: version of this check -- a sentence denying the thing, scored as the thing.
DEPRECATION = re.compile(
    r'"deprecated"\s*:'              # JSON / package manifests
    r"|^\s*deprecated\s*:"           # YAML
    r"|@deprecated\b|DeprecationWarning"   # Python
    r"|#\[deprecated"                 # Rust
    r"|@Deprecated\b",                # Java / Kotlin / TS decorators
    re.IGNORECASE | re.MULTILINE,
)
REMOVAL = re.compile(r"removed?[_\s-]*(in|version|at)|removal[_\s-]*version|sunset", re.IGNORECASE)
HISTORICAL_DOC = re.compile(r"CHANGELOG|HISTORY|RELEASES|NEWS", re.IGNORECASE)


def _emitted(repo: Repo, pattern: re.Pattern) -> list[str]:
    return [
        str(p.relative_to(repo.root)) for p in repo.files
        if pattern.search(p.name)
    ]


def _format_validated(repo: Repo, key: str, criterion: str, title: str) -> Result:
    recognise, validate = FORMATS[key]
    emitted = _emitted(repo, recognise)
    if not emitted:
        return Result(criterion, title, Status.NOT_APPLICABLE, f"emits no {key} document")
    if validate.search(repo.workflow_text):
        return Result(criterion, title, Status.PASS,
                      f"{emitted[0]} validated in CI")
    return Result(criterion, title, Status.FAIL,
                  f"{emitted[0]} is emitted but never validated against its schema; "
                  "the file asserts conformance rather than demonstrating it")


def _all_formats_validated(repo: Repo) -> Result:
    title = "Every emitted format is validated against its schema"
    emitted = {k: _emitted(repo, v[0]) for k, v in FORMATS.items()}
    present = {k: v for k, v in emitted.items() if v}
    if not present:
        return Result("8.1", title, Status.NOT_APPLICABLE, "emits no standard format")
    unvalidated = [k for k in present if not FORMATS[k][1].search(repo.workflow_text)]
    if unvalidated:
        return Result("8.1", title, Status.FAIL,
                      f"{len(present)} format(s) emitted, {len(unvalidated)} never "
                      f"validated: {', '.join(sorted(unvalidated))}")
    return Result("8.1", title, Status.PASS,
                  f"all {len(present)} emitted format(s) validated in CI")


def _uri_schemes(repo: Repo) -> Result:
    title = "No invented URI scheme where a standard one exists"
    invented: dict[str, str] = {}
    for path in repo.by_suffix(".py", ".rs", ".ts", ".js", ".json", ".md"):
        for match in CUSTOM_SCHEME.finditer(path.read_text(encoding="utf-8", errors="replace")):
            scheme = match.group(1).lower()
            if not _is_standard(scheme):
                invented.setdefault(scheme, str(path.relative_to(repo.root)))
    if not invented:
        return Result("8.2", title, Status.PASS, "no custom scheme")
    # An invented scheme is defensible when it is specified. Undocumented is
    # the failure, not custom.
    documented = {
        s for s in invented
        if any(f"{s}://" in p.read_text(encoding="utf-8", errors="replace")
               for p in repo.by_suffix(".md"))
    }
    undocumented = sorted(set(invented) - documented)
    if undocumented:
        return Result("8.2", title, Status.FAIL,
                      f"undocumented scheme(s): {', '.join(f'{s}://' for s in undocumented)}")
    return Result("8.2", title, Status.PASS,
                  f"{len(invented)} custom scheme(s), each documented")


def _a2a_card(repo: Repo) -> Result:
    title = "An agent card validates against the A2A schema"
    cards = [p for p in repo.files if "agent-card" in p.name or p.name == "agent.json"]
    if not cards:
        return Result("8.4", title, Status.NOT_APPLICABLE, "publishes no agent card")
    try:
        data = json.loads(cards[0].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Result("8.4", title, Status.FAIL, f"{cards[0].name} is not valid JSON")
    missing = [k for k in A2A_REQUIRED if k not in data]
    if missing:
        return Result("8.4", title, Status.FAIL,
                      f"{cards[0].name} omits required field(s): {', '.join(missing)}")
    if not isinstance(data.get("capabilities"), dict):
        return Result("8.4", title, Status.FAIL,
                      f"{cards[0].name}: capabilities must be an object, found "
                      f"{type(data.get('capabilities')).__name__}")
    return Result("8.4", title, Status.PASS,
                  f"{cards[0].name} carries every required A2A field")


def _conformance_corpus(repo: Repo) -> Result:
    title = "A conformance corpus is replayed in CI"
    corpus = [p for p in repo.files if "corpus" in str(p).lower() or "conformance" in str(p).lower()]
    if not corpus:
        return Result("8.8", title, Status.NOT_APPLICABLE,
                      "declares no conformance corpus")
    if re.search(r"conformance|corpus", repo.workflow_text, re.IGNORECASE):
        return Result("8.8", title, Status.PASS,
                      f"{len(corpus)} corpus file(s), replayed in CI")
    return Result("8.8", title, Status.FAIL,
                  f"{len(corpus)} corpus file(s) that CI never replays; a corpus "
                  "nobody runs is a directory")


def _deprecations(repo: Repo) -> Result:
    title = "Deprecated fields carry a removal version"
    # A changelog entry saying something *was* deprecated is a record, not a
    # live deprecation needing an end date. Scoring it asks a project to
    # rewrite its own history every release.
    deprecating = [
        p for p in repo.by_suffix(".json", ".yml", ".yaml", ".py", ".rs", ".ts")
        if not HISTORICAL_DOC.search(p.name)
        and DEPRECATION.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    if not deprecating:
        return Result("8.9", title, Status.NOT_APPLICABLE, "nothing is marked deprecated")
    without = [
        str(p.relative_to(repo.root)) for p in deprecating
        if not REMOVAL.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    if without:
        return Result("8.9", title, Status.FAIL,
                      f"deprecated without a stated removal in {without[0]}: a "
                      "deprecation with no end date never ends")
    return Result("8.9", title, Status.PASS, "every deprecation states its removal")


def run(repo: Repo) -> list[Result]:
    return [
        _all_formats_validated(repo),
        _uri_schemes(repo),
        Result("8.3", "The MCP surface passes Inspector conformance", Status.UNVERIFIED,
               "needs the server running under MCP Inspector"),
        _a2a_card(repo),
        Result("8.5", "The LSP surface passes a conformance harness", Status.UNVERIFIED,
               "needs the server running against a protocol test suite"),
        _format_validated(repo, "cyclonedx", "8.6", "SPDX and CycloneDX both emitted and valid"),
        _format_validated(repo, "sarif", "8.7", "SARIF validates against its schema"),
        _conformance_corpus(repo),
        _deprecations(repo),
        Result("8.10", "Capability negotiation rather than version sniffing",
               Status.UNVERIFIED,
               "a protocol design question; a static read cannot tell negotiation "
               "from a version comparison that happens to work"),
    ]
