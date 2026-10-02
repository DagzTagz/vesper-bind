# vesper-bind

Unofficial DagzTagz command-line program. Not an xAI, SpaceXAI, or Grok product.

**Status:** v0.1.0. Apache-2.0. Python 3.11 or newer.

vesper-bind does not call Grok and does not train a model.

## What this is

You already have two pieces of work on your own computer. One is a hypothesis file: JSON that [dagztagz-hypothesis-engine](https://github.com/DagzTagz/dagztagz-hypothesis-engine) has already written. The other is a Dagz-Scaffold run directory: a folder from [Dagz-Scaffold](https://github.com/DagzTagz/Dagz-Scaffold) that holds the plan, the evidence, the critic, and the score. vesper-bind reads those files. When both pass the checks on this page, it writes one receipt.

A receipt is a JSON file. It records where the files were, the size of the hypothesis file, the time that file was last modified, and a sha256 digest of each file. A sha256 digest is 64 lowercase hexadecimal characters. It is a fingerprint of the exact bytes. `vesper-bind verify` reads the files again later and compares those fingerprints, so a changed file shows up.

The receipt does not contain the hypothesis text, the plan, the evidence, the critic, a prompt, a topic, model reasoning, an account id, or a key. The program does not send the files anywhere.

This repository does not include a copy of dagztagz-hypothesis-engine, Dagz-Scaffold, or vesper-runtime, and the program does not import them. You pass paths to files you already have.

## The hypothesis file

`--hypothesis` is one JSON file. The top level must be a JSON object. The program refuses the file when it is missing, unreadable, larger than 8 MiB (8 × 1024 × 1024 bytes), not UTF-8 JSON, has a duplicate key, or contains a non-finite number.

A live file from the hypothesis engine leaves out `meta.dry_run`. That missing field is accepted. The program walks every object in the JSON and refuses the file when it finds any of these:

- A field named `dry_run` whose value is anything other than JSON `false`. JSON `true`, `null`, `0`, and `"false"` are all refusals.
- A field named `backend` or `retrieval_backend` whose value is the string `mock`.
- A field named `domain` whose value is the string `mock`.
- A field named `retrieval_status` whose value is `ok_mock`, or any string that ends with `_mock`.
- A field whose value is a string that starts with `mock://`.

A sentence in the file that merely mentions a mock is not one of those marks. The refusal is printed on standard error as `hypothesis file is marked dry-run` or `hypothesis file is marked mock`. The file body is not printed.

The hypothesis path may be a symbolic link only when the target stays inside the same parent directory. A link that resolves outside that directory is refused. A path with a component named `identity`, a final name `hmac.key`, or a name ending in `.priv` is refused before the file is opened.

## The scaffold run directory

`--scaffold-run` is a real directory. The directory itself must not be a symbolic link. It must contain these four files, and each file must stay inside that directory:

| File | What the program uses it for |
|------|------------------------------|
| `plan.md` | The bytes are hashed. The text is not stored. |
| `evidence.md` | The bytes are hashed. The first non-empty line is also checked for a dry-run mark. |
| `critic.md` | The bytes are hashed. The section under the heading `## VERDICT` is read. |
| `score.json` | The bytes are hashed. The object is checked for a dry-run mark and, when it has a `verdict` field, that field is compared with the critic. |

The section under `## VERDICT` must contain a line that is `REJECT`, `ACCEPT WITH WAIVERS`, or `ACCEPT`. Blank lines and wrapping `*` or backticks are ignored when that line is read. `REJECT` stops the command. `ACCEPT` and `ACCEPT WITH WAIVERS` are allowed. If `score.json` has a `verdict` field, it must be that same line. A disagreement exits 1. The standard-error line is `scaffold critic verdict is REJECT` when either side is `REJECT`, and `scaffold critic verdict disagrees` otherwise.

The run is also refused, with `scaffold run is dry-run`, when any of these is true:

- `score.json` has a `dry_run` field whose value is anything other than JSON `false`. A score file with no `dry_run` field is not refused for that reason.
- The `notes` string in `score.json` starts with `Synthetic dry-run`.
- The first non-empty line of `evidence.md` starts with `DRY-RUN MOCK`.

A missing `score.json` exits 1 with `scaffold score.json is missing`. Each file is refused when it is larger than 8 MiB (8 × 1024 × 1024 bytes). A file of exactly that size is accepted.

## The receipt

`bind` writes one file. The name is the UTC time of the write, packed into `YYYYMMDDTHHMMSSZ`, then `-receipt.json`. A write at `2026-10-02T13:13:42Z` produces `20261002T131342Z-receipt.json`. That same time is the `created_utc` field inside the file.

The file is UTF-8 JSON, indented two spaces, with a trailing newline. Another program can load it with `json.loads` and does not need this command installed. `show` and `verify` use the checker in `vesper_bind.receipt`, which requires the schema id `vesper-bind/receipt/v1`, the field names below, and no extra fields.

The file mode is `0600`. That means the owner can read and write the file, and the group and everyone else have no permission. The output directory mode is `0700`. That means the owner can open the directory and add or remove files in it, and the group and everyone else have no permission. Both modes are set on the open directory and the open file, so the process umask cannot widen them. If you name a directory that already exists, the program sets that directory to mode `0700` before it publishes the receipt.

The bytes are written to a temporary file in the output directory, flushed to disk, and then published under the final name. An existing file of that name is left unchanged, and the command exits 1 with `receipt already exists`. If a later step fails, the new receipt is removed. If this command created the output directory and that directory is then empty, the directory is removed too.

In the file, `hypothesis`, `scaffold`, and `pass_flags` are objects. `show` prints each inner field with a dot. `hypothesis.path` on screen is the JSON field `path` inside `hypothesis`.

| Field | What it holds |
|-------|----------------|
| `schema` | The string `vesper-bind/receipt/v1`. |
| `created_utc` | The UTC time of the write, `YYYY-MM-DDTHH:MM:SSZ`. |
| `tool_version` | The program version. This release is `0.1.0`. |
| `hypothesis.path` | Absolute path of the hypothesis file that was hashed. |
| `hypothesis.size` | Size of that file, in bytes. |
| `hypothesis.mtime_utc` | Last modification time of that file, UTC, to the whole second. The fractional part is dropped. |
| `hypothesis.sha256` | sha256 digest of that file, 64 lowercase hexadecimal characters. |
| `scaffold.path` | Absolute path of the run directory. |
| `scaffold.plan_md_sha256` | sha256 digest of `plan.md`. |
| `scaffold.evidence_md_sha256` | sha256 digest of `evidence.md`. |
| `scaffold.critic_md_sha256` | sha256 digest of `critic.md`. |
| `scaffold.score_json_sha256` | sha256 digest of `score.json`. |
| `pass_flags` | Six checks. On a file this program wrote, each one is JSON `true`. |
| `vesper_note_id` | The note id, or JSON `null` when you did not pass a workspace. |

| Pass flag | The check that passed |
|-----------|------------------------|
| `hypothesis_present` | The hypothesis file was read. |
| `hypothesis_not_dry_run` | No `dry_run` mark was found. A missing `dry_run` field is not a mark. |
| `hypothesis_not_mock` | No mock mark was found. |
| `scaffold_score_present` | `score.json` was read. |
| `scaffold_not_dry_run` | The run was not marked as a dry run. |
| `critic_not_reject` | The critic verdict was not `REJECT`. |

`show` and `verify` reject a receipt that adds a field, drops a field, or sets a pass flag to anything other than JSON `true`. The full types are in [docs/receipt-v1.md](docs/receipt-v1.md).

A path in the receipt can include a home-directory name. That is the path field. It is not a copy of the file.

## Commands

Every refusal exits 1. The message goes to standard error and starts with `vesper-bind: `. Success exits 0. There is no other exit code.

### Preview with `--dry-run`

```bash
vesper-bind --dry-run \
  --hypothesis examples/passing/hypothesis.json \
  --scaffold-run examples/passing/scaffold
```

This reads both inputs, runs the same checks as `bind`, and prints one receipt on standard output. It creates no file and no directory. `vesper_note_id` is JSON `null`, because this form does not take `--vesper-workspace`. Exit 0 means both inputs passed. Exit 1 means a check failed and nothing was written. Combining `--dry-run` with `bind`, `show`, `verify`, or `--vesper-workspace` exits 1.

### Write one receipt with `bind`

```bash
vesper-bind bind \
  --hypothesis examples/passing/hypothesis.json \
  --scaffold-run examples/passing/scaffold \
  --out receipts
```

`--hypothesis`, `--scaffold-run`, and `--out` are required. Exit 0 prints one line on standard output: the absolute path of the new receipt. Exit 1 writes no receipt. `receipts/` is listed in `.gitignore`, so a receipt you create there is not part of a later commit.

The fixtures in `examples/passing/` are synthetic and contain no secrets. `examples/fail-dry-run/` is a run that `bind` must refuse. The numbered steps, with the expected exit code after each one, are in [getting-started.md](getting-started.md).

### Read a receipt with `show`

```bash
vesper-bind show receipts/<UTC>-receipt.json
```

Exit 0 prints 19 lines. Each line is `name: value`, in the order in [docs/receipt-v1.md](docs/receipt-v1.md). The first line is `schema: vesper-bind/receipt/v1`. Boolean flags are the words `true` and `false`. A missing note id is the word `null`. This layout is the one a later local reader should print. This repository does not include that reader. `show` prints a regular file even when its mode is not `0600`. It refuses a symbolic link.

### Check a receipt with `verify`

```bash
vesper-bind verify receipts/<UTC>-receipt.json
```

Exit 0 prints `verify ok`. The command requires the receipt to be a regular file at mode `0600`. It opens the file without following a symbolic link. It then recomputes sha256 for the hypothesis path and for `plan.md`, `evidence.md`, `critic.md`, and `score.json` inside the scaffold path. A path that is no longer on disk is skipped. A path that is still on disk and whose digest differs exits 1 with `digest mismatch:` and the file name. A receipt whose mode is not `0600` exits 1 with `receipt is not mode 0600`.

### See the version

```bash
vesper-bind --help
vesper-bind --version
```

`--help` exits 0 and lists the commands. `--version` exits 0 and prints `vesper-bind 0.1.0`.

## Optional workspace note

`bind` accepts `--vesper-workspace` with the path of a folder that [vesper-runtime](https://github.com/DagzTagz/vesper-runtime) has already created. The program opens `<workspace>/state.json` only. It appends one note whose text is exactly `vesper-bind wrote a receipt.` The receipt's `vesper_note_id` is the id of that note. The note does not contain the hypothesis text or the receipt path.

If the directory is missing, is a symbolic link, or has no usable `state.json`, the command exits 1 and writes no receipt. The program does not create a workspace. It does not open `identity/`, a file ending in `.priv`, or `hmac.key`.

## What it does not do

- It does not call Grok, xAI, SpaceXAI, or any other API.
- It does not train, fine-tune, or distill a model.
- It does not spend credits.
- It does not store prompts, topics, reasoning, account ids, or keys.
- It does not become a model.
- It does not include or import dagztagz-hypothesis-engine, Dagz-Scaffold, or vesper-runtime.
- It does not open `identity/`, a `*.priv` file, or `hmac.key`.
- It does not shell out to grok, curl, pip, or git.
- It does not provide a graphical interface.

## Install

From Ubuntu, with Python 3.11 or newer:

```bash
git clone https://github.com/DagzTagz/vesper-bind.git
cd vesper-bind
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
vesper-bind --help
```

The program's own dependencies are the Python standard library. The `[dev]` extra installs pytest so you can run the tests. The tests use `examples/` and do not use the network.

What good looks like: pytest prints a line that ends in `passed` and exits 0. `vesper-bind --help` prints the command list and exits 0.

What failure means: if `vesper-bind` is not found, the virtual environment is not active. Run `source .venv/bin/activate` again. `which python` should point inside `.venv`. If pytest prints `failed`, stop and read the failing test name before you bind a real file.

## Docs

| You want to… | Read |
|--------------|------|
| Do the steps once, with the exit code after each step | [getting-started.md](getting-started.md) |
| See every receipt field, its type, and who writes it | [docs/receipt-v1.md](docs/receipt-v1.md) |
| See the local-only rules and what a receipt leaves out | [SECURITY.md](SECURITY.md) |
| See what changed | [CHANGELOG.md](CHANGELOG.md) |

## Related projects

vesper-bind reads files you pass in. It does not import these repositories.

- Hypothesis JSON is produced by [dagztagz-hypothesis-engine](https://github.com/DagzTagz/dagztagz-hypothesis-engine).
- Run directories are produced by [Dagz-Scaffold](https://github.com/DagzTagz/Dagz-Scaffold).
- An optional note is appended to a workspace from [vesper-runtime](https://github.com/DagzTagz/vesper-runtime).

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
