"""How risky is something Claude wants to do.

"read" passes without asking. "normal" needs a two-second hold on the watch;
"destructive" needs three, on a red card. The patterns err toward asking:
a command that is not clearly read-only is at least normal.
"""

import re

HOLD_SECONDS = {"normal": 2, "destructive": 3}

_SHELL_TOOLS = {"Bash", "PowerShell"}
_READING_TOOLS = {"Read", "Glob", "Grep", "LS", "WebSearch", "TodoWrite"}

_READ_ONLY = re.compile(
    r"^\s*(git\s+(status|diff|log|show)\b|ls\b|dir\b|pwd\b|cat\b|type\b|head\b|tail\b|wc\b|"
    r"where\b|which\b|echo\b|Get-ChildItem\b|Get-Content\b|Get-Location\b|Select-String\b|Test-Path\b)",
    re.IGNORECASE,
)
# Anything that can hide a second command: a new line, chaining, pipes,
# redirects, and every way bash or PowerShell substitutes or expands
# ($x, $(...), (...), @(...), {...}, %VAR%, backticks).
_CHAINING = re.compile(r"[\n\r;&|<>`$(){}@%]")
_DESTRUCTIVE = re.compile(
    r"(\brm\b|\bdel\b|\berase\b|\brmdir\b|\brd\s+/s|Remove-Item|Clear-Content|\bformat\s+[a-z]:|diskpart|mkfs|"
    r"git\s+push|git\s+reset\s+--hard|git\s+clean\s+-[a-z]*f|git\s+branch\s+(-d|-D|--delete)\b|git\s+checkout\s+--\s|"
    r"git\s+rebase|git\s+filter-branch|\breg\s+(add|delete|import)\b|Remove-ItemProperty|"
    r"\bshutdown\b|Stop-Computer|Restart-Computer|Stop-Process|\btaskkill\b|"
    r"npm\s+publish|pip\s+uninstall|npm\s+uninstall|drop\s+(table|database)|truncate\s+table|"
    r"\bicacls\b|\btakeown\b|cipher\s+/w|\|\s*(sh|bash|iex)\b)",
    re.IGNORECASE,
)


def classify(tool_name: str, tool_input: dict) -> str:
    if tool_name in _SHELL_TOOLS:
        command = str((tool_input or {}).get("command") or "")
        if not command.strip():
            return "normal"
        if _DESTRUCTIVE.search(command):
            return "destructive"
        if _READ_ONLY.match(command) and not _CHAINING.search(command):
            return "read"
        return "normal"
    if tool_name in _READING_TOOLS:
        return "read"
    return "normal"
