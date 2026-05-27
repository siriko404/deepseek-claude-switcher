# API Provider Switcher (`apix`) — Design Spec v2

**Date:** 2026-05-26
**Tier:** 1 (small feature, ~350 LOC, single file)
**Status:** locked

## Purpose

Single Python CLI script that switches Claude Code between DeepSeek (proxy) and Anthropic (native) APIs. Supports global (~/.claude/settings.json) and per-project (.claude/settings.local.json) scope. Ships GitHub-safe with no embedded keys.

## File layout

```
deepseek/
  switch-api.py
  switch-api.ps1                    # Windows launcher
  switch-api.bat                    # double-click launcher
  api-profiles.example.json         # GitHub-safe template (no real keys)
  docs/superpowers/specs/2026-05-26-api-switcher-design.md
```

Runtime files (auto-created, .gitignored):
- `~/.claude/api-profiles.json` — single source of truth for both provider configs
- `~/.claude/settings.json` — global target (env key only; rest preserved)
- `[project]/.claude/settings.local.json` — per-project target

## Profiles

DeepSeek:
```
ANTHROPIC_BASE_URL          = https://api.deepseek.com/anthropic
ANTHROPIC_AUTH_TOKEN        = <user's DeepSeek API key>
ANTHROPIC_MODEL             = deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_OPUS_MODEL   = deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_SONNET_MODEL = deepseek-v4-pro[1m]
ANTHROPIC_DEFAULT_HAIKU_MODEL  = deepseek-v4-flash
CLAUDE_CODE_SUBAGENT_MODEL     = deepseek-v4-flash
CLAUDE_CODE_EFFORT_LEVEL       = max
```

Anthropic:
```
ANTHROPIC_MODEL             = claude-opus-4-7
ANTHROPIC_DEFAULT_OPUS_MODEL   = claude-opus-4-7
ANTHROPIC_DEFAULT_SONNET_MODEL = claude-sonnet-4-6
ANTHROPIC_DEFAULT_HAIKU_MODEL  = claude-haiku-4-5-20251001
CLAUDE_CODE_SUBAGENT_MODEL     = claude-sonnet-4-6
```

## Startup Flow (v2)

1. If `~/.claude/api-profiles.json` missing → first-run setup (seed from existing config)
2. **Scope selection:**
   ```
   [1] Global (~/.claude/settings.json)
   [2] This project only (cwd/.claude/settings.local.json)
   [3] Specify project path
   [4] Quit
   ```
3. After scope selected → provider menu with scope label in header

## Provider Menu (v2)

```
  ===================================
     Claude Code API Switcher
     Scope: GLOBAL
  ===================================
  Current: DeepSeek (deepseek-v4-pro)

  [1] DeepSeek
  [2] Anthropic
  [3] Edit profiles file
  [4] Restore settings from backup
  [5] Set DeepSeek API key
  [6] Quit
```

## Switch Logic (diff-and-reconcile, target_path threaded)

1. Validate provider has API key before proceeding
2. Read target file (global or project-local)
3. Compute diff (ADD/REMOVE/CHANGE) between current and target env
4. Show diff, ask [Y/n] confirmation
5. Rotating backup of target file (5 copies)
6. Apply changes (diff-and-reconcile)
7. Atomic write + write-then-verify
8. If global: clean PROJECT_LOCAL of ANTHROPIC keys
9. If local + DeepSeek: warn about API key in project dir
10. Offer session cleaning (v3 — see below)
11. Print confirmation + restart notice

## Session Cleaning (v3)

After switching a project to DeepSeek, the tool scans that project's Claude Code session files in `~/.claude/projects/` for `advisor_tool_result` content blocks (unsupported by DeepSeek's API). If found:

1. Shows block count and total file size
2. Warns if Claude Code process is running
3. Offers to clean: converts blocks to text placeholders (data preserved via `_stashed_type`/`_stashed_content`)
4. Streams line-by-line (handles 291MB+ files without memory blowup)
5. Recursive glob catches `subagents/agent-*.jsonl` files
6. Rotating backups (`.bak.0`–`.bak.4`) before modification
7. Atomic write via temp file + `shutil.move`
8. Corrupt JSON lines logged and preserved as-is

## API Key Management (v2)

- Menu [5] reads current key, shows masked: `sk-de58...a33e`
- Prompts for new key using `getpass` (input hidden, like password prompt)
- Stores in `api-profiles.json` under `deepseek.ANTHROPIC_AUTH_TOKEN`
- DeepSeek switch blocked with clear message if key is empty
- GitHub safety: `.gitignore` entry for `api-profiles.json`, example template shipped

## Key Functions & Changes from v1

| Function | v2 Change |
|----------|-----------|
| `main()` | Added scope selection loop before provider loop. Threads `target_path` to all consumers. |
| `switch_to(target_path, ...)` | Reads/writes `target_path` instead of hardcoded `SETTINGS`. Key validation before diff. |
| `detect_provider(env)` | Unchanged (takes env dict, path-agnostic) |
| `restore_backup(target_path)` | Globs backups from `target_path.parent`. Restores to `target_path`. |
| `atomic_save(path, data)` | Creates temp in `path.parent`, uses `shutil.move` for cross-drive. Creates parent dir if needed. |
| `rotate_backups(base)` | Unchanged (derives backup paths from base, path-agnostic) |
| `set_api_key(profiles)` | New. Uses `getpass`. Shows masked current key. |
| `mask_key(key)` | New. Returns `sk-abc...xyz1` format. |
| `scope_prompt()` | New. Returns selected target Path or None. |

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Old provider env keys persist after switch | Diff-and-reconcile |
| settings.json corrupted on write | Atomic write + rotating backups (5) + write-then-verify |
| Project-local overrides block global switch | Strip ANTHROPIC keys from script's project local on global switch |
| API key in plaintext | Warn on first run + warn on local DeepSeek switch |
| Key visible during typing | `getpass` masks input |
| Cross-drive write failure | `shutil.move` (fallback copy+delete) |
| Local mode writes to wrong project | Path shown in header and scope prompt, user confirms |
| Key committed to GitHub in local mode | Explicit warning after local DeepSeek switch |
| Launcher forces cwd to script dir | Launchers for global use; terminal invocation for per-project |
| Already on provider, key changed | Key validation runs before diff check |
