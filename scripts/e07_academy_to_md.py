#!/usr/bin/env python3
"""E0.7 Skylit Academy raw JSON -> readable markdown with provenance.

Reads docs/re/skylit-academy/raw/*.json (captured 2026-10-02 from the logged-in
app.skylit.ai session, /api/nexus/academy/courses endpoints, read-only) and
writes one markdown file per course under docs/re/skylit-academy/, grouped by
track (heatseeker / flowseeker), plus INDEX.md.

Every output file carries provenance: API URL, course id, capture date.
Usage: python3 scripts/e07_academy_to_md.py
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "docs", "re", "skylit-academy", "raw")
OUT = os.path.join(ROOT, "docs", "re", "skylit-academy")
CAPTURED = "2026-10-02"


def slug(s: str) -> str:
    s = re.sub(r"[^0-9A-Za-z]+", "-", s).strip("-").lower()
    return s[:60] or "untitled"


def main() -> None:
    courses = []
    for fn in sorted(os.listdir(RAW)):
        if not (fn.startswith("course_") and fn.endswith(".json")):
            continue
        with open(os.path.join(RAW, fn)) as f:
            courses.append(json.load(f))

    courses.sort(key=lambda c: (c.get("categoryTrack") or "",
                                c.get("categorySortOrder") or 0,
                                c.get("sortOrder") or 0))

    index_rows = []
    for c in courses:
        track = (c.get("categoryTrack") or "unknown").lower()
        name = slug(c.get("title") or c["id"])
        out_fn = f"{track}-{c.get('sortOrder', 0):02d}-{name}.md"
        cid = c["id"]
        api = f"https://app.skylit.ai/api/nexus/academy/courses/{cid}"

        lines = [
            f"# {c.get('title', '').strip()}",
            "",
            f"- Track: {track} / category: {c.get('categoryName', '')}",
            f"- Level: {c.get('experienceLevel', '')} · duration: {c.get('estimatedDuration', '')}",
            f"- Passing score: {c.get('passingScore', '')} · sections: {c.get('sectionCount', '')} · quiz questions: {c.get('questionCount', '')}",
            f"- Provenance: {api} (JSON, captured {CAPTURED}, read-only) · course id `{cid}`",
            f"- Views/completions at capture: {c.get('viewCount', '')}/{c.get('completedCount', '')}",
            "",
            "## Course description",
            "",
            (c.get("description") or "").strip() or "(none)",
            "",
        ]
        for s in sorted(c.get("sections") or [], key=lambda x: x.get("sortOrder") or 0):
            lines.append(f"## Section {s.get('sortOrder', '?')}: {s.get('title', '')}")
            lines.append("")
            lines.append((s.get("introContent") or "").strip() or "(empty)")
            lines.append("")
            qs = s.get("questions") or []
            if qs:
                lines.append(f"### Quiz ({len(qs)} questions)")
                lines.append("")
                for q in qs:
                    prompt = (q.get("questionText") or q.get("text") or "").strip()
                    lines.append(f"- Q: {prompt}")
                    for k in ("options", "answers", "choices"):
                        opts = q.get(k)
                        if isinstance(opts, list):
                            for o in opts:
                                label = o.get("text") if isinstance(o, dict) else str(o)
                                correct = o.get("isCorrect") if isinstance(o, dict) else None
                                mark = " [correct]" if correct else ""
                                lines.append(f"    - {label}{mark}")
                    ans = q.get("explanation") or q.get("answerExplanation")
                    if ans:
                        lines.append(f"    - explanation: {str(ans).strip()}")
                lines.append("")
        with open(os.path.join(OUT, out_fn), "w") as f:
            f.write("\n".join(lines))
        index_rows.append((track, c.get("categoryName", ""), c.get("sortOrder", 0),
                           c.get("title", "").strip(), out_fn, cid))

    with open(os.path.join(OUT, "INDEX.md"), "w") as f:
        f.write("# Skylit Academy capture — index\n\n")
        f.write(f"Captured {CAPTURED} from the logged-in app.skylit.ai session "
                "(acct lapcheong) via `/api/nexus/academy/courses*` JSON, read-only.\n\n")
        f.write("| track | category | # | course | file | course id |\n|---|---|---|---|---|---|\n")
        for r in index_rows:
            f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | `{r[5]}` |\n")
        f.write(f"\nTotal courses: {len(index_rows)}\n")

    print(f"wrote {len(index_rows)} course files + INDEX.md -> {OUT}")


if __name__ == "__main__":
    main()
