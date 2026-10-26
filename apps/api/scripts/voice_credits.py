"""Operator-only voice credit management using the configured database connection."""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from app.core.database import AsyncSessionLocal, engine
from app.services.billing.voice_quota import allowance_snapshot


async def run(args):
    try:
        if args.command == "migrate":
            path = Path(__file__).resolve().parents[1] / "database/migrations/20261016_consolidate_voice_credits.sql"
            async with engine.connect() as connection:
                raw = await connection.get_raw_connection()
                try:
                    await raw.driver_connection.execute(path.read_text(encoding="utf-8-sig"))
                except Exception:
                    await raw.driver_connection.execute("ROLLBACK")
                    raise
            print("Voice credits consolidated into audit history; obsolete credit table and session view removed.")
            return
        async with AsyncSessionLocal() as db:
            if args.command == "grant":
                row = (await db.execute(text("""
                    select * from public.grant_voice_minutes(:email, :minutes, :reason, :request_id)
                """), {"email": args.email, "minutes": args.minutes, "reason": args.reason,
                         "request_id": args.request_id})).mappings().one()
                org_id = row["org_id"]
                await db.commit()
                print(f"Grant recorded: {row['id']} (+{row['seconds'] // 60} minutes). Reusing this ID does not add minutes again.")
            else:
                org_id = (await db.execute(text("""
                    select org_id from public.users where lower(btrim(email))=lower(btrim(:email))
                    and is_active and org_id is not null
                """), {"email": args.email})).scalar_one()
            print(json.dumps(await allowance_snapshot(db, org_id), indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Migrate credit history and remove obsolete database objects")
    balance = commands.add_parser("balance", help="Show the clinic balance for an active account")
    balance.add_argument("--email", required=True)
    grant = commands.add_parser("grant", help="Grant extra minutes to this email's clinic")
    grant.add_argument("--email", required=True)
    grant.add_argument("--minutes", type=int, required=True)
    grant.add_argument("--reason", required=True)
    grant.add_argument("--request-id", type=UUID, required=True, help="Unique UUID; reuse it when retrying this grant")
    args = parser.parse_args()
    if args.command == "grant" and (not 1 <= args.minutes <= 100000 or not 1 <= len(args.reason.strip()) <= 500):
        parser.error("Use 1-100000 minutes and a reason of 1-500 characters")
    try:
        asyncio.run(run(args))
    except Exception as exc:
        # Avoid printing SQLAlchemy exceptions containing credentials or SQL parameters.
        print(f"Credit operation failed ({type(exc).__name__}). Check account email, database permissions, migration, and request ID. Retry grants with the SAME request ID.")
        raise SystemExit(1)
