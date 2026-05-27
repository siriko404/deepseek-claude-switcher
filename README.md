# Claude Code API Switcher

One-click toggle between DeepSeek and Anthropic APIs in Claude Code. Global or per-project. No manual JSON editing.

## Quick Start

```powershell
python switch-api.py
```

Double-click `switch-api.bat` for convenience.

First run seeds profiles from your existing config. After that, switching takes one keystroke.

## What It Does

Switches Claude Code's API routing by writing the `env` block in settings files:

| Provider | Base URL | Model |
|----------|----------|-------|
| DeepSeek | `api.deepseek.com/anthropic` | `deepseek-v4-pro` |
| Anthropic | (default) | `claude-opus-4-7` |

## Features

- **One-click switch** — interactive CLI with numbered menu
- **Global or per-project** — pick scope at startup
- **Diff preview** — see what changes before applying
- **Atomic writes** — temp file + rename, never corrupts settings
- **Rotating backups** — 5 copies of every settings file
- **API key management** — set/update keys with hidden input
- **Session cleaner** — auto-detects and offers to clean `advisor_tool_result` blocks when switching to DeepSeek (preserves data, creates backups)
- **GitHub-safe** — example config shipped, real keys in `~/.claude/`

## Requirements

- Python 3 (no pip packages needed)
- Windows, macOS, or Linux
- Claude Code installed

## Usage

```
python switch-api.py
```

### Scope Selection

```
  [1] Global
       Switch Claude Code globally (~/.claude/settings.json)
  [2] Specify project path
       Switch only for a specific project
  [3] Quit
```

### Provider Menu

```
  [1] DeepSeek
       Route through DeepSeek API proxy
  [2] Anthropic
       Use Anthropic API directly
  [3] Edit profiles file
       Open api-profiles.json to manually edit config
  [4] Restore settings from backup
       Roll back to a previous settings state
  [5] Set DeepSeek API key
       Update your DeepSeek API key (input hidden)
  [6] Change scope
       Switch between global and per-project mode
  [7] Quit
```

## Configuration

Profiles stored in `~/.claude/api-profiles.json`:

```json
{
  "deepseek": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "<your-key>",
    ...
  },
  "anthropic": {
    "ANTHROPIC_MODEL": "claude-opus-4-7",
    ...
  }
}
```

Edit directly or use menu `[3]`. API keys set via menu `[5]` with masked input.

## Session Cleaner

Switching to DeepSeek with old Anthropic advisor history? The tool offers to clean `advisor_tool_result` blocks from session files:

- Converts unsupported content to text placeholders
- Creates rotating backups before modifying
- Streams line-by-line (safe for multi-GB session files)
- Recursive scan catches agent sub-sessions

Also available standalone: `python clean-session.py --path /path/to/project`

## Safety

- **No secrets in repo** — `api-profiles.json` is `.gitignore`d, example template shipped
- **Atomic writes** — never corrupts settings on crash
- **Write-then-verify** — every save is re-read and validated
- **Rotating backups** — 5 copies kept for every file modified (`file.bak.0` through `.bak.4`)
- **Diff preview** — confirm changes before applying

## Files

```
deepseek-claude-switcher/
  switch-api.py                  Main tool
  switch-api.ps1                 PowerShell launcher
  switch-api.bat                 Double-click launcher
  clean-session.py               Standalone session cleaner
  api-profiles.example.json      Template (no real keys)
  docs/                          Design specification
```

## After Switching

**Restart Claude Code** for changes to take effect. The tool prints this reminder after every switch.
