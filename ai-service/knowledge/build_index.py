"""Build the Module 21 knowledge index. Run by hand; never at import time.

    cd ai-service
    python knowledge/build_index.py

Writes `knowledge/artifacts/knowledge_index_v1.json`, which is COMMITTED.

This mirrors `ml/train_diabetes.py` and its siblings: a separate, re-runnable
script produces a reviewable artifact that the service only ever loads. The
reasons are the ones `app/rag/index.py` gives -- reproducibility, reviewability,
and a startup cost that does not scale with the corpus.

The build is DETERMINISTIC. Running it twice on an unchanged corpus produces a
byte-identical file, which is what makes "the index in the repository is the
index that was reviewed" a checkable claim rather than a hope. `--check` asserts
exactly that without writing, which is what CI should run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `app` importable when run as a script from the service root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.index import (  # noqa: E402
    DEFAULT_INDEX_PATH,
    SIMILARITY_FLOOR,
    KnowledgeIndex,
    save_index,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed artifact matches a fresh build; write nothing",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        help=f"artifact path (default: {DEFAULT_INDEX_PATH})",
    )
    args = parser.parse_args()

    index = KnowledgeIndex.build()
    stats = index.stats()

    if args.check:
        if not args.out.exists():
            print(f"FAIL: no artifact at {args.out}", file=sys.stderr)
            return 1
        committed = args.out.read_text(encoding="utf-8")
        fresh = json.dumps(
            index.to_dict(), indent=1, sort_keys=True, ensure_ascii=False
        )
        if committed != fresh:
            print(
                "FAIL: the committed index does not match a fresh build of the "
                "current corpus. Re-run `python knowledge/build_index.py`.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: committed index matches a fresh build ({stats['chunks']} chunks)")
        return 0

    written = save_index(index, args.out)

    print(f"knowledge index written to {written}")
    print(f"  corpus version    {stats['corpus_version']}")
    print(f"  fingerprint       {stats['fingerprint'][:16]}...")
    print(f"  documents         {stats['documents']}")
    print(f"  chunks            {stats['chunks']}")
    print(f"  vocabulary        {stats['vocabulary_size']} terms")
    print(
        f"  chunk chars       min {stats['chunk_chars_min']} / "
        f"mean {stats['chunk_chars_mean']} / max {stats['chunk_chars_max']}"
    )
    print(f"  similarity floor  {SIMILARITY_FLOOR}")
    print(f"  by topic          {stats['chunks_by_topic']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
