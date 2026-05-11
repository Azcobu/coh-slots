"""
Flask web frontend for coh-slots v2.

Reads from slots.sqlite (built by `python -m coh_slots_v2 all`) and the
refdata JSONs. No writes, no auth — read-only stats viewer.

Run with:
    .venv/bin/python -m webapp
or:
    FLASK_APP=webapp .venv/bin/flask run --debug
"""
from __future__ import annotations

from flask import Flask

from . import views


def create_app() -> Flask:
    app = Flask(__name__)
    views.register(app)
    return app
