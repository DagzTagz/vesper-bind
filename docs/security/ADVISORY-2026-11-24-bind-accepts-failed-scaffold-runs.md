# Security advisory: `vesper-bind bind` accepts Scaffold runs that Scaffold's scorer fails

| | |
|---|---|
| **Component** | `src/vesper_bind/inputs.py` (`load_inputs`), used by `vesper-bind bind` |
| **Audit priority** | High (see [audit rubric](https://github.com/DagzTagz/Dagz-Scaffold/blob/main/docs/audits/2026-11-state-machine-audit.md#2-methodology)). No CVE or CVSS score has been assigned. |
| **Audited commit** | [`aa1e93c86bf46780106c6410effe9113b454769c`](https://github.com/DagzTagz/vesper-bind/tree/aa1e93c86bf46780106c6410effe9113b454769c) (Dagz-Scaffold compared at [`76edab4`](https://github.com/DagzTagz/Dagz-Scaffold/tree/76edab4b4c93e199034ca1e8fa545c27b79a0a2d)) |
| **Status** | Fixed and merged on `main` in [vesper-bind#1](https://github.com/DagzTagz/vesper-bind/pull/1), merge [`c9b4e82`](https://github.com/DagzTagz/vesper-bind/commit/c9b4e82dcdf2ce8d323f4404017180eca487f771) (2026-11-24) |
| **Published** | 2026-11-24 |
| **Type** | Integrity / gate bypass. No code execution, no network access, no data exposure. |

## Summary

`vesper-bind bind` is described as writing "one receipt when both inputs pass" ([cli.py L74](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/src/vesper_bind/cli.py#L74)). For the Dagz-Scaffold run, it checks only two things: that the run is not marked dry-run, and that the critic verdict is not `REJECT`. It does **not** check the other conditions that make Scaffold's own scorer fail a run, such as `quit_early` and `missing_evidence`. So `bind` writes a receipt, with all six `pass_flags` set to `true`, for runs that `harness/score.py` reports as `ok: false`.

vesper-bind behaves the way its README's check list describes ([README L84-L92](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/README.md#L84-L92)). The problem is that "passed" in vesper-bind is much weaker than "passed" in Dagz-Scaffold, and a receipt does not show the difference.

## Affected component

- The only Scaffold gates in `load_inputs` are dry-run markers ([inputs.py L48-L49](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/src/vesper_bind/inputs.py#L48-L49), [`_scaffold_dry` L146-L160](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/src/vesper_bind/inputs.py#L146-L160)) and the critic verdict ([L50-L60](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/src/vesper_bind/inputs.py#L50-L60)). Whole function: [L32-L80](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/src/vesper_bind/inputs.py#L32-L80).
- `pass_flags` are literal `True` values, so the `not all(flags.values())` guard can never fire ([L62-L71](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/src/vesper_bind/inputs.py#L62-L71)). The receipt loader accepts only `true` flags ([receipt.py L180-L185](https://github.com/DagzTagz/vesper-bind/blob/aa1e93c86bf46780106c6410effe9113b454769c/src/vesper_bind/receipt.py#L180-L185)). This is audit finding F13.
- Searching `src/` for `quit_early`, `missing_evidence`, `fail_reasons` or `override` finds nothing.
- For comparison, Scaffold's pass condition is `ok = not fail_reasons`. The fail reasons include `quit_early`, `REJECT` without an honored override, `missing_evidence`, `evidence_has_no_commands`, `dry_run`, `task_contract_missing`, `required_verification`, `solution_not_called`, and replay mismatch: [Dagz-Scaffold score.py L491-L553](https://github.com/DagzTagz/Dagz-Scaffold/blob/76edab4b4c93e199034ca1e8fa545c27b79a0a2d/harness/score.py#L491-L553).

## Impact

**Confirmed:**
- We copied `examples/passing`, set `quit_early: true` and `missing_evidence: true` in `scaffold/score.json`, and ran `bind`. It exited 0 and wrote a receipt with all six `pass_flags` set to `true`.
- We applied the same edit to Dagz-Scaffold's `examples/sample-run`. `score.py` reported `ok: false` with `fail_reasons: ["quit_early", "missing_evidence"]`, and `vesper-bind bind` still exited 0 and wrote a receipt.
- We ran `bind` on Dagz-Scaffold's own **unmodified** failing example runs, paired with vesper-bind's passing hypothesis fixture. It wrote a receipt for 9 of the 11 runs that Scaffold fails: `fail-fake-commands`, `fail-green-only-005`, `fail-missing-evidence`, `fail-quit-early`, `fail-quit-early-green-only`, `fail-quit-early-prose-assert`, `fail-scope-cut`, `fake-green-run`, and `quit-early-run`. It correctly refused the two `REJECT` runs (`fail-reject`, `reject-run`).

**What this means:**
- A receipt does **not** prove that Scaffold's scorer passed the run. It proves only that the run was not marked dry-run and that the critic verdict was not `REJECT`.
- The `critic_not_reject` flag is accurate, but a reader can mistake the flags for a full pass.

**Not affected:**
- Receipt integrity. `verify` still detects changes to the hashed files.
- Hypothesis-side checks.
- Local-only operation. vesper-bind makes no network calls and runs no subprocesses.

## Who is affected

Anyone who uses a vesper-bind receipt, or the note it can add to a vesper workspace, as evidence that a Dagz-Scaffold run **passed**. Examples are a review step, a CI check, or a later tool that trusts receipts. Producing receipts for your own records is not affected, as long as you don't read them as "Scaffold passed".

## Conditions to trigger

Run `vesper-bind bind --scaffold-run <dir>` on a run folder where:
- the critic verdict (`## VERDICT` in `critic.md`, and `score.json` `verdict` if present) is `ACCEPT` or `ACCEPT WITH WAIVERS`,
- the run is not marked dry-run, and
- Scaffold would still fail it for any other reason, for example `quit_early: true`, `missing_evidence: true`, no commands in the evidence, a missing required verification, or a replay mismatch.

This needs no attacker. Ordinary failed runs trigger it, as the unmodified Scaffold examples show.

## Workarounds until fixed

- **Score before you bind.** Run Dagz-Scaffold's scorer on the same folder, and call `bind` only if it exits 0:
  ```bash
  python3 /path/to/Dagz-Scaffold/harness/score.py RUN_DIR >/dev/null \
    && vesper-bind bind --hypothesis HYP.json --scaffold-run RUN_DIR --out receipts/
  ```
  `score.py` exits 0 only when `ok` is true. Leave off `--replay` unless you have read the evidence and your Scaffold checkout is a real `git clone`. See the Dagz-Scaffold advisory.
- **Without Scaffold available**, at least refuse runs whose `score.json` does not have both `"quit_early": false` and `"missing_evidence": false`:
  ```bash
  python3 -c 'import json,sys; s=json.load(open(sys.argv[1])); sys.exit(0 if s.get("quit_early") is False and s.get("missing_evidence") is False else 1)' RUN_DIR/score.json
  ```
  This catches only those two fields. It is much weaker than running the scorer: Scaffold also detects quitting early from the evidence text, so a run like Scaffold's `examples/quit-early-run`, whose `score.json` says `"quit_early": false`, passes this check but fails `score.py`.
- **For receipts you already have:** run `vesper-bind verify RECEIPT` to confirm the files are unchanged, then run Scaffold's `score.py` on the `scaffold.path` recorded in the receipt. Treat the receipt as a pass only if both succeed.

## Fix

**Status: fixed and merged on `main` in [vesper-bind#1](https://github.com/DagzTagz/vesper-bind/pull/1), merge [`c9b4e82`](https://github.com/DagzTagz/vesper-bind/commit/c9b4e82dcdf2ce8d323f4404017180eca487f771).**

- `load_inputs` now classifies the scaffold run into an explicit `ScaffoldRunState`: `dry_run`, `rejected`, `failed`, `unscored`, or `passed`, checked in that order. Only `passed` binds.
- `failed`: `score.json` has `quit_early` or `missing_evidence` set to anything other than JSON `false` (a missing field included), or carries `ok` / `fail_reasons` showing a failure; or the scorer result does.
- `unscored`: the run folder has no `score-result.json`. Dagz-Scaffold's failing examples all claim `quit_early: false` and `missing_evidence: false` in `score.json`; only the scorer (task contract, evidence scans, replay) finds their failures. vesper-bind must not run subprocesses or vendor Scaffold, so it now requires the scorer's own output, saved with `python3 harness/score.py RUN_DIR > RUN_DIR/score-result.json`.
- `passed`: `score-result.json` has `ok: true`, an empty `fail_reasons` list, a `score` object equal to `score.json`, and (when present) a `critic_verdict` equal to `critic.md`'s verdict.
- `pass_flags` are computed from the checks they name instead of literal `true` values (F13). The receipt format is still `vesper-bind/receipt/v1`.
- **Breaking:** binding a run now requires `score-result.json`. `examples/passing/scaffold/` gained a synthetic one.
- New tests in `tests/test_scaffold_state.py` cover the edited `score.json`, a missing scorer result, failing or malformed scorer results, a scorer result for a different `score.json`, and computed flags.

After the fix, the reproduction above refuses all 11 of Dagz-Scaffold's failing example runs, both as shipped and with their scorer output saved. The 9 that used to bind are refused with `scaffold run has no scorer result` as shipped and `scaffold scorer did not pass: <fail reasons>` with the output saved; the two `REJECT` runs are still refused as `REJECT`, and refuses the edited `sample-run` (`scaffold run is quit-early`). The unmodified `sample-run` with its scorer output saved, and `examples/passing`, still bind.

**Limit:** `score-result.json` is written next to the agent's own files, so it is a check that the scorer was run and passed, not a signature. The receipt hashes the four inputs, so anyone can score them again to confirm it. An explicit, versioned run state written by Dagz-Scaffold itself remains the longer-term design (audit F2).

## Credit and methodology

Found during a self-audit by the DagzTagz maintainers, assisted by an AI agent, of the five public DagzTagz repositories at their default-branch HEADs. The audit looked for implicit state machines (lifecycles encoded as flags, `None` sentinels, or status strings). This issue is finding **F2**, with **F13** as a contributing factor. It was reproduced by running the code at the audited commits.

Full report: [docs/audits/2026-11-state-machine-audit.md on Dagz-Scaffold](https://github.com/DagzTagz/Dagz-Scaffold/blob/main/docs/audits/2026-11-state-machine-audit.md)

Related lower-priority finding touching this repository: F11 (memory tier recorded twice). See the report.
