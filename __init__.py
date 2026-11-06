"""Gateway Guardian — Telegram/gateway reliability health check.

Read-only status. Recovery returns an approved plan only; it never restarts,
kills or rebinds anything by itself.
"""

import json
import os
import re
import time
from pathlib import Path

STATUS_SCHEMA = {
    "name": "gateway_guardian_status",
    "description": (
        "Check Hermes gateway health: duplicate pollers, 409/Telegram polling "
        "conflicts, freezes, stale locks and missed deliveries. Use when the "
        "user reports Telegram silence, 409 conflicts, gateway freezes or when "
        "auditing gateway reliability."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tail_lines": {
                "type": "integer",
                "description": "How many recent log lines to scan (default 400, max 2000).",
            }
        },
    },
}

RECOVER_SCHEMA = {
    "name": "gateway_guardian_recover",
    "description": (
        "Return the approved recovery plan for a detected gateway problem. "
        "This tool never restarts or kills anything; it records the intent and "
        "prints the exact operator command to approve and run."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Recovery action: status, restart-gateway, clear-stale-lock, or rebind-telegram.",
            }
        },
        "required": ["action"],
    },
}

_PATTERNS = {
    "conflict_409": re.compile(r"\b409\b|conflict|terminated by other getupdates|getupdates.*terminated", re.I),
    "polling": re.compile(r"polling|getupdates", re.I),
    "freeze": re.compile(r"freeze|frozen|stuck|unresponsive", re.I),
    "stale_lock": re.compile(r"stale.*lock|lock.*stale|already in use|gateway.*lock", re.I),
    "missed_delivery": re.compile(r"missed.*(delivery|reply|message)|delivery.*(failed|missed)|send.*failed", re.I),
    "restart": re.compile(r"restart|starting|drain|shutdown", re.I),
}

_RECOVERY_PLANS = {
    "status": [
        "hermes gateway status --deep",
        "hermes doctor",
    ],
    "restart-gateway": [
        "hermes gateway status --deep",
        "hermes gateway restart -y --detach",
        "hermes gateway status --deep",
    ],
    "clear-stale-lock": [
        "hermes gateway status --deep",
        "Remove only the stale gateway lock file shown by status (never a live PID lock).",
        "hermes gateway restart -y --detach",
    ],
    "rebind-telegram": [
        "hermes gateway status --deep",
        "Stop duplicate Telegram pollers first (one gateway per token).",
        "hermes gateway restart -y --detach",
        "Send one Telegram test message and confirm delivery.",
    ],
}


def _hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".hermes"


def _log_candidates(home: Path) -> list[Path]:
    candidates = [home / "logs" / "gateway.log", home / "gateway.log"]
    profiles = home / "profiles"
    if profiles.exists():
        candidates.extend(sorted(profiles.glob("*/logs/gateway.log"))[:25])
    seen: set[Path] = set()
    out: list[Path] = []
    for path in candidates:
        if path.is_file() and path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _gateway_processes() -> list[int]:
    pids: list[int] = []
    proc = Path("/proc")
    if not proc.exists():
        return pids
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "hermes" in cmdline and "gateway" in cmdline:
            pids.append(int(entry.name))
    return sorted(pids)


def _read_tail(path: Path, tail_lines: int) -> list[str]:
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 262144))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return []
    return text.splitlines()[-max(1, min(tail_lines, 2000)):]


def _classify(lines: list[str]) -> dict:
    text = "\n".join(lines)
    counts = {name: len(pattern.findall(text)) for name, pattern in _PATTERNS.items()}
    if counts["conflict_409"] >= 3:
        state, cause = "BLOCKED", "repeated 409/polling conflict"
    elif counts["conflict_409"] or counts["freeze"] >= 2 or counts["stale_lock"] >= 2 or counts["missed_delivery"] >= 2:
        state, cause = "DEGRADED", "gateway warnings in recent logs"
    elif counts["freeze"] or counts["stale_lock"] or counts["missed_delivery"]:
        state, cause = "DEGRADED", "single gateway warning in recent logs"
    else:
        state, cause = "OK", "no gateway fault pattern in recent logs"
    return {"state": state, "cause": cause, "counts": counts}


def gateway_guardian_status(args: dict | None = None) -> str:
    args = args or {}
    tail_lines = int(args.get("tail_lines") or 400)
    home = _hermes_home()
    logs = _log_candidates(home)
    lines: list[str] = []
    for path in logs[:5]:
        lines.extend(_read_tail(path, tail_lines))
    result = _classify(lines)
    result.update(
        {
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "gateway_pids": _gateway_processes(),
            "log_files_scanned": [str(p) for p in logs[:5]],
            "note": "Read-only. Body text is not stored; only pattern counts are returned.",
        }
    )
    if not result["gateway_pids"] and result["state"] == "OK":
        result["state"] = "DEGRADED"
        result["cause"] = "no gateway process found"
    return json.dumps(result, indent=2, sort_keys=True)


def _record_intent(action: str) -> Path:
    data_dir = _hermes_home() / "plugin-data" / "gateway-guardian"
    data_dir.mkdir(parents=True, exist_ok=True)
    log = data_dir / "recovery-intents.log"
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} action={action}\n")
    return log


def gateway_guardian_recover(args: dict | None = None) -> str:
    args = args or {}
    action = str(args.get("action") or "status").strip()
    if action not in _RECOVERY_PLANS:
        return json.dumps(
            {
                "ok": False,
                "error": "unknown action",
                "allowed": sorted(_RECOVERY_PLANS),
            },
            indent=2,
        )
    log = _record_intent(action)
    return json.dumps(
        {
            "ok": True,
            "action": action,
            "executes": False,
            "operator_must_approve_and_run": _RECOVERY_PLANS[action],
            "intent_logged": str(log),
        },
        indent=2,
    )


def _gateway_command(ctx, raw_args: str = "") -> str:
    return gateway_guardian_status({"tail_lines": 400})


def register(ctx):
    ctx.register_tool(
        name="gateway_guardian_status",
        toolset="gateway_guardian",
        schema=STATUS_SCHEMA,
        handler=gateway_guardian_status,
    )
    ctx.register_tool(
        name="gateway_guardian_recover",
        toolset="gateway_guardian",
        schema=RECOVER_SCHEMA,
        handler=gateway_guardian_recover,
    )
    ctx.register_command(
        "gateway-guardian",
        _gateway_command,
        description="Show Gateway Guardian health status",
    )
