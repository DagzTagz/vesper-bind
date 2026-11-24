# State-machine audit, November 2026: vesper-bind

This page is the vesper-bind part of the full disclosure for the November 2026 implicit-state-machine audit of the DagzTagz repositories.

- The complete report, with every finding and how each was reproduced, is in [Dagz-Scaffold/docs/audits/2026-11-state-machine-audit.md](https://github.com/DagzTagz/Dagz-Scaffold/blob/main/docs/audits/2026-11-state-machine-audit.md). It also has the remediation status of all 13 findings.
- The audited commit is [`aa1e93c`](https://github.com/DagzTagz/vesper-bind/tree/aa1e93c86bf46780106c6410effe9113b454769c).

| Finding | Priority | What was wrong | Fix | Status |
|---|---|---|---|---|
| F2 | **High** | `bind` accepted a Dagz-Scaffold run that Dagz-Scaffold's own scorer fails, such as `quit_early: true` or `missing_evidence: true`, and wrote a receipt for it. **Reproduced.** The advisory is [ADVISORY-2026-11-24-bind-accepts-failed-scaffold-runs.md](ADVISORY-2026-11-24-bind-accepts-failed-scaffold-runs.md). | [PR #1](https://github.com/DagzTagz/vesper-bind/pull/1), [`d28061c`](https://github.com/DagzTagz/vesper-bind/commit/d28061c) | merged |
| F13 | Low | `pass_flags` were six literal `true` values instead of the result of the checks they name. | [PR #1](https://github.com/DagzTagz/vesper-bind/pull/1), [`d28061c`](https://github.com/DagzTagz/vesper-bind/commit/d28061c) | merged |
| F11 | Low | `--vesper-workspace` read `state.json`, and later wrote back the bytes it had prepared, with no lock and no check in between. A `vesper remember` that ran in that window was lost. | [`f948812`](https://github.com/DagzTagz/vesper-bind/commit/f948812) | this PR |
| F10 | Low | vesper-bind matches dagztagz-hypothesis-engine's retrieval strings (`ok_mock`, `mock://`). Those strings were free text in that repo. | No change here. [dagztagz-hypothesis-engine#4](https://github.com/DagzTagz/dagztagz-hypothesis-engine/pull/4) turns them into enums with the same values and documents them as a stable contract. | upstream PR |

## What changed for F11

- `prepare_note` now returns a `PreparedNote` that records the sha256 of the `state.json` it was built from.
- `commit_note` takes an exclusive `flock` on `<workspace>/.lock`, the lock vesper-runtime holds for `fork`, `remember`, `link` and `sleep`. It then re-reads `state.json` and refuses with `workspace state changed during bind` if the digest is different.
- When it refuses, `bind` exits 1, removes the receipt it just wrote, and leaves the other writer's change in place.
- `.lock` is opened with `O_NOFOLLOW` at mode `0600`.
- vesper-bind still does not import or vendor vesper-runtime. The shared contract (the lock file name and the STM note shape) is written down in vesper-runtime's `docs/memory.md`, under "Writers outside this program".

### What was not done

The audit suggested that vesper-bind could call vesper-runtime's `remember` instead of copying the STM rules. This repository's rules forbid vendoring vesper-runtime, and it has no runtime dependencies. So the contract is documented in both repositories and enforced by the lock and the compare-and-swap.

## Do I need to do anything?

Update to pick up F2 and F13 (already on `main`) and F11 (this PR). If `bind` reports `workspace state changed during bind`, run it again.
