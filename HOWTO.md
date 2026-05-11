# Homecoming Build Stats — How-To Guide

## Directory layout

```
coh-slots/
├── assets/          Icon images (PNGs, WOFF2 font). Served via symlinks from webapp/static/.
├── data/            SQLite databases (runtime data, not in version control).
│   ├── archive.sqlite        Forum post archive — source of raw build text.
│   ├── attachment_cache.sqlite  Downloaded attachment files (survives pipeline resets).
│   └── slots.sqlite          Parsed builds and aggregated stats — rebuilt by the pipeline.
├── pipeline/        Backend package. Parses builds, aggregates stats.
├── refdata/         JSON reference files built from Mids data. Rebuilt by `pipeline refdata`.
├── scripts/         Standalone utility scripts.
├── webapp/          Flask frontend package.
└── HOWTO.md         This file.
```

---

## Prerequisites

```
pip install -r requirements.txt
```

All commands below should be run from the project root (`coh-slots/`).

---

## Running the web app

```bash
python -m webapp
```

Starts Flask on **http://127.0.0.1:5050** in debug mode. The server reloads
automatically when Python source files change; static files and templates take
effect immediately on refresh.

---

## Pipeline commands

The pipeline reads `data/archive.sqlite` and writes to `data/slots.sqlite`.
All subcommands are run as:

```bash
python -m pipeline <subcommand> [options]
```

### `refdata` — rebuild reference JSON

Parses the Mids data files (`I12.mhd`, `EnhDB.mhd`) and writes the JSON files
under `refdata/`. Run this when Mids data has been updated.

```bash
python -m pipeline refdata
```

The source files are read directly from the Mids Reborn installation:

```
~/bottles/Mids/drive_c/users/blw/AppData/Roaming/LoadedCamel/MidsReborn/Databases/Homecoming/
```

No copying or symlinking is needed — `refdata.py` reads from that path directly.

> **Warning:** MxDz-format builds use power static indices that are tied to the
> specific version of `I12.mhd` they were created with. Rebuilding refdata from
> a newer Mids installation shifts those indices and silently breaks all MxDz
> decoding — potentially losing thousands of builds. Only run `refdata` when you
> have a specific reason to update the Mids data, and verify MxDz build counts
> afterwards with `pipeline validate`.

### `scan` — parse forum posts into slots.sqlite

Reads every post in `archive.sqlite`, extracts builds in all supported formats
(MBD, MxDz, plain-text compact, plain-text long-form), deduplicates, and
writes to `slots.sqlite`. Resets `slots.sqlite` by default.

```bash
python -m pipeline scan              # full reset and scan
python -m pipeline scan --limit 500  # stop after 500 posts (for testing)
python -m pipeline scan --no-reset   # append to existing slots.sqlite
```

### `aggregate` — compute power statistics

Reads raw slotting rows from `slots.sqlite` and computes `power_stats`
(take rates, slot counts, top layouts, top enhancements). Run after `scan`.

```bash
python -m pipeline aggregate
```

### `validate` — coverage report

Prints a summary of parse rates, enhancement resolution, and the top N
unresolved enhancement names. Useful for spotting new sets that need mapping.

```bash
python -m pipeline validate           # top 20 unresolved
python -m pipeline validate --top 40  # show more
```

### `all` — standard pipeline run

Runs `scan` → `aggregate` → `validate` in sequence. Does **not** include
`refdata` — that must be run explicitly and deliberately (see warning below).

```bash
python -m pipeline all
python -m pipeline all --limit 1000   # test run
```

---

## Attachment downloader

Downloads `.mbd` / `.mxd` / `.txt` build files posted as forum attachments,
caches them in `data/attachment_cache.sqlite`, and injects them into
`slots.sqlite`. Run separately from the main pipeline, at most occasionally.
Idempotent — already-cached files are skipped.

```bash
cd scripts
python fetch_attachments.py
python fetch_attachments.py --limit 50     # process at most 50 new files
python fetch_attachments.py --rate 2.0     # seconds between requests (default 1.0)
python fetch_attachments.py --dry-run      # enumerate links without downloading
```

---

## Typical full refresh sequence

```bash
# 1. Re-scan and reaggregate (resets slots.sqlite)
python -m pipeline all

# 2. Re-inject attachment builds (always needed after a scan reset)
python scripts/fetch_attachments.py --parse-only

# 3. Re-aggregate to include attachment builds in stats
python -m pipeline aggregate

# 4. (Optional) fetch and parse any newly posted attachments
python scripts/fetch_attachments.py

# 5. Start the webapp
python -m webapp
```

> **Note:** `pipeline scan` resets `slots.sqlite`, which wipes attachment-sourced
> builds. Always run `fetch_attachments.py --parse-only` after a scan to restore
> them from the local cache (no network requests needed).

To rebuild reference data from Mids (only when deliberately updating Mids version — see warning above):

```bash
python -m pipeline refdata
python -m pipeline all
```

---

## Generating the static site

```bash
python scripts/freeze.py           # output to build/
python scripts/freeze.py --out DIR # output to a custom directory
```

This crawls all routes, writes HTML to `build/`, then resolves the icon
symlinks from `webapp/static/` by copying the real asset files in. The result
is a fully self-contained static site ready for deployment.

For Cloudflare Pages: set the build output directory to `build/` and the
build command to `python scripts/freeze.py`. The `build/` directory should
be in `.gitignore` as it is regenerated on each deploy.

## Adding or correcting icons

Icons are served from `webapp/static/` via symlinks into `assets/`:

| Static path        | Asset directory                  | Mapping module         |
|--------------------|----------------------------------|------------------------|
| `static/at/`       | `assets/ArchetypeIcons/`         | `webapp/at_icons.py`   |
| `static/ps/`       | `assets/Powersets/`              | `webapp/ps_icons.py`   |
| `static/enh/`      | `assets/Enhancements/`           | `webapp/enh_icons.py`  |
| `static/pwr-pool/` | `assets/Pool Powers/`            | `webapp/power_icons.py`|
| `static/pwr-patron/`| `assets/Patron Power Pools/`    | `webapp/power_icons.py`|

Each mapping module contains a `_MAP` dict (or auto-match logic) keyed by
display name. To add a missing icon: place the PNG in the appropriate `assets/`
subdirectory and add an entry to the relevant mapping module.

To find enhancements currently missing icons:

```bash
python -m pipeline validate --top 40
```

---

## Filtering unwanted powers

`pipeline/banned.py` contains `BANNED_DISPLAY_NAMES` — a set of power display
names that are excluded from all stats and display (form-shifts, ammo swaps,
unslottable temp powers such as Jaunt and Translocation). Add new entries here
when new auto-toggle or unslottable powers are introduced.
