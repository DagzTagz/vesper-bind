# Changelog

## 0.1.0 — 2026-10-02

- Initial local receipt binder.
- Reads a hypothesis JSON file and a Dagz-Scaffold run directory.
- Writes one `vesper-bind/receipt/v1` file, mode 0600, or prints it with `--dry-run`.
- Optional note appends to an existing vesper-runtime workspace without opening key files.
- Does not call a network API and does not train a model.
