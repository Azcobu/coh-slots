"""
Ingest manually-submitted .mbd files from data/submitted/<SubmitterName>/.

Each subfolder is treated as a separate submitter; the folder name becomes the
author field on the resulting build records.  File content is hashed so that
files already in the DB are skipped on incremental runs (after a full reset
the build table is empty, so all files are re-processed regardless).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from . import db_schema
from .refdata import load as load_refdata
from .extractors.mbd import (
    _classify_powersets,
    _slot_enh_from_uid,
)
from .extractors.common import BuildRecord, PowerSlotting
from .scan import _insert_record
from .banned import is_banned

SUBMITTED_DIR = db_schema.PROJECT_ROOT / "data" / "submitted"


def scan_submitted() -> None:
    if not SUBMITTED_DIR.is_dir():
        print("No submitted/ directory found, skipping.")
        return

    refdata = load_refdata()
    conn = db_schema.connect()
    conn.executescript(db_schema.SCHEMA)
    conn.commit()

    n_new = n_inserted = n_sig_dupes = n_already = 0

    for submitter_dir in sorted(SUBMITTED_DIR.iterdir()):
        if not submitter_dir.is_dir():
            continue
        submitter = submitter_dir.name
        mbd_files = sorted(submitter_dir.glob("*.mbd"))
        if not mbd_files:
            continue
        print(f"  Submitted/{submitter}: {len(mbd_files)} file(s)")

        for mbd_file in mbd_files:
            raw = mbd_file.read_bytes()
            file_hash = hashlib.sha256(raw).hexdigest()

            already = conn.execute(
                "SELECT 1 FROM submitted_file WHERE file_hash = ?", (file_hash,)
            ).fetchone()
            if already:
                n_already += 1
                continue

            n_new += 1
            posted_at = datetime.fromtimestamp(
                mbd_file.stat().st_mtime
            ).isoformat(" ", "minutes")
            # Synthetic post_id: negative to avoid collisions with archive IDs.
            post_id = -(int(file_hash[:8], 16) % (2 ** 31))

            try:
                data = json.loads(raw)
            except Exception as e:
                print(f"    decode failed for {mbd_file.name}: {e}")
                continue

            rec = BuildRecord(
                post_id=post_id,
                block_index=0,
                source_format="MBD",
                archetype=refdata.archetype_map.get(
                    data.get("Class", ""), data.get("Class")
                ),
            )
            ps_list = data.get("PowerSets") or []
            rec.primary_set, rec.secondary_set, rec.epic_set = _classify_powersets(
                refdata, rec.archetype, ps_list
            )

            for pe in data.get("PowerEntries") or []:
                full_name = pe.get("PowerName")
                if not full_name:
                    continue
                disp = refdata.powers_index.get(full_name, {}).get("display_name", "")
                if is_banned(disp):
                    continue
                enhs = []
                for se in pe.get("SlotEntries") or []:
                    enh_obj = se.get("Enhancement") if se else None
                    if not enh_obj:
                        continue
                    slot_enh = _slot_enh_from_uid(
                        refdata, enh_obj.get("Uid"), enh_obj.get("IoLevel")
                    )
                    if slot_enh is not None:
                        enhs.append(slot_enh)
                if enhs:
                    rec.powers.append(
                        PowerSlotting(power_full_name=full_name, enhancements=enhs)
                    )

            inserted = _insert_record(conn, rec, author=submitter, posted_at=posted_at)
            if inserted:
                conn.execute(
                    "INSERT OR IGNORE INTO submitted_file "
                    "(file_hash, submitter, filename) VALUES (?,?,?)",
                    (file_hash, submitter, mbd_file.name),
                )
                n_inserted += 1
            else:
                n_sig_dupes += 1

        conn.commit()

    conn.close()
    print(
        f"Submitted scan complete: {n_new} new files, {n_inserted} builds inserted, "
        f"{n_sig_dupes} signature dupes, {n_already} already ingested."
    )
