# Getting started

vesper-bind does not call Grok and does not train a model.

The steps below use the fixtures in this repository. They contain no secrets. Run them from the project directory after install. `receipts/` is gitignored.

## Create a receipt

1. Dry-run. This prints a receipt and writes nothing.

   ```bash
   vesper-bind --dry-run \
     --hypothesis examples/passing/hypothesis.json \
     --scaffold-run examples/passing/scaffold
   ```

   Expected exit code: 0.

2. Write one receipt from the same hypothesis file and scaffold run.

   ```bash
   vesper-bind bind \
     --hypothesis examples/passing/hypothesis.json \
     --scaffold-run examples/passing/scaffold \
     --out receipts
   ```

   Expected exit code: 0. Stdout is one line: the absolute path of `receipts/<UTC>-receipt.json`. The file mode is `0600`. The directory mode is `0700`.

   A hypothesis marked dry-run or mock, or a scaffold whose `score.json` is missing, whose `dry_run` is true, or whose critic verdict is `REJECT`, exits 1 and writes no receipt.

## Read and check a receipt

1. Show the receipt. Use the path printed in the previous step.

   ```bash
   vesper-bind show receipts/<UTC>-receipt.json
   ```

   Expected exit code: 0. The first line is `schema: vesper-bind/receipt/v1`. The rest of the lines are the layout in [docs/receipt-v1.md](docs/receipt-v1.md).

2. Check the receipt.

   ```bash
   vesper-bind verify receipts/<UTC>-receipt.json
   ```

   Expected exit code: 0. Stdout is `verify ok`. The command recomputes sha256 for hypothesis and scaffold paths that still exist and compares them to the receipt. It exits 1 if a digest differs or the receipt mode is not `0600`.

## Optional workspace note

Pass `--vesper-workspace` only when that directory already exists. The command appends one note, `vesper-bind wrote a receipt.`, to `state.json`. It does not open `identity/`, a `*.priv` file, or `hmac.key`. If the directory is missing, the exit code is 1 and no receipt is written.
