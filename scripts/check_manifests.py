#!/usr/bin/env python3
"""Prove this repository says one thing, and that each host would accept it.

Every host reads a different manifest, so the plugin's name, version and
description are written out six times, and the marketplace five. This checks
they agree, that each one carries the fields its host reads, that every path
and URL they name resolves inside this repository, that every copy of a skill
is identical, and that every `curie` command a skill names is one the CLI
ships.

Two things are worth separating when reading a failure. Some checks come from
a host's own documentation, and a failure means that host would refuse the
plugin. The rest are this repository's own policy -- one plugin directory, one
hostname allowlist, the same metadata everywhere -- and a failure means we
contradicted ourselves, not that anything is broken.

It also runs the host validators that are installed. Claude Code and Grok
Build ship one; Codex does not, so nothing here proves Codex would load the
plugin, and a Codex failure would only ever show up in Codex.

    python3 scripts/check_manifests.py            # everything available
    python3 scripts/check_manifests.py --no-hosts # skip the host validators
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]

PLUGIN = "curie"
MARKETPLACE = "curie-plugins"
PLUGIN_DIR = "plugins/curie"
PLUGIN_SOURCE = f"./{PLUGIN_DIR}"

# Semver, so a prerelease or a build tag passes and 01.2.3 does not.
SEMVER = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][\w-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][\w-]*))*)?"
    r"(?:\+[\w-]+(?:\.[\w-]+)*)?$"
)

# What a plugin or marketplace may be called: lowercase letters, digits,
# hyphens and periods, up to 64, and no doubled separator.
NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")

AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

# How a marketplace entry may name where a plugin comes from. Ours is always
# the copy in this repository; the rest are here so a typo in the kind is
# caught rather than read as a new kind.
SOURCE_KINDS = {"local", "github", "git", "git-subdir", "npm", "url"}

# Codex reads a policy on every marketplace entry, and both values are closed
# sets. Ours says the plugin is installable and that signing in happens the
# first time the agent needs it, not while installing.
INSTALLATION_POLICY = {"NOT_AVAILABLE", "AVAILABLE", "INSTALLED_BY_DEFAULT"}
AUTHENTICATION_POLICY = {"ON_INSTALL", "ON_USE"}

# Our own ceiling for a skill description. Hosts allow more -- Claude Code
# allows 1,536 characters shared with when_to_use -- but a description this
# long has stopped being the one line that decides whether to read the skill.
DESCRIPTION_MAX = 1024

# Top-level commands the CLI ships, from `curie --help`. Refresh this list from
# https://curie.is/cli/commands when the CLI gains one; there is no
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

# Hosts we are allowed to fetch from. Anything else in a manifest or in a
# skill is a supply-chain question waiting to be asked.
ALLOWED_HOSTS = {"curie.is", "downloads.curie.is", "github.com", "agent-plugins.org"}

# Manifests that describe the plugin. Each host reads one of these.
PLUGIN_MANIFESTS = {
    "plugin.json": "agent-plugins",
    "plugins/curie/plugin.json": "agent-plugins",
    "plugins/curie/.claude-plugin/plugin.json": "claude",
    "plugins/curie/.codex-plugin/plugin.json": "codex",
    "plugins/curie/.cursor-plugin/plugin.json": "cursor",
    "plugins/curie/.grok-plugin/plugin.json": "grok",
}

# Manifests that describe the marketplace this repository is.
MARKETPLACE_MANIFESTS = {
    ".claude-plugin/marketplace.json": "claude",
    ".github/plugin/marketplace.json": "copilot",
    ".cursor-plugin/marketplace.json": "cursor",
    ".grok-plugin/marketplace.json": "grok",
    ".agents/plugins/marketplace.json": "codex",
}

# Every directory a host looks in for skills. The plugin's own copy is what a
# marketplace install reads; the one at the root is what Gemini reads, and
# what someone who clones the repository sees first.
SKILL_ROOTS = ("plugins/curie/skills", "skills")

# The images this repository ships. No manifest names them, and none can:
# Claude Code refuses an `icon` field under --strict, and the Agent Plugins 1.0
# schema closes the object and defines no icon either, so there is nowhere in a
# manifest to put one. They exist for the store submissions that ask for an
# image by hand, and for the README. That makes them exactly the kind of file
# that rots unnoticed, so each is checked against what its name claims.
#
# curie-beehive* is the plugin's own mark -- the six-cell still life the
# landing page's automata settles into. curie-logo* is the product's app icon.
ASSETS = (
    "assets/curie-beehive.svg",
    "assets/curie-beehive-icon.svg",
    "assets/curie-beehive-icon-512.png",
    "assets/curie-logo.svg",
    "assets/curie-logo-512.png",
)

OTHER_REQUIRED = [
    "gemini-extension.json",
    "README.md",
    "LICENSE",
    *ASSETS,
]

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
SVG_ROOT = "{http://www.w3.org/2000/svg}svg"

# What each host's own documentation says it reads. Only `name` is universally
# required; the rest are optional-and-displayed, and we write them everywhere
# so the plugin looks the same wherever it is installed from.
REQUIRED_PLUGIN_FIELDS = {
    "agent-plugins": ("$schema", "name", "version", "description"),
    "claude": ("name",),
    "codex": ("name", "interface"),
    "cursor": ("name",),
    "grok": ("name",),
}

REQUIRED_CODEX_INTERFACE = ("displayName", "shortDescription", "category")

# Fields we write into every plugin manifest, whether or not a host requires
# them, so that a person sees the same plugin in every list.
OUR_PLUGIN_FIELDS = ("name", "version", "description")

problems: list[str] = []
notes: list[str] = []

TYPES = {str: "a string", dict: "an object", list: "an array"}


def fail(message: str) -> None:
    problems.append(message)


def load(rel: str) -> dict | None:
    path = ROOT / rel
    if not path.exists():
        fail(f"{rel}: missing")
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        fail(f"{rel}: not valid JSON ({error})")
        return None
    if not isinstance(data, dict):
        fail(f"{rel}: the manifest must be an object")
        return None
    return data


def typed(rel: str, data: dict, key: str, kind: type, *, required: bool = True):
    """The value at `key`, once it is the type the host reads there."""
    if key not in data:
        if required:
            fail(f"{rel}: needs a {key}")
        return None
    value = data[key]
    if not isinstance(value, kind) or (kind is str and not value.strip()):
        fail(f"{rel}: {key} must be {TYPES[kind]}, and is {json.dumps(value)}")
        return None
    return value


def check_name(rel: str, what: str, value: str) -> None:
    if not NAME.match(value) or "--" in value or ".." in value:
        fail(
            f"{rel}: {what} {value!r} is not a name a host will take "
            "(lowercase letters, digits, - and ., up to 64)"
        )


def contained(rel: str, what: str, value: str, base: Path) -> Path | None:
    """A path a manifest names, resolved under the directory that owns it.

    Reading the resolved path is not enough: a check that strips "./" off the
    front turns "/skills/" and "../skills/" into the same thing and lets both
    through. So the written path is judged first, and the resolved one second.
    """
    if value.startswith(("/", "~")) or ".." in PurePosixPath(value).parts:
        fail(f"{rel}: {what} {value!r} must be a path inside the plugin")
        return None
    resolved = (base / value).resolve()
    root = base.resolve()
    if resolved != root and root not in resolved.parents:
        fail(f"{rel}: {what} {value!r} leaves the plugin directory")
        return None
    return resolved


def plugin_root(rel: str) -> Path:
    """The directory a plugin manifest speaks for.

    A host-specific manifest sits one level down in its own dotted directory,
    so the plugin is its grandparent; a portable one sits in the plugin
    directory itself.
    """
    directory = (ROOT / rel).parent
    return directory.parent if directory.name.startswith(".") else directory


def check_urls(rel: str, node: object) -> None:
    """Every URL a manifest names is https and points somewhere we own."""
    if isinstance(node, dict):
        for value in node.values():
            check_urls(rel, value)
    elif isinstance(node, list):
        for value in node:
            check_urls(rel, value)
    elif isinstance(node, str) and re.match(r"^https?://", node):
        if node.startswith("http://"):
            fail(f"{rel}: {node} is not https")
            return
        host = node.split("/")[2]
        if host not in ALLOWED_HOSTS:
            fail(f"{rel}: {node} is not a host this plugin should name")


def check_plugin_manifests() -> dict[str, str]:
    """Read every plugin manifest, and return the metadata they agree on."""
    seen: dict[str, set[str]] = {field: set() for field in OUR_PLUGIN_FIELDS}

    for rel, host in PLUGIN_MANIFESTS.items():
        data = load(rel)
        if data is None:
            continue
        check_urls(rel, data)

        for field in REQUIRED_PLUGIN_FIELDS[host]:
            kind = dict if field == "interface" else str
            typed(rel, data, field, kind)

        for field in OUR_PLUGIN_FIELDS:
            value = typed(rel, data, field, str)
            if value is not None:
                seen[field].add(value)

        name = data.get("name")
        if isinstance(name, str):
            check_name(rel, "plugin name", name)

        author = typed(rel, data, "author", dict, required=False)
        if author is not None:
            typed(f"{rel} author", author, "name", str)

        if host == "agent-plugins" and data.get("$schema") != AGENT_PLUGINS_SCHEMA:
            fail(
                f"{rel}: $schema is {data.get('$schema')!r}, and the only one "
                f"this repository writes is {AGENT_PLUGINS_SCHEMA}"
            )

        # Every host reads ./skills/ on its own, so this field is a pointer at
        # the place it would have looked anyway. It stays because it says out
        # loud where the skills are; it is checked rather than required.
        skills = data.get("skills")
        if isinstance(skills, str):
            resolved = contained(rel, "skills path", skills, plugin_root(rel))
            if resolved is not None and not resolved.is_dir():
                fail(f"{rel}: skills path {skills!r} is not a directory")
        elif skills is not None:
            fail(f"{rel}: skills must be a string, and is {json.dumps(skills)}")

        if not (plugin_root(rel) / "skills").is_dir():
            fail(f"{rel}: the host reads ./skills/ beside it, which is not here")

        interface = data.get("interface")
        if host == "codex" and isinstance(interface, dict):
            for field in REQUIRED_CODEX_INTERFACE:
                typed(f"{rel} interface", interface, field, str)
            for field in ("capabilities", "defaultPrompt"):
                values = typed(f"{rel} interface", interface, field, list, required=False)
                if values is not None and not all(isinstance(v, str) for v in values):
                    fail(f"{rel}: every {field} entry must be a string")

    for field in OUR_PLUGIN_FIELDS:
        if len(seen[field]) > 1:
            fail(f"plugin {field} disagrees across manifests: {sorted(seen[field])}")

    agreed = {field: next(iter(seen[field]), "") for field in OUR_PLUGIN_FIELDS}

    if agreed["name"] and agreed["name"] != PLUGIN:
        fail(f"plugin name is {agreed['name']!r}, not {PLUGIN!r}")
    if agreed["version"] and not SEMVER.match(agreed["version"]):
        fail(f"plugin version {agreed['version']!r} is not a semver")

    return agreed


def check_source(rel: str, entry: dict) -> None:
    """Where the marketplace entry says the plugin is, and whether it is."""
    source = entry.get("source")
    if isinstance(source, str):
        path = source
    elif isinstance(source, dict):
        kinds = [source[key] for key in ("source", "type") if key in source]
        if len(kinds) != 1 or kinds[0] not in SOURCE_KINDS:
            fail(f"{rel}: the source names no kind a host knows: {json.dumps(source)}")
        path = typed(f"{rel} source", source, "path", str)
        if path is None:
            return
    else:
        fail(f"{rel}: the plugin entry needs a source")
        return

    if path != PLUGIN_SOURCE:
        fail(f"{rel}: plugin source is {path!r}, not {PLUGIN_SOURCE!r}")
    elif not (ROOT / PLUGIN_DIR).is_dir():
        fail(f"{rel}: plugin source {path!r} does not exist")


def check_marketplace_manifests(plugin: dict[str, str]) -> None:
    for rel, host in MARKETPLACE_MANIFESTS.items():
        data = load(rel)
        if data is None:
            continue
        check_urls(rel, data)

        name = typed(rel, data, "name", str)
        if name is not None:
            check_name(rel, "marketplace name", name)
            if name != MARKETPLACE:
                fail(f"{rel}: marketplace is {name!r}, not {MARKETPLACE!r}")

        # Codex carries the marketplace's label inside interface instead.
        if host == "codex":
            interface = typed(rel, data, "interface", dict)
            if interface is not None:
                typed(f"{rel} interface", interface, "displayName", str)
        else:
            owner = typed(rel, data, "owner", dict)
            if owner is not None:
                typed(f"{rel} owner", owner, "name", str)

        plugins = typed(rel, data, "plugins", list)
        if not plugins:
            if plugins is not None:
                fail(f"{rel}: no plugins listed")
            continue

        names = [p.get("name") for p in plugins if isinstance(p, dict)]
        if names != [PLUGIN]:
            fail(f"{rel}: lists {names}, expected [{PLUGIN!r}]")

        for entry in plugins:
            if not isinstance(entry, dict):
                fail(f"{rel}: a plugin entry is not an object")
                continue
            check_source(rel, entry)

            if host == "codex":
                policy = typed(f"{rel} entry", entry, "policy", dict)
                if policy is not None:
                    for field, allowed in (
                        ("installation", INSTALLATION_POLICY),
                        ("authentication", AUTHENTICATION_POLICY),
                    ):
                        value = typed(f"{rel} policy", policy, field, str)
                        if value is not None and value not in allowed:
                            fail(
                                f"{rel}: policy {field} is {value!r}, "
                                f"and Codex reads one of {sorted(allowed)}"
                            )
                typed(f"{rel} entry", entry, "category", str)
                continue

            # A relative source means the host reads this entry as well as the
            # plugin's own manifest, and the entry wins. Two places to bump,
            # so they are checked against each other rather than trusted.
            for field in ("description", "version"):
                value = typed(f"{rel} entry", entry, field, str)
                if value is not None and plugin[field] and value != plugin[field]:
                    fail(
                        f"{rel}: the entry's {field} is {value!r}, and it "
                        f"overrides plugin.json, which says {plugin[field]!r}"
                    )


def check_gemini(plugin: dict[str, str]) -> None:
    gemini = load("gemini-extension.json")
    if gemini is None:
        return
    check_urls("gemini-extension.json", gemini)
    for field in OUR_PLUGIN_FIELDS:
        value = typed("gemini-extension.json", gemini, field, str)
        if value is not None and plugin[field] and value != plugin[field]:
            fail(
                f"gemini-extension.json {field} is {value!r}, "
                f"and plugin.json says {plugin[field]!r}"
            )


def frontmatter(rel: str, text: str) -> dict[str, str] | None:
    """The frontmatter, and whether a strict host could read it.

    Claude Code and Grok Build both accept frontmatter that is not valid YAML,
    so their validators pass a file another host would refuse. A description
    holding a colon and a space is the way it happens: unquoted, that is a
    mapping inside a mapping, and a strict parser stops there.
    """
    if not text.startswith("---\n"):
        fail(f"{rel}: no frontmatter")
        return None
    end = text.find("\n---", 3)
    if end == -1:
        fail(f"{rel}: the frontmatter is never closed")
        return None

    block = text[4:end]
    fields: dict[str, str] = {}
    for line in block.splitlines():
        match = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        fields[key] = value
        quoted = len(value) > 1 and value[0] == value[-1] and value[0] in "\"'"
        if quoted:
            continue
        if ": " in value or value.endswith(":"):
            fail(f"{rel}: the {key} holds a colon and is not quoted, which is not valid YAML")
        if value[:1] in "[{*&!|>%@`#":
            fail(f"{rel}: the {key} starts with {value[0]!r}, which YAML reads as syntax; quote it")
        if " #" in value:
            fail(f"{rel}: the {key} holds ' #', which YAML reads as a comment")

    try:
        import yaml  # noqa: PLC0415 - optional, and only for a stricter read
    except ImportError:
        notes.append("PyYAML: not installed, frontmatter checked by rule only")
        return fields

    try:
        parsed = yaml.safe_load(block)
    except yaml.YAMLError as error:
        fail(f"{rel}: the frontmatter is not valid YAML ({error.args[0]})")
        return fields
    if not isinstance(parsed, dict):
        fail(f"{rel}: the frontmatter is not a mapping")
    return fields


def check_skill(rel: str, directory: str, text: str) -> None:
    fields = frontmatter(rel, text)
    if fields is not None:
        name = fields.get("name")
        if name != directory:
            fail(f"{rel}: frontmatter name is {name!r}, and the directory is {directory!r}")
        description = fields.get("description", "")
        if not description:
            fail(f"{rel}: frontmatter has no description")
        elif len(description) > DESCRIPTION_MAX:
            fail(f"{rel}: the description is over {DESCRIPTION_MAX} characters")

    for block in re.findall(r"```(?:sh|bash|console)?\n(.*?)```", text, re.S):
        for raw in block.splitlines():
            line = raw.strip()
            if not line.startswith("curie"):
                continue
            words = line.split()
            if len(words) < 2:
                fail(f"{rel}: `{line}` names no command")
                continue
            word = words[1]
            if word.startswith("-"):
                continue
            if word not in CLI_COMMANDS:
                fail(f"{rel}: `{line}` is not a command the CLI ships")

    for url in re.findall(r"https?://[^\s)>\"']+", text):
        if url.startswith("http://"):
            fail(f"{rel}: {url} is not https")
            continue
        host = url.split("/")[2]
        if host not in ALLOWED_HOSTS:
            fail(f"{rel}: {url} is not a host this plugin should name")


def check_skills() -> None:
    """Every skill in every place a host looks, and all copies the same."""
    copies: dict[str, dict[str, str]] = {}

    for root_rel in SKILL_ROOTS:
        root = ROOT / root_rel
        if not root.is_dir():
            fail(f"{root_rel}: missing, and a host reads skills there")
            continue
        directories = sorted(path for path in root.iterdir() if path.is_dir())
        if not directories:
            fail(f"{root_rel}: holds no skill")
        for directory in directories:
            if not NAME.match(directory.name):
                fail(f"{root_rel}/{directory.name}: not a name a host will take")
            skill = directory / "SKILL.md"
            rel = f"{root_rel}/{directory.name}/SKILL.md"
            if not skill.exists():
                fail(f"{rel}: missing")
                continue
            copies.setdefault(directory.name, {})[rel] = skill.read_text()

    for name, found in sorted(copies.items()):
        if len(found) != len(SKILL_ROOTS):
            fail(f"the {name} skill is in {sorted(found)}, and not in every skills directory")
        if len(set(found.values())) > 1:
            fail(f"the copies of {name}/SKILL.md differ; they must be byte-identical")
        rel, text = sorted(found.items())[0]
        check_skill(rel, name, text)


def check_required_files() -> None:
    for rel in OTHER_REQUIRED:
        if not (ROOT / rel).exists():
            fail(f"{rel}: missing")


def check_assets() -> None:
    """Each image is the format, and the size, its filename claims.

    A store form takes whatever it is handed, and a README renders a broken
    image without complaining, so nothing downstream would catch a truncated
    export or a file that kept its name through a resize. This does.
    """
    for rel in ASSETS:
        path = ROOT / rel
        if not path.exists():
            continue  # check_required_files has already said so.
        data = path.read_bytes()
        if not data:
            fail(f"{rel}: empty")
            continue

        if rel.endswith(".svg"):
            try:
                root = ElementTree.fromstring(data)
            except ElementTree.ParseError as error:
                fail(f"{rel}: not valid XML ({error})")
                continue
            if root.tag != SVG_ROOT:
                fail(f"{rel}: the root element is {root.tag!r}, not an <svg>")
            continue

        if data[:8] != PNG_MAGIC:
            fail(f"{rel}: not a PNG")
            continue
        # IHDR is always the first chunk, so the width and height are the two
        # big-endian words after the signature, the length and the type.
        width, height = struct.unpack(">II", data[16:24])
        claimed = re.search(r"-(\d+)\.png$", rel)
        if claimed and (width, height) != (int(claimed.group(1)),) * 2:
            fail(
                f"{rel}: the name says {claimed.group(1)} square, and the "
                f"file is {width}x{height}"
            )


def run_host_validators() -> None:
    """Ask each installed host to accept the manifests it reads.

    Both are run strictly, so a field neither host recognises is an error here
    rather than a warning someone has to notice.
    """
    checks = [
        ("claude plugin", ["claude", "plugin", "validate", "--strict", str(ROOT / PLUGIN_DIR)]),
        ("claude marketplace", ["claude", "plugin", "validate", "--strict", str(ROOT)]),
        ("grok plugin", ["grok", "plugin", "validate", str(ROOT / PLUGIN_DIR)]),
    ]
    for label, argv in checks:
        if shutil.which(argv[0]) is None:
            notes.append(f"{label}: not installed, skipped")
            continue
        result = subprocess.run(argv, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip().splitlines()
            tail = output[-1] if output else f"exit {result.returncode}"
            fail(f"{label} rejected the manifest: {tail}")
        else:
            notes.append(f"{label}: accepted")
    notes.append("codex: ships no validator, so nothing here speaks for Codex")


def main(argv: list[str]) -> int:
    plugin = check_plugin_manifests()
    check_marketplace_manifests(plugin)
    check_gemini(plugin)
    check_skills()
    check_required_files()
    check_assets()
    if "--no-hosts" not in argv:
        run_host_validators()

    for note in notes:
        print(f"  {note}")

    if problems:
        print("\nThe manifests do not agree:\n")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print(
        f"\nOK: {plugin['name']} {plugin['version']} agrees across "
        f"{len(PLUGIN_MANIFESTS)} plugin manifests and "
        f"{len(MARKETPLACE_MANIFESTS)} marketplaces."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
