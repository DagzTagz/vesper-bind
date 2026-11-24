# Changelog

## Unreleased

### Security

- `--vesper-workspace` no longer overwrites a change that another writer made to `state.json` between reading it and writing the note (audit F11). The note is committed under an exclusive `flock` on `<workspace>/.lock`, the lock vesper-runtime uses. If the file changed, `bind` exits 1 with `workspace state changed during bind` and removes its receipt. The full disclosure for this repository is in [docs/security/state-machine-audit-2026-11.md](docs/security/state-machine-audit-2026-11.md).

- `bind` and `--dry-run` now refuse a Dagz-Scaffold run unless Dagz-Scaffold's scorer passed it. Before, `bind` checked only the dry-run marks and the critic verdict, so it wrote receipts for runs the scorer fails (for example `quit_early` or `missing_evidence`), including 9 of Dagz-Scaffold's 11 failing example runs. See [docs/security/ADVISORY-2026-11-24-bind-accepts-failed-scaffold-runs.md](docs/security/ADVISORY-2026-11-24-bind-accepts-failed-scaffold-runs.md).
- **Breaking:** a scaffold run folder must now contain `score-result.json`, the output of `python3 harness/score.py RUN_DIR`, with `ok: true` and no `fail_reasons`, for the same `score.json`. `score.json` must also say `quit_early: false` and `missing_evidence: false`.
- `pass_flags` are now computed from the checks they name instead of being literal `true` values. The receipt format is unchanged (`vesper-bind/receipt/v1`).

## 0.1.0 — 2026-10-02

- Initial local receipt binder.
- Reads a hypothesis JSON file and a Dagz-Scaffold run directory.
- Writes one `vesper-bind/receipt/v1` file, mode 0600, or prints it with `--dry-run`.
- Optional note appends to an existing vesper-runtime workspace without opening key files.
- Does not call a network API and does not train a model.
- README explains the two inputs, each command, the receipt fields, and the file modes in complete sentences.
