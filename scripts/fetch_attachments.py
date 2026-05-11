"""
One-shot downloader for build attachments posted on the Homecoming forums.

Forum posts link to .mbd / .mxd / .txt build files hosted on the forum server.
This script:
  1. Enumerates all such links from archive.sqlite (deduplicated by file_id).
  2. Downloads new files to attachment_cache.sqlite (survives slots.sqlite rebuilds).
  3. Parses each cached file and inserts builds into slots.sqlite.

Run this independently of the standard pipeline, at most occasionally:

    python fetch_attachments.py [--rate SECONDS] [--limit N] [--dry-run]

Idempotent: files already in the cache are not re-downloaded; builds already
in slots.sqlite (matched by signature) are silently skipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

import sys
sys.path.insert(0, str(PROJECT_ROOT))

ARCHIVE_DB   = PROJECT_ROOT / "data" / "archive.sqlite"
SLOTS_DB     = PROJECT_ROOT / "data" / "slots.sqlite"
CACHE_DB     = PROJECT_ROOT / "data" / "attachment_cache.sqlite"

TARGET_EXTS = {"mbd", "mxd", "txt"}
DEFAULT_RATE = 0.5   # seconds between requests


# ── cache schema ─────────────────────────────────────────────────────────────

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS attachment (
    file_id     INTEGER PRIMARY KEY,
    post_id     INTEGER NOT NULL,    -- earliest post that linked this file
    ext         TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    http_status INTEGER,
    content     BLOB,                -- NULL if fetch failed
    fetched_at  TEXT
);
"""


def open_cache() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CACHE_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript(CACHE_SCHEMA)
    conn.commit()
    return conn


# ── enumerate attachment links ────────────────────────────────────────────────

_ATTACH_RE = re.compile(
    r'<a\s[^>]*class="ipsAttachLink"[^>]*>',
    re.IGNORECASE,
)
_HREF_RE     = re.compile(r'href="([^"]+)"')
_FILEID_RE   = re.compile(r'[?&]id=(\d+)')
_FILEEXT_RE  = re.compile(r'data-fileext="([^"]+)"', re.IGNORECASE)


def _parse_links(body_html: str) -> list[tuple[int, str, str]]:
    """Return [(file_id, ext, url), ...] for every build attachment tag."""
    out = []
    for m in _ATTACH_RE.finditer(body_html):
        tag = m.group(0)
        href_m = _HREF_RE.search(tag)
        id_m   = _FILEID_RE.search(tag)
        ext_m  = _FILEEXT_RE.search(tag)
        if not (href_m and id_m and ext_m):
            continue
        ext = ext_m.group(1).lower()
        if ext not in TARGET_EXTS:
            continue
        url = href_m.group(1).replace("&amp;", "&")
        file_id = int(id_m.group(1))
        out.append((file_id, ext, url))
    return out


def enumerate_links(archive: sqlite3.Connection) -> dict[int, dict]:
    """
    Scan archive.sqlite for all attachment links.  Returns a dict keyed by
    file_id; value has the earliest post_id, ext, and url.
    """
    files: dict[int, dict] = {}
    rows = archive.execute(
        "SELECT post_id, body_html FROM posts WHERE body_html LIKE '%ipsAttachLink%'"
    ).fetchall()
    for row in rows:
        for file_id, ext, url in _parse_links(row["body_html"]):
            if file_id not in files or row["post_id"] < files[file_id]["post_id"]:
                files[file_id] = {"post_id": row["post_id"], "ext": ext, "url": url}
    return files


# ── fetch ─────────────────────────────────────────────────────────────────────

_HEADERS = {"User-Agent": "coh-slots-research/1.0 (build stats; contact via HC forums)"}


def fetch_one(url: str) -> tuple[int, bytes | None]:
    """Return (http_status, content_bytes_or_None)."""
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return 0, None


def download_missing(cache: sqlite3.Connection, files: dict[int, dict],
                     rate: float, limit: int | None, dry_run: bool) -> int:
    """Download files not yet in cache. Returns count of new fetches attempted."""
    cached_ids = {r[0] for r in cache.execute("SELECT file_id FROM attachment").fetchall()}
    pending = [(fid, info) for fid, info in files.items() if fid not in cached_ids]
    if limit:
        pending = pending[:limit]

    print(f"  {len(cached_ids)} already cached, {len(pending)} to fetch")
    if dry_run:
        for fid, info in pending[:5]:
            print(f"    [dry-run] would fetch file_id={fid} ext={info['ext']} {info['url'][:80]}")
        return 0

    n_ok = n_fail = 0
    for i, (fid, info) in enumerate(pending):
        status, content = fetch_one(info["url"])
        ok = content is not None
        cache.execute(
            "INSERT OR REPLACE INTO attachment (file_id, post_id, ext, url, http_status, content, fetched_at) "
            "VALUES (?,?,?,?,?,?,datetime('now'))",
            (fid, info["post_id"], info["ext"], info["url"], status, content),
        )
        if (i + 1) % 50 == 0:
            cache.commit()
            print(f"    {i+1}/{len(pending)} fetched ({n_ok} ok, {n_fail} failed)")
        if ok:
            n_ok += 1
        else:
            n_fail += 1
        if i + 1 < len(pending):
            time.sleep(rate)

    cache.commit()
    print(f"  Fetched {len(pending)}: {n_ok} ok, {n_fail} failed")
    return len(pending)


# ── parse & insert ────────────────────────────────────────────────────────────

def _parse_mbd_file(refdata, post_id: int, content: bytes):
    """Parse a raw .mbd JSON file (not the base64+brotli inline variant)."""
    from pipeline.extractors.mbd import _classify_powersets, _slot_enh_from_uid
    from pipeline.extractors.common import BuildRecord, PowerSlotting
    from pipeline.banned import is_banned

    try:
        data = json.loads(content)
    except Exception:
        return None

    archetype = refdata.archetype_map.get(data.get("Class", ""), data.get("Class"))
    record = BuildRecord(
        post_id=post_id, block_index=0, source_format="MBD",
        archetype=archetype,
    )
    ps_list = data.get("PowerSets") or []
    record.primary_set, record.secondary_set, record.epic_set = _classify_powersets(
        refdata, archetype, ps_list
    )
    for pe in data.get("PowerEntries") or []:
        full_name = pe.get("PowerName")
        if not full_name:
            continue
        disp = refdata.powers_index.get(full_name, {}).get("display_name", "")
        if is_banned(disp):
            continue
        enhancements = []
        for se in pe.get("SlotEntries") or []:
            enh_obj = se.get("Enhancement") if se else None
            if not enh_obj:
                continue
            slot_enh = _slot_enh_from_uid(refdata, enh_obj.get("Uid"), enh_obj.get("IoLevel"))
            if slot_enh is not None:
                enhancements.append(slot_enh)
        if enhancements:
            record.powers.append(PowerSlotting(power_full_name=full_name, enhancements=enhancements))
    return record if record.powers else None


# Saved .mxd files separate the power name from its enhancements with 2+ tabs
# rather than the ' -- ' used in pasted inline text.  Normalise before parsing.
_TAB_SEP_RE = re.compile(r'^(Level\s+\d+:)\t([^\t\n]+)\t{2,}(.*)$', re.MULTILINE)
_TAB_NOSEP_RE = re.compile(r'^(Level\s+\d+:)\t([^\t\n]+)$', re.MULTILINE)


def _normalize_mxd_tabs(text: str) -> str:
    text = _TAB_SEP_RE.sub(r'\1 \2 -- \3', text)
    text = _TAB_NOSEP_RE.sub(r'\1 \2', text)
    return text


def _parse_text_file(refdata, post_id: int, content: bytes):
    """Parse a .mxd or .txt file through the existing text extractors."""
    from pipeline.extractors import text as tex, text_v2 as tv2
    text_body = content.decode("utf-8", errors="replace")
    text_body = _normalize_mxd_tabs(text_body)
    # Try text_v2 first (newer Mids format), then text (older).
    for rec in tv2.extract(refdata, post_id, text_body):
        if rec.powers:
            return rec
    for rec in tex.extract(refdata, post_id, text_body):
        if rec.powers:
            return rec
    return None


def parse_and_insert(cache: sqlite3.Connection, slots: sqlite3.Connection,
                     refdata, dry_run: bool) -> None:
    from pipeline.scan import _insert_record

    rows = cache.execute(
        "SELECT file_id, post_id, ext, content FROM attachment "
        "WHERE content IS NOT NULL"
    ).fetchall()

    n_inserted = n_dupe = n_fail = 0
    for row in rows:
        ext     = row["ext"]
        content = row["content"]
        post_id = row["post_id"]

        try:
            if ext == "mbd":
                rec = _parse_mbd_file(refdata, post_id, content)
            else:
                rec = _parse_text_file(refdata, post_id, content)
        except Exception as e:
            n_fail += 1
            continue

        if rec is None or not rec.powers:
            continue

        if dry_run:
            print(f"  [dry-run] file_id={row['file_id']} ext={ext} AT={rec.archetype} "
                  f"primary={rec.primary_set} powers={len(rec.powers)}")
            n_inserted += 1
            continue

        try:
            inserted = _insert_record(slots, rec)
            if inserted:
                n_inserted += 1
            else:
                n_dupe += 1
        except Exception:
            n_fail += 1

    if not dry_run:
        slots.commit()
    print(f"  Parsed: {n_inserted} inserted, {n_dupe} dupes, {n_fail} errors")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE,
                    help=f"seconds between requests (default {DEFAULT_RATE})")
    ap.add_argument("--limit", type=int, default=None,
                    help="max new files to download this run")
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate and show what would be done, without fetching or inserting")
    ap.add_argument("--parse-only", action="store_true",
                    help="skip downloading; only parse what's already cached")
    args = ap.parse_args()

    archive = sqlite3.connect(str(ARCHIVE_DB))
    archive.row_factory = sqlite3.Row
    cache   = open_cache()

    from pipeline import db_schema
    from pipeline.refdata import load as load_refdata
    slots   = db_schema.connect()
    refdata = load_refdata()

    print("Step 1: enumerating attachment links...")
    files = enumerate_links(archive)
    mbd_count = sum(1 for f in files.values() if f["ext"] == "mbd")
    mxd_count = sum(1 for f in files.values() if f["ext"] == "mxd")
    txt_count = sum(1 for f in files.values() if f["ext"] == "txt")
    print(f"  Found {len(files)} unique files: {mbd_count} mbd, {mxd_count} mxd, {txt_count} txt")

    if not args.parse_only:
        print(f"\nStep 2: downloading (rate={args.rate}s)...")
        download_missing(cache, files, rate=args.rate, limit=args.limit, dry_run=args.dry_run)

    print("\nStep 3: parsing and inserting...")
    parse_and_insert(cache, slots, refdata, dry_run=args.dry_run)

    archive.close()
    cache.close()
    slots.close()


if __name__ == "__main__":
    main()
