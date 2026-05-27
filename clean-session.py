"""Strip advisor_tool_result blocks from Claude Code session JSONL files.

DeepSeek's Anthropic API rejects `advisor_tool_result` content blocks.
Session history from Anthropic sessions carries these blocks forward.
This script removes them so conversations can continue on DeepSeek.

Usage:
    python clean-session.py                            # auto-detect project
    python clean-session.py --path C:/path/to/project   # specify project
    python clean-session.py --dry-run                   # preview only
"""

import json
import shutil
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

UNSUPPORTED_TYPES = {"advisor_tool_result"}


def encode_path(p):
    return p.replace(":", "-").replace("\\", "-").replace("/", "-").replace("_", "-")


def find_project_dir(target_path=None):
    if target_path:
        encoded = encode_path(target_path)
        for d in PROJECTS_DIR.iterdir():
            if d.is_dir() and d.name == encoded:
                return d
        for d in PROJECTS_DIR.iterdir():
            if d.is_dir() and encoded in d.name:
                return d
        print(f"No project dir found for {target_path}")
        print(f"Tried matching: {encoded}")
        return None

    # Auto-detect from session metadata
    sessions = CLAUDE_DIR / "sessions"
    if sessions.exists():
        for sf in sorted(sessions.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(sf.read_text())
                cwd = data.get("cwd", "")
                if cwd:
                    return find_project_dir(cwd)
            except Exception:
                continue

    print("Could not auto-detect project. Use --path to specify.")
    return None


def find_affected_files(project_dir):
    affected = []
    for jsonl in sorted(project_dir.glob("*.jsonl")):
        try:
            with open(jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    if '"type":"advisor_tool_result"' in line:
                        affected.append(jsonl)
                        break
        except Exception:
            continue
    return affected


def count_references(text):
    return text.count('"type":"advisor_tool_result"')


def clean_line(line):
    """Remove advisor_tool_result objects from content arrays. Returns (cleaned_line, removed_count)."""
    if '"type":"advisor_tool_result"' not in line:
        return line, 0

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return line, 0

    msg = data.get("message", {})
    content = msg.get("content")

    if not isinstance(content, list):
        return line, 0

    new_content = []
    removed = 0
    for item in content:
        if isinstance(item, dict) and item.get("type") in UNSUPPORTED_TYPES:
            removed += 1
        else:
            new_content.append(item)

    if removed == 0:
        return line, 0

    if not new_content:
        # All content was advisor blocks — remove entire message
        return None, removed

    msg["content"] = new_content
    data["message"] = msg
    return json.dumps(data, ensure_ascii=False), removed


def clean_file(jsonl_path, dry_run=False):
    path = Path(jsonl_path)
    lines = path.read_text(encoding="utf-8").splitlines(True)
    cleaned_lines = []
    total_removed = 0
    lines_modified = 0
    lines_removed = 0

    for i, line in enumerate(lines):
        result, removed = clean_line(line)
        if result is None:
            lines_removed += 1
            total_removed += removed
        else:
            cleaned_lines.append(result)
            if removed > 0:
                total_removed += removed
                lines_modified += 1

    if total_removed == 0:
        return 0

    if not dry_run:
        bak = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, bak)
        path.write_text("".join(cleaned_lines), encoding="utf-8")
        print(f"  Backup: {bak.name}")

    print(f"  Blocks removed: {total_removed} ({lines_modified} lines modified, {lines_removed} lines deleted)")
    return total_removed


def main():
    dry_run = "--dry-run" in sys.argv
    target = None
    for i, arg in enumerate(sys.argv):
        if arg == "--path" and i + 1 < len(sys.argv):
            target = sys.argv[i + 1]

    project_dir = find_project_dir(target)
    if not project_dir:
        sys.exit(1)

    print(f"Project dir: {project_dir.name}")
    print(f"Path: {project_dir}")
    if dry_run:
        print("DRY RUN — no changes will be made")
    print()

    files = find_affected_files(project_dir)
    if not files:
        print("No files with advisor_tool_result blocks found.")
        return

    print(f"Found {len(files)} file(s) with unsupported content blocks:")
    print()

    total = 0
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  {f.name} ({size_mb:.1f} MB)")
        removed = clean_file(f, dry_run=dry_run)
        total += removed
        print()

    if dry_run:
        print(f"DRY RUN: would remove {total} blocks from {len(files)} file(s).")
        print("Run without --dry-run to apply.")
    else:
        print(f"Done. Removed {total} blocks from {len(files)} file(s).")
        print("Original files backed up as .jsonl.bak")
        print()
        print("Exit and restart Claude Code for changes to take effect.")


if __name__ == "__main__":
    main()
