# Homecoming Build Stats — How-To Guide

## Directory layout

```
coh-slots/
├── assets/          Icon images (PNGs, WOFF2 font). Served via symlinks from webapp/static/.
├── data/            SQLite databases (runtime data, not in version control).
│   ├── archive.sqlite        Forum post archive — source of raw build text.
│   ├── attachment_cache.sqlite  Downloaded attachment files (survives pipeline resets).
│   ├── slots.sqlite          Parsed builds and aggregated stats — rebuilt by the pipeline. LOCAL ONLY.
│   ├── slots_deploy.sqlite   Trimmed deploy DB committed to git (~49 MB). Used by Cloudflare.
│   └── filter-json/          Pre-generated filter JSON files (committed). Used by Cloudflare Pages.
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
python scripts/fetch_attachments.py
python scripts/fetch_attachments.py --limit 50     # process at most 50 new files
python scripts/fetch_attachments.py --rate 2.0     # seconds between requests (default 1.0)
python scripts/fetch_attachments.py --dry-run      # enumerate links without downloading
python scripts/fetch_attachments.py --parse-only   # re-parse cached files, no network requests
```

## Importing local build files

To import a directory of local `.mbd` / `.mxd` / `.txt` build files (e.g. a
builder's personal archive) and attribute them to a named author:

```bash
python scripts/import_local_builds.py --dir data/submitted/Icesphere --author Icesphere
```

Files are attributed to `--author` with each file's modification time as
`posted_at`. Already-imported files (matched by filename hash) are skipped.
Run `pipeline aggregate` afterwards to include them in stats.

---

## Typical full refresh sequence

```bash
# 1. Re-scan and reaggregate (resets slots.sqlite)
python -m pipeline all

# 2. Re-inject attachment builds (always needed after a scan reset)
python scripts/fetch_attachments.py --parse-only

# 3. Re-inject local build files (if any)
python scripts/import_local_builds.py --dir data/submitted/Icesphere --author Icesphere
python scripts/import_local_builds.py --dir data/submitted/Maelwys --author Maelwys

# 4. Re-aggregate to include all builds in stats
python -m pipeline aggregate

# 5. (Optional) fetch and parse any newly posted attachments
python scripts/fetch_attachments.py

# 6. Start the webapp locally to verify
python -m webapp
```

> **Note:** `pipeline scan` resets `slots.sqlite`, which wipes attachment-sourced
> and locally-imported builds. Always run `fetch_attachments.py --parse-only`
> and any `import_local_builds.py` commands after a scan to restore them.

## Deploying to Cloudflare Pages

After a data refresh, regenerate the deploy DB and push:

```bash
python scripts/freeze.py       # rebuilds slots_deploy.sqlite + data/filter-json/ + build/
git add data/slots_deploy.sqlite data/filter-json/
git commit -m "refresh data"
git push
```

Cloudflare Pages picks up the push automatically and rebuilds the static site
using `python scripts/freeze.py` as the build command (configured in the
Cloudflare dashboard). Because `slots.sqlite` is not committed, on Cloudflare
the freeze script copies the pre-built `data/filter-json/` files into `build/`
instead of regenerating them. Both `slots_deploy.sqlite` and `data/filter-json/`
must be committed for the Cloudflare build to work.

The live site is at: https://cohstats.pages.dev

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
symlinks from `webapp/static/` by copying the real asset files in. It also
generates per-filter-combination JSON files for the author/year filter UI:

- When `slots.sqlite` is present: generates filter JSON from full data, writes
  copies to both `build/data/` and `data/filter-json/` (the committed cache).
- When `slots.sqlite` is absent (Cloudflare build): copies `data/filter-json/`
  into `build/data/` instead.

For Cloudflare Pages: build command is `python scripts/freeze.py`, build
output directory is `build/`. The `build/` directory is in `.gitignore` as
it is regenerated on each deploy. `slots_deploy.sqlite` (~49 MB) and
`data/filter-json/` are both committed to the repo so Cloudflare has data to
work from; `slots.sqlite` (314 MB) is not committed and stays local only.

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
