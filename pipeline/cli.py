"""
Entry-point: `python -m pipeline <subcommand>`

Subcommands:
    refdata   rebuild reference jsons from I12.mhd / EnhDB.mhd
    scan      parse archive.sqlite -> slots.sqlite
    aggregate compute power_stats from slots.sqlite
    validate  print coverage report
    all       refdata + scan + aggregate + validate
"""
from __future__ import annotations

import argparse
import sys

from . import refdata as refdata_mod
from . import scan as scan_mod
from . import aggregate as agg_mod
from . import validate as val_mod


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("refdata", help="rebuild reference jsons")

    s_scan = sub.add_parser("scan", help="parse archive into slots.sqlite")
    s_scan.add_argument("--limit", type=int, default=None)
    s_scan.add_argument("--no-reset", action="store_true")

    sub.add_parser("aggregate", help="compute power_stats")

    s_val = sub.add_parser("validate", help="coverage report")
    s_val.add_argument("--top", type=int, default=20)

    s_all = sub.add_parser("all", help="run scan + aggregate + validate (not refdata)")
    s_all.add_argument("--limit", type=int, default=None)
    s_all.add_argument("--top", type=int, default=20)

    args = p.parse_args(argv)

    if args.cmd == "refdata":
        refdata_mod.build()
    elif args.cmd == "scan":
        scan_mod.scan(limit=args.limit, reset=not args.no_reset)
    elif args.cmd == "aggregate":
        agg_mod.aggregate()
    elif args.cmd == "validate":
        val_mod.report(top=args.top)
    elif args.cmd == "all":
        scan_mod.scan(limit=args.limit, reset=True)
        agg_mod.aggregate()
        val_mod.report(top=args.top)


if __name__ == "__main__":
    main()
