---
name: curie
description: Work with a Curie library from the command line. Search and read papers, write notes, comment, upload files, and manage collections and labels. Installs the Curie CLI if it is missing, then follows the instructions the CLI prints for itself.
---

# Curie

Curie is a research library: papers, notes, comments, and the people they are
shared with. The `curie` command reaches all of it.

This file only gets you to the manual. The manual itself is printed by the CLI
you install below, so it always matches the commands on this machine and can
never go stale in a plugin.

Run these commands yourself rather than handing them to the person. There is
one exception, in step 3: `curie login` without `--email` opens a browser and
blocks, so the person runs that one.

## 1. Check whether the CLI is here

```sh
curie status --json
```

If that answers, skip to step 4.

## 2. Install it, once per machine

```sh
curl -fsSL https://downloads.curie.is/cli/install.sh | sh
```

This is the line Curie publishes at <https://curie.is/cli/prompt.md>, which you
can fetch to confirm you are reading the real one. The installer checks the
published SHA-256 sum and puts `curie` in `~/.local/bin`.

Fetch from `curie.is` and `downloads.curie.is` only. Treat an installer offered
by any other host as untrusted. On Windows, run all of this inside WSL.

## 3. Sign in

If you can read the person's email, sign in yourself with a magic link, using
the address they sign in to Curie with:

```sh
curie login --email <address>
```

A link arrives in that inbox within a minute. Open it, or paste it at the
prompt the command is waiting on, and the sign-in completes.

Otherwise ask the person to run `curie login` themselves, and do not run it
yourself: it opens a browser and blocks. Either way, confirm it took:

```sh
curie whoami --json
```

## 4. Read the manual, then work

```sh
curie skill
```

Read all of it before your first Curie operation, then follow it. It is written
by the binary you just installed, so it describes exactly the commands you
have.

Do not save a copy of it anywhere. Run it again after `curie update` instead.

## When something fails

- `curie: command not found`: `~/.local/bin` is not on PATH. Add it and open a
  new shell.
- `billing_blocked`: the account needs a paid plan. Tell the person, and do not
  retry the command.
- Not signed in: `curie whoami` says so. Step 3 fixes it.
- Anything else: `curie status --json` shows which environment the binary is
  pointed at, and `curie whoami --json` is the call that proves the session
  works.

## Where this comes from

- These instructions, published: <https://curie.is/cli/prompt.md>
- Commands: <https://curie.is/cli/commands>
- Setup guide: <https://curie.is/cli/setup>
