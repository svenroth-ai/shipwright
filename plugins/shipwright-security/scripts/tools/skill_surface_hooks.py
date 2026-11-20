"""Hook and settings checks (``SURFACE_HOOK_REMOTE_SINK``, ``SURFACE_SETTINGS_SHELL_KEY``).

``prompt_injection_scan.scan_hooks_json`` already blocks ``curl | bash`` style
downloads by line pattern. This module adds the *structural* checks it cannot do:

* a hook that posts its event payload to a non-loopback host (``type: http`` or a
  command that drives ``nc`` / ``scp`` / ``rsync`` against a remote target)
* settings keys whose value is a shell command the agent runs on its own once the
  file is active (``apiKeyHelper``, ``statusLine``, ``fileSuggestion`` ...)

Part of the advisory ``skill_surface_scan`` package; see its docstring for the
attribution note (categories inspired by NVIDIA SkillSpector, Apache-2.0; rules
re-implemented, no code or text copied).
"""

from __future__ import annotations

import ipaddress
import json
import re
from urllib.parse import urlsplit



def is_loopback(host: str) -> bool:
    """One loopback test for hooks and registry: exact name or a real loopback/unspecified IP."""
    host = host.strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.is_loopback or addr.is_unspecified


# Settings keys whose string value is executed as a shell command.
SHELL_STRING_KEYS = {"apiKeyHelper", "awsAuthRefresh", "awsCredentialExport", "otelHeadersHelper"}
# Settings keys whose value is {"type": "command", "command": "..."}.
SHELL_OBJECT_KEYS = {"statusLine", "fileSuggestion"}

_REMOTE_TOOL = re.compile(r"\b(?:nc|ncat|netcat|socat|scp|sftp|rsync)\b")
# hooks.json already gets a CRITICAL line check for these (prompt_injection_scan.scan_hooks_json);
# a hooks block inside settings*.json does not, so the settings path adds them here.
_NET_TOOL = re.compile(r"\b(?:curl|wget)\b|Invoke-(?:WebRequest|RestMethod)", re.IGNORECASE)
_REMOTE_TARGET = re.compile(
    r"(?:\b[\w.-]+@[\w.-]+\.[a-z]{2,}\b|\b\d{1,3}(?:\.\d{1,3}){3}\b|https?://[^\s\"']+|\b[\w-]+(?:\.[\w-]+)+:\S+)",
    re.IGNORECASE,
)


def _host_is_remote(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return bool(host) and not is_loopback(host)


def _target_is_remote(token: str) -> bool:
    """A URL / ``user@host`` / IPv4 / ``host:path`` token that is not loopback."""
    if token.lower().startswith("http"):
        return _host_is_remote(token)
    host = token.rsplit("@", 1)[-1]
    host = host.split(":", 1)[0] if host.count(":") == 1 else host
    return not is_loopback(host)


# `nc collector.example 4444` / `socat - TCP:host:4444`: the host is a bare argument, with no
# `user@` or `:port` shape for _REMOTE_TARGET to catch. A listener (`nc -l 4444`) has only digits.
_NETCAT_HOST = re.compile(r"\b(?:nc|ncat|netcat)\b(?:\s+-\S+)*\s+([A-Za-z0-9][\w.-]*)")
_SOCAT_HOST = re.compile(r"\b(?:TCP|UDP|SSL|OPENSSL)[46]?:([\w.-]+):\d+", re.IGNORECASE)


def _command_has_remote_peer(command: str) -> bool:
    """True when a network command names a non-loopback peer in any supported form."""
    if any(_target_is_remote(t) for t in _REMOTE_TARGET.findall(command)):
        return True
    hosts = [m.group(1) for m in _NETCAT_HOST.finditer(command) if not m.group(1).isdigit()]
    hosts += [m.group(1) for m in _SOCAT_HOST.finditer(command)]
    return any(_target_is_remote(host) for host in hosts)


def _line_of(text: str, needle: str) -> int | None:
    """1-based line of the first occurrence of ``needle`` (JSON parsing drops lines).

    The raw file holds the JSON-escaped form (``\\"``, ``\\\\``), so a parsed value with a quote
    or backslash — common in Windows commands — is searched in that form too.
    """
    escaped = json.dumps(needle)[1:-1]
    for line_no, raw in enumerate(text.splitlines(), 1):
        if needle in raw or escaped in raw:
            return line_no
    return None


def _walk(node):
    if isinstance(node, dict):
        yield node
        for child in node.values():
            yield from _walk(child)
    elif isinstance(node, list):
        for child in node:
            yield from _walk(child)


def _load(text: str):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError):
        return None


def scan_hooks(text: str, emit, data=None, include_net_tools: bool = False) -> None:
    """Flag hook handlers that send data to a remote host."""
    data = _load(text) if data is None else data
    if data is None:
        return
    for node in _walk(data):
        url = node.get("url") if node.get("type") == "http" else None
        if isinstance(url, str) and _host_is_remote(url):
            emit(
                "medium",
                "SURFACE_HOOK_REMOTE_SINK",
                f"Hook posts its event payload to a remote host ({url}). Hook events carry "
                f"prompts, file paths and tool output off the machine.",
                _line_of(text, url),
                "Point the hook at a bundled local script, or confirm the endpoint is yours.",
            )
        command = node.get("command")
        if (
            isinstance(command, str)
            and (_REMOTE_TOOL.search(command) or (include_net_tools and _NET_TOOL.search(command)))
            and _command_has_remote_peer(command)
        ):
            emit(
                "medium",
                "SURFACE_HOOK_REMOTE_SINK",
                "Hook command drives a network tool (nc, socat, scp, sftp, rsync, curl, wget) "
                "against a remote target, which can ship hook data off the machine.",
                _line_of(text, command[:40]),
                "Replace with a bundled local script, or confirm the destination.",
            )


def scan_settings(text: str, emit) -> None:
    """Flag shell-command settings keys, then reuse the hook checks on a ``hooks`` block."""
    data = _load(text)
    if not isinstance(data, dict):
        return
    for key in sorted(SHELL_STRING_KEYS & data.keys()):
        if isinstance(data[key], str) and data[key].strip():
            _flag_key(emit, text, key)
    for key in sorted(SHELL_OBJECT_KEYS & data.keys()):
        value = data[key]
        command = value.get("command") if isinstance(value, dict) else value
        if isinstance(command, str) and command.strip():
            _flag_key(emit, text, key)
    if isinstance(data.get("hooks"), (dict, list)):
        scan_hooks(text, emit, data=data["hooks"], include_net_tools=True)


def _flag_key(emit, text: str, key: str) -> None:
    emit(
        "medium",
        "SURFACE_SETTINGS_SHELL_KEY",
        f"Settings key '{key}' runs a shell command on its own once this file is active. "
        f"A committed or bundled settings file that sets it executes code on whoever opens the project.",
        _line_of(text, f'"{key}"'),
        "Review the command; remove the key from shared settings unless it is intentional.",
    )
