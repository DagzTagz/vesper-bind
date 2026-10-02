# Security

vesper-bind is a local program. It is not an xAI, SpaceXAI, or Grok product. It does not call Grok and does not train a model.

## Local only

The program reads files you name and writes a receipt on the same machine. It does not open a socket, send telemetry, or call an API. It does not shell out to grok, curl, pip, or git. It does not spend credits. It does not train, fine-tune, or distill a model.

## Modes

The output directory is mode `0700`. The receipt file is mode `0600`. Both are set with `fchmod` on an open descriptor so the process umask cannot widen them. The receipt is written to a temp file in that directory, fsynced, then published under the final name. If a step fails, the temp name and any final name this command created are removed.

`verify` exits 1 when the receipt is not a regular file at mode `0600`, including when the path is a symlink.

## Keys

The program never opens a path with a component named `identity`, a final name `hmac.key`, or a name ending in `.priv`. The optional workspace update opens `<workspace>/state.json` only. A missing workspace, a symlink workspace, or a workspace without a usable `state.json` exits 1 and writes no receipt.

## Symlinks

A symlink that resolves outside the directory that contains it is refused. Files inside a scaffold run must stay inside that run. The hypothesis file must stay inside its parent directory. The output directory itself must not be a symlink.

## What a receipt does not contain

A receipt does not contain prompts, topics, hypothesis text, reasoning, model output, account ids, API keys, or private keys. The fields are listed in [docs/receipt-v1.md](docs/receipt-v1.md): schema, time, tool version, paths, one size, one mtime, sha256 digests, pass flags, and an optional note id.

The note text, when a workspace is passed, is `vesper-bind wrote a receipt.` It does not copy the hypothesis or the receipt path.

Paths are stored. A path can include a home-directory name. That is the path field, not the file body. Each hashed file is capped at 8 MiB.

Error lines name the check that failed. They do not echo file contents.

## What a maintainer can say

Processing stays on the machine that runs the command. This program does not transmit the operator's files. It does not retain prompt or account content because it never writes that content. It does not update a model. The stored record is the field list in [docs/receipt-v1.md](docs/receipt-v1.md), at mode `0600`, in a directory at mode `0700`.

That is the compliance posture: data minimization and local processing. It is an engineering description. It is not a certification and it is not a HIPAA, SOC 2, or attorney sign-off.

## Out of scope

This program is not a defense against someone who can already read the operator's files, against root, or against a disk image taken while the process is running. Unlink does not wipe free space.
