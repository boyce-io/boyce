#!/usr/bin/env python3
import re
import sys
from pathlib import Path
import hashlib

ROOT = Path(__file__).resolve().parents[1]
SUM = ROOT / "_management_documents" / "PROJECT_SUMMARY.md"

HEADER_RE = re.compile(r"^<!-- Context Hash: (.*?) -->\n<!-- Last Verified: (.*?) -->", re.DOTALL)

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def compute_body_sha256(text: str) -> str:
    """
    Compute SHA-256 over the document body, excluding the first two header lines.

    Note: Historical false mismatches were observed due to trailing whitespace
    and standalone HTML comment lines. We normalize by:
      - stripping trailing whitespace for each line
      - removing lines that are HTML comment-only (e.g., <!-- ... -->)
      - preserving line order and using LF when joining
    This reduces spurious hash drift across editors/formatters.
    """
    lines = text.splitlines()
    body_lines = lines[2:]
    norm_lines = []
    for l in body_lines:
        s = l.rstrip()
        t = s.strip()
        # drop standalone HTML comment lines anywhere in the body
        if t.startswith("<!--") and t.endswith("-->"):
            continue
        norm_lines.append(s)
    body = "\n".join(norm_lines)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

def extract_fields(text: str):
    lines = text.splitlines()
    # headers
    m = HEADER_RE.match("\n".join(lines[:2]))
    ctx_hash = lines[0].split(":",1)[1].strip().strip(" -->") if lines and lines[0].startswith("<!-- Context Hash:") else None
    last_verified = lines[1].split(":",1)[1].strip().strip(" -->") if len(lines) > 1 and lines[1].startswith("<!-- Last Verified:") else None
    # fields
    active_branch = None
    phase_tag = None
    schema_version = None
    last_updated = None
    field_patterns = {
        "active_branch": re.compile(r"^[-*]?\s*\*\*Active Branch\*\*:\s*(.+)$"),
        "phase_tag": re.compile(r"^[-*]?\s*\*\*Phase Tag\*\*:\s*(.+)$"),
        "schema_version": re.compile(r"^[-*]?\s*\*\*Graph Schema Version\*\*:\s*(.+)$"),
        "last_updated": re.compile(r"^[-*]?\s*\*\*Last Updated\*\*:\s*(.+)$"),
    }
    for line in lines:
        s = line.strip()
        m = field_patterns["active_branch"].match(s)
        if m:
            active_branch = m.group(1).strip()
            continue
        m = field_patterns["phase_tag"].match(s)
        if m:
            phase_tag = m.group(1).strip()
            continue
        m = field_patterns["schema_version"].match(s)
        if m:
            schema_version = m.group(1).strip()
            continue
        m = field_patterns["last_updated"].match(s)
        if m:
            last_updated = m.group(1).strip()
            continue
    # Fallback simple substring extraction if regex didn't find
    def fallback(name, key, current):
        if current:
            return current
        token = f"**{name}:**"
        for line in lines:
            if token in line:
                return line.split(token,1)[1].strip()
        token2 = f"**{name}**:"
        for line in lines:
            if token2 in line:
                return line.split(token2,1)[1].strip()
        return None
    active_branch = fallback("Active Branch", "active_branch", active_branch)
    phase_tag = fallback("Phase Tag", "phase_tag", phase_tag)
    schema_version = fallback("Graph Schema Version", "schema_version", schema_version)
    last_updated = fallback("Last Updated", "last_updated", last_updated)
    return {
        "hash": ctx_hash,
        "last_verified": last_verified,
        "active_branch": active_branch,
        "phase_tag": phase_tag,
        "schema_version": schema_version,
        "last_updated": last_updated,
    }

def main() -> int:
    sum_text = read(SUM)
    summ = extract_fields(sum_text)

    # recompute hash
    sum_live = compute_body_sha256(sum_text)

    issues = []

    # Verify Context Hash matches computed hash
    if (summ["hash"] or "").strip() != sum_live:
        issues.append("Project Summary Context Hash does not match live recomputation")

    if not issues:
        print("Context Hash Verified ✅")
        return 0
    else:
        print("Context Hash Issues:\n- " + "\n- ".join(issues))
        return 1

if __name__ == "__main__":
    sys.exit(main())


