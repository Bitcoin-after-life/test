#!/usr/bin/env python3
"""Build a clean, zipimport-friendly distribution archive of the BAL plugin.

Electrum loads external plugins from a ``.zip`` using Python's ``zipimport``.
``zipimport`` is picky about the archive layout, so this builder deliberately:

  * writes **only files** (no explicit directory entries) — some Electrum
    portable builds choke on directory records inside the archive;
  * uses standard DEFLATE compression (well supported by ``zipimport``);
  * emits entries in a deterministic, sorted order so the archive is
    reproducible (stable SHA-256);
  * skips ``__pycache__`` directories and compiled ``*.pyc``/``*.pyo`` files.

The archive keeps the top-level ``bal/`` directory so that the package is
importable as ``bal`` (and Electrum derives ``dirname='bal'`` from the path of
``bal/manifest.json``).

Usage::

    python3 build_zip.py [output.zip]

Prints the resulting size and SHA-256 so the download can be integrity-checked.
"""

import hashlib
import os
import sys
import zipfile

SRC_ROOT = "bal"
DEFAULT_OUT = "bal-electrum-plugin.zip"


def build(out_path: str) -> None:
    if os.path.exists(out_path):
        os.remove(out_path)

    files = []
    for dirpath, dirnames, filenames in os.walk(SRC_ROOT):
        # prune cache dirs in place so os.walk does not descend into them
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith((".pyc", ".pyo")):
                continue
            files.append(os.path.join(dirpath, fn))
    files.sort()

    with zipfile.ZipFile(
        out_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as z:
        for f in files:
            arc = f.replace(os.sep, "/")  # forward slashes inside the archive
            z.write(f, arc)

    # Integrity + summary
    with zipfile.ZipFile(out_path) as z:
        bad = z.testzip()
        if bad is not None:
            raise SystemExit(f"ERROR: corrupt entry in archive: {bad}")
        names = z.namelist()
        if not any(n.endswith("manifest.json") for n in names):
            raise SystemExit("ERROR: manifest.json missing from archive")

    data = open(out_path, "rb").read()
    print(f"built : {out_path}")
    print(f"files : {len(files)}")
    print(f"size  : {len(data)} bytes")
    print(f"sha256: {hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    build(out)
