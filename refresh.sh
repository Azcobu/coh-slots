#!/usr/bin/env bash
# Full data refresh + freeze sequence.
# Run from the project root.  Stops immediately on any error.
set -euo pipefail

cd "$(dirname "$0")"

echo "==> pipeline all (scan + aggregate + validate)"
python -m pipeline all

echo "==> re-inject attachment builds (parse-only)"
python scripts/fetch_attachments.py --parse-only

echo "==> import local builds: Icesphere"
python scripts/import_local_builds.py --dir data/submitted/Icesphere --author Icesphere

echo "==> import local builds: Maelwys"
python scripts/import_local_builds.py --dir data/submitted/Maelwys --author Maelwys

echo "==> pipeline aggregate (include all imported builds)"
python -m pipeline aggregate

echo "==> freeze (generates slots_deploy.sqlite + data/filter-json/ + build/)"
python scripts/freeze.py

echo ""
echo "Done.  To deploy:"
echo "  git add data/slots_deploy.sqlite data/filter-json/"
echo "  git commit -m 'refresh data'"
echo "  git push"
