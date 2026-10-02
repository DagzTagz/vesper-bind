# vesper-bind

Unofficial DagzTagz CLI. Not an xAI, SpaceXAI, or Grok product.

**Status:** v0.1.0

vesper-bind does not call Grok and does not train a model.

## What it does

You point it at two things that are already on disk: a hypothesis JSON file and a Dagz-Scaffold run directory. If both pass the local checks, it writes one receipt. The receipt holds paths, sizes, mtimes, sha256 digests, and pass flags.

`vesper-bind show` prints that receipt as plain text. A later local reader can use the same lines. This repository does not include that UI.

With `--vesper-workspace`, it also appends one note to an existing vesper-runtime workspace saying that a receipt was written.

## What it does not do

- It does not call Grok, xAI, SpaceXAI, or any other API.
- It does not train, fine-tune, or distill a model.
- It does not spend credits.
- It does not store prompts, topics, reasoning, account ids, or keys.
- It does not become a model.
- It does not vendor dagztagz-hypothesis-engine, Dagz-Scaffold, or vesper-runtime.
- It does not open `identity/`, a `*.priv` file, or `hmac.key`.
- It does not provide a graphical UI.

## Install

Python 3.11 or newer. The program's runtime dependencies are the standard library. pytest is a dev extra used to run the tests.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
vesper-bind --help
```

`python -m pytest -q` exits 0 when the tests pass. `vesper-bind --help` exits 0 and lists the commands.

## Commands

| Command | Effect | Exit |
|---------|--------|------|
| `vesper-bind --dry-run --hypothesis FILE --scaffold-run DIR` | Print a receipt. Write nothing. | 0 when both inputs pass. 1 when they do not. |
| `vesper-bind bind --hypothesis FILE --scaffold-run DIR --out DIR` | Write one receipt. | 0 or 1 |
| `vesper-bind verify RECEIPT` | Recompute sha256 for paths that still exist. Require mode 0600. | 0 or 1 |
| `vesper-bind show RECEIPT` | Print the stable text layout. | 0 or 1 |

`bind` accepts `--vesper-workspace DIR`. If that directory is missing, the command exits 1 and writes nothing.

The receipt file is `<UTC>-receipt.json` in the output directory. The file mode is `0600`. The directory mode is `0700`.

## Docs

- [getting-started.md](getting-started.md) — dry-run, bind, show, and verify
- [docs/receipt-v1.md](docs/receipt-v1.md) — every receipt field
- [SECURITY.md](SECURITY.md) — local-only rules and what a receipt omits
- [CHANGELOG.md](CHANGELOG.md) — versions

## Related projects

vesper-bind does not import these. It reads files you pass in.

- Hypothesis JSON is produced by [dagztagz-hypothesis-engine](https://github.com/DagzTagz/dagztagz-hypothesis-engine).
- Run directories are produced by [Dagz-Scaffold](https://github.com/DagzTagz/Dagz-Scaffold).
- An optional note is appended to a workspace from [vesper-runtime](https://github.com/DagzTagz/vesper-runtime).
