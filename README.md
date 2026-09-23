<img src="./assets/curie-beehive-icon-512.png" alt="" width="72" align="right" />

# Curie plugins

The official Curie plugin for coding agents. One install per host, and your
agent can search your Curie library, read papers, write notes, and answer
comments without leaving the terminal it is already in.

## What the plugin contains

A skill, and nothing else. It tells your agent how to install the Curie CLI,
how to sign you in, and to run `curie skill` for the command manual. The manual
is printed by the CLI itself, so it always matches the version on the machine
and never goes stale in here.

No binary is committed to this repository and the plugin downloads nothing on
its own. The CLI is installed by the line Curie publishes at
<https://curie.is/cli/prompt.md>, from `downloads.curie.is`, and the installer
checks the published SHA-256 sum. Once installed, `curie` is on PATH and
`curie update` keeps working as usual.

## Install

| Host | Install, once per machine |
| --- | --- |
| Claude Code | `claude plugin marketplace add CurieSocial/curie-plugins` then `claude plugin install curie@curie-plugins`. In an open session, `/plugin marketplace add CurieSocial/curie-plugins`, `/plugin install curie@curie-plugins` and `/reload-plugins`. |
| Codex | `codex plugin marketplace add CurieSocial/curie-plugins` then `codex plugin add curie@curie-plugins`. In an open session, `/plugins`. |
| Grok Build | `grok plugin marketplace add CurieSocial/curie-plugins` then `grok plugin install curie --trust`. |
| Copilot CLI | `copilot plugin marketplace add CurieSocial/curie-plugins` then `copilot plugin install curie@curie-plugins`. |
| Gemini CLI | `gemini extensions install https://github.com/CurieSocial/curie-plugins`. |
| Cursor | No command line. Clone this repository and copy `plugins/curie` to `~/.cursor/plugins/local/curie`, then run **Developer: Reload Window**. Team and Enterprise admins can import this repository as a team marketplace instead. |
| Anything else | There is no plugin to install. Give your agent <https://curie.is/cli/prompt.md> and it will set Curie up by hand. |

In Claude Code, Codex, Grok Build and Copilot CLI these are ordinary shell
commands, so an agent with permission to run commands can install the plugin
itself.

## For a team

A repository can declare the marketplace, and Claude Code adds and enables it
for everyone who trusts the folder. In `.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "curie-plugins": {
      "source": { "source": "github", "repo": "CurieSocial/curie-plugins" }
    }
  },
  "enabledPlugins": { "curie@curie-plugins": true }
}
```

Codex workspace admins can import the marketplace with daily sync, and Copilot
CLI enterprises can push plugins to every client.

## What it runs, and what it reaches

- Runs `curl -fsSL https://downloads.curie.is/cli/install.sh | sh` once, if
  `curie` is not already installed, and then only `curie` commands.
- Reaches `downloads.curie.is` for the install and for updates, `curie.is` for
  the published instructions, and the Curie API for your library.
- Signs in through your browser or an email magic link. There is no token to
  paste and none is stored in this repository.

## Layout

```
plugins/curie/skills/curie/SKILL.md   the skill
plugins/curie/plugin.json             Agent Plugins 1.0, also read by Cursor
plugins/curie/.claude-plugin/         Claude Code
plugins/curie/.codex-plugin/          Codex
plugins/curie/.cursor-plugin/         Cursor
plugins/curie/.grok-plugin/           Grok Build
.claude-plugin/marketplace.json       Claude Code, and Copilot CLI's fallback
.github/plugin/marketplace.json       Copilot CLI's primary path
.agents/plugins/marketplace.json      Codex
.cursor-plugin/marketplace.json       Cursor team marketplaces
.grok-plugin/marketplace.json         Grok Build
plugin.json, skills/, gemini-extension.json
                                      the repository read as one plugin, which
                                      is what Gemini CLI installs
assets/                               the images, for the listings that ask
                                      for one by hand
```

The two copies of `SKILL.md` are kept identical by the check below.

## The icon

The plugin's mark is the beehive: the six-cell still life Curie's cellular
automata settles into, in Curie orange on Curie ink.

| File | Use |
| --- | --- |
| `assets/curie-beehive-icon-512.png` | the square tile a listing asks you to upload |
| `assets/curie-beehive-icon.svg` | the same tile, and the source the PNG is rendered from |
| `assets/curie-beehive.svg` | the mark on its own, transparent, inheriting `currentColor` |
| `assets/curie-logo.svg`, `assets/curie-logo-512.png` | the Curie app icon, for where the product is named rather than the plugin |

No manifest points at any of them, and none can: Claude Code refuses an `icon`
field, and the Agent Plugins 1.0 schema defines none and allows nothing extra.
Every host draws its own list from the name and description instead. The images
are here for the store submissions that take an upload, and for this page.

Do not redraw the beehive. The six cells sit on the automata's own 12px pitch,
and `curie-beehive.svg` is the copy everything else scales.

## Checks

```sh
python3 scripts/check_manifests.py
```

It proves every manifest agrees on the plugin name, version and description,
that the marketplaces point at `plugins/curie`, that both copies of the skill
are identical, that every `curie` command the skill names is one the CLI ships,
and that each image is the format and the size its filename claims. CI runs it,
along with `claude plugin validate ./plugins/curie`.

## Licence

MIT, see [LICENSE](./LICENSE). The Curie CLI is downloaded from
`downloads.curie.is` under its own terms and is not covered by this licence.
