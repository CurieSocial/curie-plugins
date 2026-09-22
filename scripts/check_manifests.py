#!/usr/bin/env python3
"""Prove this repository says one thing.

Every host reads a different manifest, so the same plugin name, version and
description are written out seven times. This checks they agree, that the
marketplaces point at the plugin, that both copies of the skill are identical,
and that every `curie` command the skill names is one the CLI ships.

    python3 scripts/check_manifests.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PLUGIN = "curie"
MARKETPLACE = "curie-plugins"
PLUGIN_DIR = "plugins/curie"

# Top-level commands the CLI ships, from `curie --help`. Refresh this list from
# https://curie.is/cli/commands when the CLI adds one; there is no
# machine-readable index to read instead.
CLI_COMMANDS = {
    "collection",
    "comment",
    "env",
    "feed",
    "file",
    "label",
    "login",
    "logout",
    "note",
    "search",
    "skill",
    "status",
    "update",
    "upload",
    "whoami",
}

# Manifests that describe the plugin itself.
PLUGIN_MANIFESTS = [
    "plugin.json",
    "plugins/curie/plugin.json",
    "plugins/curie/.claude-plugin/plugin.json",
    "plugins/curie/.codex-plugin/plugin.json",
    "plugins/curie/.cursor-plugin/plugin.json",
    "plugins/curie/.grok-plugin/plugin.json",
]

# Manifests that describe the marketplace this repository is.
MARKETPLACE_MANIFESTS = [
    ".claude-plugin/marketplace.json",
    ".github/plugin/marketplace.json",
    ".cursor-plugin/marketplace.json",
    ".grok-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
]

SKILLS = [
    "plugins/curie/skills/curie/SKILL.md",
    "skills/curie/SKILL.md",
]

OTHER_REQUIRED = [
    "gemini-extension.json",
    "README.md",
    "LICENSE",
]

problems: list[str] = []


def fail(message: str) -> None:
    problems.append(message)


def load(rel: str):
    path = ROOT / rel
    if not path.exists():
        fail(f"{rel}: missing")
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        fail(f"{rel}: not valid JSON ({error})")
        return None


def check_plugin_manifests() -> None:
    seen: dict[str, set[str]] = {"name": set(), "version": set(), "description": set()}
    for rel in PLUGIN_MANIFESTS:
        data = load(rel)
        if data is None:
            continue
        for field in seen:
            value = data.get(field)
            if value is None:
                fail(f"{rel}: no {field}")
            else:
                seen[field].add(value)
    if seen["name"] and seen["name"] != {PLUGIN}:
        fail(f"plugin name disagrees across manifests: {sorted(seen['name'])}")
    for field in ("version", "description"):
        if len(seen[field]) > 1:
            fail(f"plugin {field} disagrees across manifests: {sorted(seen[field])}")


def source_path(entry: dict) -> str | None:
    source = entry.get("source")
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        return source.get("path")
    return None


def check_marketplace_manifests() -> None:
    for rel in MARKETPLACE_MANIFESTS:
        data = load(rel)
        if data is None:
            continue
        if data.get("name") != MARKETPLACE:
            fail(f"{rel}: marketplace name is {data.get('name')!r}, not {MARKETPLACE!r}")
        plugins = data.get("plugins")
        if not isinstance(plugins, list) or not plugins:
            fail(f"{rel}: no plugins listed")
            continue
        names = [p.get("name") for p in plugins]
        if names != [PLUGIN]:
            fail(f"{rel}: lists {names}, expected [{PLUGIN!r}]")
        for entry in plugins:
            path = source_path(entry)
            if path not in (f"./{PLUGIN_DIR}", PLUGIN_DIR):
                fail(f"{rel}: plugin source is {path!r}, not './{PLUGIN_DIR}'")


def check_versions_match_gemini() -> None:
    plugin = load("plugin.json") or {}
    gemini = load("gemini-extension.json") or {}
    for field in ("name", "version", "description"):
        if plugin.get(field) != gemini.get(field):
            fail(
                f"gemini-extension.json {field} is {gemini.get(field)!r}, "
                f"plugin.json says {plugin.get(field)!r}"
            )


def check_skill_copies() -> str | None:
    texts = {}
    for rel in SKILLS:
        path = ROOT / rel
        if not path.exists():
            fail(f"{rel}: missing")
            continue
        texts[rel] = path.read_text()
    if len(texts) == len(SKILLS) and len(set(texts.values())) > 1:
        fail("the two copies of SKILL.md differ; they must be byte-identical")
    return next(iter(texts.values()), None)


def check_skill_body(text: str | None) -> None:
    if text is None:
        return
    if not text.startswith("---\n"):
        fail("SKILL.md: no frontmatter")
        return
    end = text.find("\n---", 3)
    front = text[4:end] if end != -1 else ""
    if not re.search(rf"^name:\s*{PLUGIN}\s*$", front, re.M):
        fail(f"SKILL.md: frontmatter name is not {PLUGIN!r}")
    if not re.search(r"^description:\s*\S", front, re.M):
        fail("SKILL.md: frontmatter has no description")

    for block in re.findall(r"```(?:sh|bash|console)?\n(.*?)```", text, re.S):
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("curie "):
                continue
            word = line.split()[1]
            if word.startswith("-"):
                continue
            if word not in CLI_COMMANDS:
                fail(f"SKILL.md: `{line}` is not a command the CLI ships")


def check_required_files() -> None:
    for rel in OTHER_REQUIRED:
        if not (ROOT / rel).exists():
            fail(f"{rel}: missing")


def main() -> int:
    check_plugin_manifests()
    check_marketplace_manifests()
    check_versions_match_gemini()
    check_skill_body(check_skill_copies())
    check_required_files()

    if problems:
        print("The manifests do not agree:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    plugin = load("plugin.json") or {}
    print(
        f"OK: {plugin.get('name')} {plugin.get('version')} agrees across "
        f"{len(PLUGIN_MANIFESTS)} plugin manifests and "
        f"{len(MARKETPLACE_MANIFESTS)} marketplaces."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
