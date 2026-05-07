"""Generate a crawl-jobs.json manifest from a text file of slugs (one per line)."""

import json
import sys
from pathlib import Path

TEMPLATE = {
    "task": "crawl",
    "payload": {
        "formats": ["EPUB"],
        "grouping": "1",
        "skip_illustrations": False,
        "output_folder": "/home/tung/Data/novels",
    },
}


def main():
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <slugs.txt>")
        sys.exit(1)

    src = Path(sys.argv[1])
    if not src.is_file():
        print(f"File not found: {src}")
        sys.exit(1)

    slugs = [line.strip() for line in src.read_text().splitlines() if line.strip()]
    if not slugs:
        print("No slugs found in file.")
        sys.exit(1)

    jobs = []
    for slug in slugs:
        job = {**TEMPLATE, "alias_id": slug, "payload": {**TEMPLATE["payload"], "slug": slug}}
        jobs.append(job)

    out = src.with_name("crawl-jobs.json")
    out.write_text(json.dumps(jobs, indent=4, ensure_ascii=False))
    print(f"Generated {out} with {len(jobs)} job(s).")


if __name__ == "__main__":
    main()
