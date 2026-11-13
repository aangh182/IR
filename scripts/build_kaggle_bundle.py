"""Build the keyframe bundle zip for Kaggle (ZIP_STORED, incompressible JPEGs)."""

from __future__ import annotations

import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
KEYFRAMES = ARTIFACTS / "keyframes"
MANIFEST = ARTIFACTS / "manifest.jsonl"
OUT = ROOT / "artifacts_keyframes.zip"

README = """AIC2024 KIS - keyframe bundle for Kaggle
Contents:
  keyframes/<video_id>/g<generation>/<shot>_<keyframe>.jpg
  manifest.jsonl   (kf_uid, video_id, generation, shot_idx, kf_idx, ts_ms, path)
Upload this zip as a Kaggle Dataset, run scripts/kaggle_embed.ipynb, then download
the shard zip and import it locally with:
  uv run ir import-shards artifacts_embed_shards.zip
"""


def main() -> int:
    if not KEYFRAMES.is_dir() or not MANIFEST.is_file():
        print(f"missing bundle inputs: {KEYFRAMES} {MANIFEST}", file=sys.stderr)
        return 1

    paths = sorted(p for p in KEYFRAMES.rglob("*") if p.is_file())
    total = sum(p.stat().st_size for p in paths)
    print(f"files={len(paths)} raw={total / 1e9:.2f} GB", flush=True)

    temporary = OUT.with_suffix(OUT.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()

    written = 0
    done = 0
    started = time.time()
    last = 0.0
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_STORED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ARTIFACTS).as_posix())
            written += 1
            done += path.stat().st_size
            now = time.time()
            if now - last >= 15:
                last = now
                elapsed = now - started
                rate = done / elapsed / 1e6 if elapsed else 0
                print(
                    f"{done / 1e9:.2f}/{total / 1e9:.2f} GB "
                    f"{100 * done / total:5.1f}% files={written} {rate:.0f} MB/s "
                    f"elapsed={elapsed / 60:.1f}m",
                    flush=True,
                )
        archive.write(MANIFEST, "manifest.jsonl")
        archive.writestr("README.txt", README)

    os.replace(temporary, OUT)
    size = OUT.stat().st_size
    print(
        f"done: {OUT} files={written + 2} size={size / 1e9:.2f} GB "
        f"elapsed={(time.time() - started) / 60:.1f}m",
        flush=True,
    )
    print(json.dumps({"zip": str(OUT), "files": written + 2, "bytes": size}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
