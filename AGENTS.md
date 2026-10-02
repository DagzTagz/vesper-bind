# AGENTS.md

Unofficial DagzTagz project. vesper-bind does not call Grok and does not train a model.

## Hard rules

- Python 3.11+. The standard library only. No runtime dependencies.
- Do not import socket, http, urllib, a model SDK, subprocess, or a GUI toolkit.
- Do not shell out to grok, curl, pip, or git.
- Do not vendor dagztagz-hypothesis-engine, Dagz-Scaffold, or vesper-runtime.
- Receipts store paths, sizes, mtimes, sha256 digests, and pass flags. Do not store prompts, topics, reasoning, account ids, or keys.
- Never open `identity/`, a file ending in `.priv`, or `hmac.key`.
- Receipt files are mode 0600. The output directory is mode 0700. Write via a temp file in that directory, fsync, then publish the name. On failure, leave no partial file.
- Reject a symlink that resolves outside the directory the operator named.
- `vesper_bind.receipt` loads, validates, and renders a receipt. The CLI calls it. Do not add a UI.
- Exit 0 on success. Exit 1 on every refusal. Do not add a network call to make a check pass.

## Done

pytest is green, including dry-run writes nothing, REJECT and dry_run scaffolds exit 1, a symlink escape exits 1, a good bind is mode 0600, verify fails after one flipped byte, and show prints `vesper-bind/receipt/v1`.
