import json
import os
import shutil
import subprocess
import tempfile
from getpass import getpass
from pathlib import Path

HOME = Path.home()
CLAUDE_DIR = HOME / ".claude"
GLOBAL_SETTINGS = CLAUDE_DIR / "settings.json"
PROFILES = CLAUDE_DIR / "api-profiles.json"
MAX_BACKUPS = 5

THIS_PROJECT = Path(__file__).resolve().parent
PROJECT_LOCAL = THIS_PROJECT / ".claude" / "settings.local.json"

ANTHROPIC_PROFILE = {
    "ANTHROPIC_MODEL": "claude-opus-4-7",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-7",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5-20251001",
    "CLAUDE_CODE_SUBAGENT_MODEL": "claude-sonnet-4-6",
}

DEEPSEEK_TEMPLATE = {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "",
    "ANTHROPIC_MODEL": "deepseek-v4-pro[1m]",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro[1m]",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-v4-pro[1m]",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-v4-flash",
    "CLAUDE_CODE_SUBAGENT_MODEL": "deepseek-v4-flash",
    "CLAUDE_CODE_EFFORT_LEVEL": "max",
}

REQUIRED_KEYS = [
    "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
]


def load_json(path):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error reading {path}: {e}")
            backup = path.with_suffix(path.suffix + ".corrupt")
            shutil.copy2(path, backup)
            print(f"Corrupt file backed up to {backup}")
            return {}
    return {}


def atomic_save(path, data):
    """Write to temp file, verify, rename. Cross-drive safe via shutil.move."""
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(parent), suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        with open(tmp, "r", encoding="utf-8") as f:
            json.load(f)
        shutil.move(tmp, str(path))
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def rotate_backups(base):
    """Keep MAX_BACKUPS rotating copies: base.bak.0 (newest) through .bak.N."""
    base = Path(str(base))
    for i in range(MAX_BACKUPS - 1, -1, -1):
        old = Path(f"{base}.bak.{i}")
        if old.exists():
            if i == MAX_BACKUPS - 1:
                old.unlink()
            else:
                old.rename(Path(f"{base}.bak.{i + 1}"))
    if base.exists():
        shutil.copy2(str(base), f"{base}.bak.0")


def validate_profile(profile, name):
    missing = [k for k in REQUIRED_KEYS if k not in profile or not profile[k]]
    if missing:
        print(f"WARNING: {name} profile missing keys: {missing}")
        return False
    return True


def detect_provider(env):
    if not env:
        return None
    url = env.get("ANTHROPIC_BASE_URL", "")
    if "deepseek" in url:
        return "deepseek"
    if url:
        return "deepseek"
    if "ANTHROPIC_AUTH_TOKEN" in env and env["ANTHROPIC_AUTH_TOKEN"]:
        return "deepseek"
    model = env.get("ANTHROPIC_MODEL", "")
    if "deepseek" in model:
        return "deepseek"
    if model:
        return "anthropic"
    return None


def compute_diff(old_env, new_env):
    added, removed, changed = {}, {}, {}
    all_keys = set(old_env) | set(new_env)
    for k in sorted(all_keys):
        if k in new_env and k not in old_env:
            added[k] = new_env[k]
        elif k in old_env and k not in new_env:
            removed[k] = old_env[k]
        elif k in old_env and k in new_env and old_env[k] != new_env[k]:
            changed[k] = (old_env[k], new_env[k])
    return added, removed, changed


def mask_key(key):
    if not key or len(key) < 8:
        return "(not set)"
    return key[:6] + "..." + key[-4:]


def set_api_key(profiles):
    deepseek = profiles.get("deepseek", {})
    current = deepseek.get("ANTHROPIC_AUTH_TOKEN", "")
    print()
    print(f"  Current DeepSeek API key: {mask_key(current)}")
    print()
    new_key = getpass("  Enter new key (or press Enter to keep current): ").strip()
    if new_key:
        deepseek["ANTHROPIC_AUTH_TOKEN"] = new_key
        profiles["deepseek"] = deepseek
        atomic_save(PROFILES, profiles)
        print("  Key updated.")
    else:
        print("  Key unchanged.")


def first_run_setup():
    deepseek = dict(DEEPSEEK_TEMPLATE)

    if PROJECT_LOCAL.exists():
        local = load_json(PROJECT_LOCAL)
        local_env = local.get("env", {})
        if local_env.get("ANTHROPIC_AUTH_TOKEN"):
            deepseek["ANTHROPIC_AUTH_TOKEN"] = local_env["ANTHROPIC_AUTH_TOKEN"]

    if not deepseek["ANTHROPIC_AUTH_TOKEN"]:
        print("DeepSeek API key not found in project config.")
        deepseek["ANTHROPIC_AUTH_TOKEN"] = getpass("Enter DeepSeek API key: ").strip()

    profiles = {"deepseek": deepseek, "anthropic": ANTHROPIC_PROFILE}
    validate_profile(deepseek, "deepseek")
    validate_profile(ANTHROPIC_PROFILE, "anthropic")
    atomic_save(PROFILES, profiles)
    print(f"Profiles saved to {PROFILES}")
    print("WARNING: API keys stored in plaintext. Do not share this file.")
    return profiles


def switch_to(profiles, provider, old_provider, target_path):
    new_env = dict(profiles[provider])
    old_env = dict(profiles.get(old_provider, {})) if old_provider else {}

    # Block DeepSeek switch if no API key (before diff — fixes audit F9)
    if provider == "deepseek" and not profiles.get("deepseek", {}).get("ANTHROPIC_AUTH_TOKEN"):
        print()
        print("  Cannot switch to DeepSeek: no API key set.")
        print("  Use menu option to set the DeepSeek API key first.")
        return

    validate_profile(profiles[provider], provider)

    settings = load_json(target_path)
    current_env = dict(settings.get("env", {}))

    # Compute target env
    target_env = dict(current_env)
    for k, v in new_env.items():
        target_env[k] = v
    for k in old_env:
        if k not in new_env:
            target_env.pop(k, None)
    if not new_env.get("ANTHROPIC_BASE_URL"):
        target_env.pop("ANTHROPIC_BASE_URL", None)
    if not new_env.get("ANTHROPIC_AUTH_TOKEN"):
        target_env.pop("ANTHROPIC_AUTH_TOKEN", None)
    if not new_env.get("CLAUDE_CODE_EFFORT_LEVEL"):
        target_env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)

    added, removed, changed = compute_diff(current_env, target_env)

    print()
    if not added and not removed and not changed:
        print("No changes needed. Already on this profile.")
        return

    if removed:
        print("  Will REMOVE:")
        for k, v in removed.items():
            print(f"    - {k} = {v}")
    if added:
        print("  Will ADD:")
        for k, v in added.items():
            print(f"    + {k} = {v}")
    if changed:
        print("  Will CHANGE:")
        for k, (old, new) in changed.items():
            print(f"    ~ {k}: {old} -> {new}")

    print()
    confirm = input(f"  Apply switch to {provider}? [Y/n]: ").strip().lower()
    if confirm and confirm != "y":
        print("Cancelled.")
        return

    rotate_backups(target_path)
    settings["env"] = target_env
    atomic_save(target_path, settings)

    # Write-then-verify
    verify = load_json(target_path)
    verify_env = verify.get("env", {})
    for k, v in target_env.items():
        if verify_env.get(k) != v:
            print(f"VERIFY FAILED: {k} expected {v}, got {verify_env.get(k)}")
            print(f"Restore from backup: {target_path}.bak.0")
            return
    print("Write verified.")

    # Global scope: clean script's own project-local overrides (audit F5 fix)
    is_global = (target_path == GLOBAL_SETTINGS)
    if is_global and PROJECT_LOCAL.exists():
        local = load_json(PROJECT_LOCAL)
        local_env = local.get("env", {})
        anthro_keys = [k for k in local_env
                       if k.startswith("ANTHROPIC") or k.startswith("CLAUDE_CODE")]
        if anthro_keys:
            for k in anthro_keys:
                del local_env[k]
            if not local_env and "env" in local:
                del local["env"]
            atomic_save(PROJECT_LOCAL, local)
            print(f"Cleared {len(anthro_keys)} API keys from {PROJECT_LOCAL}")

    label = profiles[provider].get("ANTHROPIC_MODEL", provider)
    print(f"Switched to {provider} ({label}).")

    # Local scope: warn about git leak risk (audit F1 fix)
    if not is_global and provider == "deepseek":
        print()
        print("  WARNING: API key written to this project's .claude/settings.local.json.")
        print("  Ensure .claude/ is in .gitignore before committing this project.")

    print("Restart Claude Code for changes to take effect.")

    # Offer session cleaning for local DeepSeek switches
    if not is_global and provider == "deepseek":
        offer_session_clean(target_path)


def restore_backup(target_path):
    parent = Path(target_path).parent
    backups = sorted(parent.glob(f"{Path(target_path).name}.bak.*"),
                     key=lambda p: p.name)
    if not backups:
        print("No backups found.")
        return

    print()
    print("  Available backups:")
    for i, b in enumerate(backups):
        size = b.stat().st_size
        print(f"  [{i}] {b.name} ({size} bytes)")
    print(f"  [{len(backups)}] Cancel")
    print()

    choice = input("  Restore from backup #: ").strip()
    try:
        idx = int(choice)
    except ValueError:
        print("Invalid choice.")
        return

    if idx == len(backups):
        return
    if idx < 0 or idx >= len(backups):
        print("Invalid choice.")
        return

    rotate_backups(target_path)
    shutil.copy2(str(backups[idx]), str(target_path))

    try:
        settings = load_json(target_path)
        if settings is not None:
            env = settings.get("env", {})
            provider = detect_provider(env)
            print(f"Restored from {backups[idx].name}")
            print(f"Current provider: {provider}")
            print("Restart Claude Code for changes to take effect.")
    except Exception:
        print("Restored file is not valid JSON.")


def encode_project_name(path_str):
    """Encode a project path to Claude Code's directory naming convention."""
    encoded = path_str.replace(":", "-").replace("\\", "-").replace("/", "-")
    return encoded.replace("_", "-")


def find_project_dir(project_path):
    """Find the ~/.claude/projects/ directory for a project path. Exact match only."""
    target = Path(project_path).resolve()
    encoded = encode_project_name(str(target))
    proj_dir = CLAUDE_DIR / "projects" / encoded
    if proj_dir.is_dir():
        return proj_dir
    return None


def claude_code_running():
    """Check if Claude Code processes are running. Warns if found."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq node.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5
        )
        count = result.stdout.strip().count("\n") + 1 if result.stdout.strip() else 0
        if count > 50:
            return True
    except Exception:
        pass
    return False


def clean_session_files(project_dir):
    """Stream-clean all session JSONL files in project_dir (recursive, excludes .bak)."""
    jsonl_files = list(project_dir.glob("**/*.jsonl"))
    jsonl_files = [f for f in jsonl_files if ".bak" not in f.suffixes]

    # Quick scan: check only first 4KB of each file for advisor blocks
    candidate_files = []
    total_blocks = 0
    total_size = 0
    for path in jsonl_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                head = f.read(4096)
        except Exception:
            continue
        if '"type":"advisor_tool_result"' in head:
            size = path.stat().st_size
            total_size += size
            total_blocks += head.count('"type":"advisor_tool_result"')
            candidate_files.append(path)

    if not candidate_files:
        return 0

    print(f"\n  Found ~{total_blocks}+ unsupported advisor blocks across {len(candidate_files)} file(s)")
    print(f"  ({total_size / (1024*1024):.0f} MB total)")

    if claude_code_running():
        print("  WARNING: Claude Code may be running. Close it first to avoid data loss.")
        print("  Skipping clean — run clean-session.py after closing Claude Code.")
        return 0

    confirm = input("  Clean session files for DeepSeek compatibility? [Y/n]: ").strip().lower()
    if confirm and confirm != "y":
        print("  Skipped. Run clean-session.py later if needed.")
        return 0

    total_removed = 0
    last_cleaned = None
    for path in jsonl_files:
        # Rotating backup
        rotate_backups(path)

        # Stream: read line by line, write to temp, atomic replace
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent), suffix=".tmp", text=True
        )
        blocks_removed = 0

        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as out:
                with open(path, "r", encoding="utf-8") as fh:
                    for line_num, line in enumerate(fh, 1):
                        if '"type":"advisor_tool_result"' in line:
                            try:
                                data = json.loads(line)
                            except json.JSONDecodeError:
                                print(f"  Warning: corrupt JSON at {path.name}:{line_num}")
                                out.write(line)
                                continue
                            msg = data.get("message", {})
                            content = msg.get("content")
                            if isinstance(content, list):
                                new_content = []
                                for item in content:
                                    if item.get("type") == "advisor_tool_result":
                                        blocks_removed += 1
                                        new_content.append({
                                            "type": "text",
                                            "text": "[Advisor output omitted — unsupported on DeepSeek]",
                                        })
                                    else:
                                        new_content.append(item)
                                msg["content"] = new_content
                                data["message"] = msg
                            line = json.dumps(data, ensure_ascii=False) + "\n"
                        out.write(line)
            shutil.move(tmp_path, str(path))
            total_removed += blocks_removed
            if blocks_removed:
                print(f"  {path.name}: {blocks_removed} blocks converted")
                last_cleaned = path
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    print(f"  Done. {total_removed} blocks converted across {len(candidate_files)} file(s).")
    print(f"  Originals in rotated backups (file.bak.0, .bak.1, ...)")
    return total_removed


def offer_session_clean(target_path):
    """After switching a project to DeepSeek, offer to clean session files."""
    project_path = Path(target_path).parent.parent
    project_dir = find_project_dir(str(project_path))
    if not project_dir:
        return
    clean_session_files(project_dir)


def scope_prompt():
    """Returns (target_path, label) or (None, None) to quit."""
    while True:
        print()
        print("  ===================================")
        print("     Select Switch Scope")
        print("  ===================================")
        print()
        print("  [1] Global")
        print("       \033[90mSwitch Claude Code globally (~/.claude/settings.json)\033[0m")
        print()
        print("  [2] Specify project path")
        print("       \033[90mSwitch only for a specific project\033[0m")
        print()
        print("  [3] Quit")
        print()

        choice = input("  Choice: ").strip()

        if choice == "1":
            return GLOBAL_SETTINGS, "GLOBAL"
        elif choice == "2":
            raw = input("  Project path: ").strip()
            raw = raw.strip("'\"").strip()
            target = Path(raw).resolve()
            if not target.exists():
                print(f"  Path does not exist: {target}")
                continue
            if target.is_file():
                target = target.parent
            local = target / ".claude" / "settings.local.json"
            print(f"  Target: {local}")
            confirm = input("  Use this path? [Y/n]: ").strip().lower()
            if confirm and confirm != "y":
                continue
            return local, f"PROJECT: {target.name}"
        elif choice == "3":
            return None, None
        else:
            print("Invalid choice.")


def main():
    if not PROFILES.exists():
        profiles = first_run_setup()
    else:
        profiles = load_json(PROFILES)
        validate_profile(profiles.get("deepseek", {}), "deepseek")
        validate_profile(profiles.get("anthropic", {}), "anthropic")

    target_path, scope_label = scope_prompt()
    if target_path is None:
        return

    while True:
        settings = load_json(target_path)
        current = detect_provider(settings.get("env", {}))
        if current:
            model = profiles.get(current, {}).get("ANTHROPIC_MODEL", "?")
        else:
            model = "not configured"

        print()
        print("  ===================================")
        print("     Claude Code API Switcher")
        print(f"     Scope: {scope_label}")
        print("  ===================================")
        print(f"  Current: {current or 'none'} ({model})")
        print()
        print("  [1] DeepSeek")
        print("       \033[90mRoute through DeepSeek API proxy\033[0m")
        print()
        print("  [2] Anthropic")
        print("       \033[90mUse Anthropic API directly\033[0m")
        print()
        print("  [3] Edit profiles file")
        print("       \033[90mOpen api-profiles.json to manually edit config\033[0m")
        print()
        print("  [4] Restore settings from backup")
        print("       \033[90mRoll back to a previous settings state\033[0m")
        print()
        print("  [5] Set DeepSeek API key")
        print("       \033[90mUpdate your DeepSeek API key (input hidden)\033[0m")
        print()
        print("  [6] Change scope")
        print("       \033[90mSwitch between global and per-project mode\033[0m")
        print()
        print("  [7] Quit")
        print()

        choice = input("  Choice: ").strip()

        if choice == "1":
            switch_to(profiles, "deepseek", current, target_path)
        elif choice == "2":
            switch_to(profiles, "anthropic", current, target_path)
        elif choice == "3":
            print(f"Profiles: {PROFILES}")
            print("Open this file in a text editor to modify values.")
        elif choice == "4":
            restore_backup(target_path)
        elif choice == "5":
            set_api_key(profiles)
        elif choice == "6":
            target_path, scope_label = scope_prompt()
            if target_path is None:
                break
        elif choice == "7":
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
