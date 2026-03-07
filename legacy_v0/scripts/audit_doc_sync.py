import os, re, json, hashlib, datetime

SUMMARY = "_management_documents/PROJECT_SUMMARY.md"
REPO_ROOT = "datashark-mcp/src/datashark_mcp"


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def collect_repo_files():
    out = []
    for root, _, files in os.walk(REPO_ROOT):
        for f in files:
            if f.endswith(".py"):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, ".")
                out.append({
                    "path": rel,
                    "sha": file_sha256(full),
                    "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(full)).isoformat(timespec="seconds"),
                })
    return sorted(out, key=lambda x: x["path"])


def parse_markdown_refs(path):
    text = open(path, "r", encoding="utf-8").read()
    refs = re.findall(r"datashark[^\s)`'\"]+\.py", text)
    phases = re.findall(r"Phase\s+\d+", text)
    return {"refs": sorted(set(refs)), "phases": sorted(set(phases))}


def main():
    repo_files = collect_repo_files()
    docs = {SUMMARY: parse_markdown_refs(SUMMARY)}
    all_doc_refs = sorted(set(docs[SUMMARY]["refs"]))

    missing_in_docs = [f["path"] for f in repo_files if f["path"] not in all_doc_refs]
    missing_in_repo = [r for r in all_doc_refs if not os.path.exists(r)]

    print("==== DATA SHARK DOC SYNCHRONIZATION AUDIT ====")
    print(f"Total .py files in repo: {len(repo_files)}")
    print(f"Referenced in docs: {len(all_doc_refs)}")
    print(f"Missing in docs: {len(missing_in_docs)}")
    for m in missing_in_docs:
        print(f"  • {m}")
    print(f"Missing in repo (stale references): {len(missing_in_repo)}")
    for r in missing_in_repo:
        print(f"  • {r}")
    print(f"Phases mentioned in summary: {docs[SUMMARY]['phases']}")
    print("================================================")
    report = {
        "timestamp": datetime.datetime.utcnow().isoformat(timespec="seconds"),
        "repo_file_count": len(repo_files),
        "doc_ref_count": len(all_doc_refs),
        "missing_in_docs": missing_in_docs,
        "missing_in_repo": missing_in_repo,
        "summary_phases": docs[SUMMARY]['phases'],
    }
    with open("scripts/audit_doc_sync_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print("✅ Audit report written to scripts/audit_doc_sync_report.json")


if __name__ == "__main__":
    main()


