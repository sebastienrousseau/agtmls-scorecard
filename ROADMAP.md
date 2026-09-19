<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau -->
<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Roadmap

The number that matters here is **coverage**, not score.

## Now

- Six of ten categories have checkers. Four do not, and say so.

## Next

- **API & Developer Experience.** The pattern exists in `agtmls`: enumerate
  the CLI surface, invoke every command, assert none crashes. Generalising it
  needs a per-language surface reader.
- **Observability.** Needs a running process; `--log-format=json` and an exit
  code taxonomy are both checkable by invoking the tool under test.
- **Interoperability.** Each emitted format validated against its upstream
  schema. Needs network access, so it belongs behind a flag.

## Not planned

- **Weighted scores.** Choosing weights is the judgement this tool removes.
- **A grade.** It reports what it could see.
