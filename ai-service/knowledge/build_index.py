from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.index import (
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
