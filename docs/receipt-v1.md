# Receipt v1

Schema id: `vesper-bind/receipt/v1`.

A receipt is UTF-8 JSON with indent 2 and a trailing newline. A later program can load it with `json.loads` and does not need this CLI. `vesper_bind.receipt` is the checker this CLI uses. Field order is fixed. Duplicate keys are rejected. NaN and Infinity are rejected.

The file name is `<YYYYMMDDTHHMMSSZ>-receipt.json`. That stamp is the same second as `created_utc`. The file mode is `0600`. The directory that holds it is mode `0700`.

vesper-bind writes every field. The operator chooses the input paths. The program records the absolute paths it read and the digests it computed. A reader writes nothing.

## Top-level fields

| Field | Type | Who writes it |
|-------|------|----------------|
| `schema` | string, always `vesper-bind/receipt/v1` | vesper-bind |
| `created_utc` | string, `YYYY-MM-DDTHH:MM:SSZ` | vesper-bind, from the UTC clock |
| `tool_version` | string, package version, at most 64 characters | vesper-bind |
| `hypothesis` | object | vesper-bind |
| `scaffold` | object | vesper-bind |
| `pass_flags` | object of JSON booleans | vesper-bind |
| `vesper_note_id` | string or JSON `null` | vesper-bind. `null` when `--vesper-workspace` is omitted |

## hypothesis

| Field | Type | Who writes it |
|-------|------|----------------|
| `path` | absolute path string, no newline, at most 4096 characters | vesper-bind, the real file it hashed |
| `size` | integer byte count, not a boolean | vesper-bind |
| `mtime_utc` | string, `YYYY-MM-DDTHH:MM:SSZ`, whole seconds | vesper-bind, from `st_mtime` |
| `sha256` | 64 lowercase hex characters | vesper-bind |

The hypothesis object does not contain the hypothesis text, topic, or rationale.

A live hypothesis-engine file omits `meta.dry_run`. That omission is accepted. A `dry_run` value of JSON `true`, or any present value other than JSON `false`, is a dry-run mark and is refused. Mock markers are structural: `backend` or `retrieval_backend` equal to `mock`, `domain` equal to `mock`, `retrieval_status` of `ok_mock` or ending in `_mock`, or a string that starts with `mock://`. Prose that mentions a mock is not a marker.

## scaffold

| Field | Type | Who writes it |
|-------|------|----------------|
| `path` | absolute path of the run directory | vesper-bind |
| `plan_md_sha256` | 64 lowercase hex characters | vesper-bind, hash of `plan.md` |
| `evidence_md_sha256` | 64 lowercase hex characters | vesper-bind, hash of `evidence.md` |
| `critic_md_sha256` | 64 lowercase hex characters | vesper-bind, hash of `critic.md` |
| `score_json_sha256` | 64 lowercase hex characters | vesper-bind, hash of `score.json` |

The scaffold object does not contain the markdown text or the score document.

The run is refused when `score.json` is missing, when `dry_run` is not JSON `false` if that key is present, when `notes` starts with `Synthetic dry-run`, when the first non-empty evidence line starts with `DRY-RUN MOCK`, or when the critic verdict is `REJECT`. `## VERDICT` in `critic.md` must be `REJECT`, `ACCEPT WITH WAIVERS`, or `ACCEPT`. If `score.json` also has `verdict`, it must match.

## pass_flags

Each value on a file this program writes is JSON `true`. A reader rejects a flag that is not `true`.

| Field | Type | Meaning | Who writes it |
|-------|------|---------|----------------|
| `hypothesis_present` | boolean | The hypothesis file was read. | vesper-bind |
| `hypothesis_not_dry_run` | boolean | No `dry_run` mark was found. A missing key is not a mark. | vesper-bind |
| `hypothesis_not_mock` | boolean | No mock marker was found. | vesper-bind |
| `scaffold_score_present` | boolean | `score.json` was read. | vesper-bind |
| `scaffold_not_dry_run` | boolean | The run is not marked dry-run. | vesper-bind |
| `critic_not_reject` | boolean | The critic verdict is not `REJECT`. | vesper-bind |

## vesper_note_id

| Value | Who writes it |
|-------|----------------|
| JSON `null` | vesper-bind, when no workspace was passed |
| string matching `[A-Za-z0-9._-]{1,128}` | vesper-bind, the id of the one note it appended |

The note text is `vesper-bind wrote a receipt.` The id is `m-` plus the first 16 hex characters of SHA-256 over `stm|<unix>|<text>|<stm count before append>`, UTF-8. The item is an STM note: `id`, `ts`, `text`, `valence` 0.5, `weight` 1.0, `tier` `stm`, `pinned` false. If the STM list would exceed 100, the oldest `(ts, id)` is dropped so the new note remains. The note does not contain the receipt path or the hypothesis text.

## Show layout

`vesper-bind show` prints these lines, in this order, then a trailing newline. A later binder-reader UI mirrors this layout. Booleans are `true` or `false`. A missing note id is the four characters `null`.

```text
schema: vesper-bind/receipt/v1
created_utc: YYYY-MM-DDTHH:MM:SSZ
tool_version: 0.1.0
hypothesis.path: /absolute/path
hypothesis.size: 0
hypothesis.mtime_utc: YYYY-MM-DDTHH:MM:SSZ
hypothesis.sha256: <64 lowercase hex>
scaffold.path: /absolute/directory
scaffold.plan_md.sha256: <64 lowercase hex>
scaffold.evidence_md.sha256: <64 lowercase hex>
scaffold.critic_md.sha256: <64 lowercase hex>
scaffold.score_json.sha256: <64 lowercase hex>
pass_flags.hypothesis_present: true
pass_flags.hypothesis_not_dry_run: true
pass_flags.hypothesis_not_mock: true
pass_flags.scaffold_score_present: true
pass_flags.scaffold_not_dry_run: true
pass_flags.critic_not_reject: true
vesper_note_id: null
```

## Verify

`vesper-bind verify` requires the receipt file itself to be a regular file at mode `0600`. It recomputes sha256 for `hypothesis.path` and for `plan.md`, `evidence.md`, `critic.md`, and `score.json` under `scaffold.path` when that path still exists. A missing path is skipped. A path that exists and whose digest differs exits 1. A symlink that resolves outside its parent directory exits 1.

## Limits

Each input file is refused above 8 MiB. Paths in the receipt are absolute and can contain a home-directory name. They do not contain the file body.
