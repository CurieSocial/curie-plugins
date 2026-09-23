#!/usr/bin/env python3
"""Break one thing at a time, and check the gate says so.

A checker nobody checks is a green tick, not a guarantee. Each case here is a
mistake a host would punish us for -- a description that is not valid YAML, a
path that climbs out of the plugin, a version two files disagree on -- applied
to a throwaway copy of the repository. The gate has to refuse every one.

    python3 scripts/check_manifests_test.py
"""

from __future__ import annotations

import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def edit_json(root: pathlib.Path, rel: str, change) -> None:
    path = root / rel
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


def unquoted_colon(root: pathlib.Path) -> None:
    """The defect that started this: valid to two hosts, invalid YAML to all."""
    for rel in ("skills/curie/SKILL.md", "plugins/curie/skills/curie/SKILL.md"):
        path = root / rel
        path.write_text(
            path.read_text().replace(
                "from the command line.", "from the command line: like this,", 1
            )
        )


def png(width: int, height: int) -> bytes:
    """A real, if tiny, PNG -- so the gate is refusing the size, not the file."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def second_skill(root: pathlib.Path) -> None:
    (root / "skills" / "curie-extra").mkdir()
    (root / "skills" / "curie-extra" / "SKILL.md").write_text(
        "---\nname: curie-extra\ndescription: a skill in one place only\n---\n"
    )


CASES = {
    "an unquoted colon in the skill description": unquoted_colon,
    "a $schema nobody publishes": lambda r: edit_json(
        r, "plugin.json", lambda d: d.__setitem__("$schema", "https://curie.is/x.json")
    ),
    "a marketplace entry that overrides the version": lambda r: edit_json(
        r,
        ".claude-plugin/marketplace.json",
        lambda d: d["plugins"][0].__setitem__("version", "9.9.9"),
    ),
    "a skills path that climbs out": lambda r: edit_json(
        r,
        "plugins/curie/.claude-plugin/plugin.json",
        lambda d: d.__setitem__("skills", "../../skills/"),
    ),
    "a skills path that starts at the root": lambda r: edit_json(
        r,
        "plugins/curie/.claude-plugin/plugin.json",
        lambda d: d.__setitem__("skills", "/skills/"),
    ),
    "a name that is a number": lambda r: edit_json(
        r, "plugins/curie/.grok-plugin/plugin.json", lambda d: d.__setitem__("name", 7)
    ),
    "a name with a capital letter": lambda r: edit_json(
        r,
        "plugins/curie/.grok-plugin/plugin.json",
        lambda d: d.__setitem__("name", "Curie"),
    ),
    "a policy value Codex does not read": lambda r: edit_json(
        r,
        ".agents/plugins/marketplace.json",
        lambda d: d["plugins"][0]["policy"].__setitem__("authentication", "LATER"),
    ),
    "a source kind nobody knows": lambda r: edit_json(
        r,
        ".grok-plugin/marketplace.json",
        lambda d: d["plugins"][0]["source"].__setitem__("type", "tarball"),
    ),
    "a source that drops the ./": lambda r: edit_json(
        r,
        ".claude-plugin/marketplace.json",
        lambda d: d["plugins"][0].__setitem__("source", "plugins/curie"),
    ),
    "an interface that is a string": lambda r: edit_json(
        r,
        "plugins/curie/.codex-plugin/plugin.json",
        lambda d: d.__setitem__("interface", "Curie"),
    ),
    "a version with a leading zero": lambda r: edit_json(
        r, "plugin.json", lambda d: d.__setitem__("version", "01.2.3")
    ),
    "a skill that is in one skills directory only": second_skill,
    "an icon that kept its name through a resize": lambda r: (
        r / "assets/curie-beehive-icon-512.png"
    ).write_bytes(png(256, 256)),
    "an icon that is a PNG under an .svg name": lambda r: (
        r / "assets/curie-beehive.svg"
    ).write_bytes(png(8, 8)),
    "an icon that exported as nothing": lambda r: (
        r / "assets/curie-logo-512.png"
    ).write_bytes(b""),
}


def main() -> int:
    missed: list[str] = []
    for label, mutate in CASES.items():
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "repo"
            shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git"))
            mutate(root)
            run = subprocess.run(
                [sys.executable, str(root / "scripts/check_manifests.py"), "--no-hosts"],
                capture_output=True,
                text=True,
            )
            said = next(
                (line.strip(" -") for line in run.stdout.splitlines() if line.startswith("  - ")),
                "",
            )
            if run.returncode == 0:
                missed.append(label)
                print(f"  MISSED  {label}")
            else:
                print(f"  caught  {label}\n            {said}")

    if missed:
        print(f"\n{len(missed)} of {len(CASES)} got past the gate.")
        return 1
    print(f"\nOK: the gate refused all {len(CASES)} broken repositories.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
