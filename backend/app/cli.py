"""Operational commands.

    python -m app.cli genkey      # print a fresh .env secret block
    python -m app.cli cleanup     # run retention cleanup once
    python -m app.cli audit [N]   # print the last N audit events
"""

from __future__ import annotations

import base64
import json
import secrets
import sys


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "help"
    if cmd == "genkey":
        print(f"AFTERIMAGE_MASTER_KEY={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')}")
        print(f"AFTERIMAGE_AUDIT_SECRET={secrets.token_urlsafe(32)}")
        print(f"AFTERIMAGE_ADMIN_TOKEN={secrets.token_urlsafe(32)}")
        return 0

    from sqlalchemy import select

    from app.config import get_settings
    from app.db import init_engine, session_factory
    from app.models.orm import AuditEvent, Base
    from app.services.cleanup import purge_expired
    from app.services.context import Services

    settings = get_settings()
    engine = init_engine(settings.database_url)
    Base.metadata.create_all(engine)
    if cmd == "cleanup":
        with session_factory()() as db:
            print(json.dumps(purge_expired(db, Services.from_settings(settings))))
        return 0
    if cmd == "audit":
        n = int(argv[2]) if len(argv) > 2 else 50
        with session_factory()() as db:
            for e in db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(n)):
                print(f"{e.created_at:%Y-%m-%d %H:%M:%S} {e.outcome:8} {e.event_type:28} {json.dumps(e.details)}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
