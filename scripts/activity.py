"""Is anyone using the system right now? — the pre-deploy gate.

Every deploy so far has followed one rule: restart only if the last 15 minutes are empty. A restart
kills any generation in flight, and a lesson that dies mid-run costs the user a minute of waiting
and their quota, with no way to give either back.

Run it against the live container:

    docker compose cp scripts/activity.py api:/tmp/activity.py
    docker compose exec -T api python /tmp/activity.py

It lived only inside the container until 2026-08-14, created ad-hoc in a session — so
`docker compose up -d` deleted it, and the next deploy had no gate to check. It belongs in the repo
for that reason: the check that decides whether a deploy is safe should not be the one artefact the
deploy destroys.

**Reads timing only — never content.** Message bodies are the users' own words; deciding whether to
restart needs to know that a message exists and when, and nothing else.

The `messages` count is the load-bearing one, not `requests`. A request row is written when the
generation COMPLETES, so a turn that is still running shows as zero requests and one user message.
Zero requests therefore does not mean idle; a user message with no assistant reply after it means a
generation is in flight right now. That is exactly the case worth waiting out.
"""
import sqlite3
from datetime import UTC, datetime, timedelta

DB = "/app-data/chavruta.db"

now = datetime.now(UTC)
print("now (UTC)", now.strftime("%Y-%m-%d %H:%M:%S"))
print()

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def _count(table: str, column: str, since: datetime) -> int:
    try:
        return conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} >= ?", (since.isoformat(),)
        ).fetchone()[0]
    except sqlite3.Error:
        return -1


for minutes in (5, 15, 60, 180):
    since = now - timedelta(minutes=minutes)
    print(f"  last {minutes:4d}min: {_count('usage_events', 'at', since):3d} request(s), "
          f"{_count('sessions', 'created_at', since):3d} new chat(s), "
          f"{_count('messages', 'created_at', since):3d} message(s)")

print()
print("=== the last 10 requests ===")
for at, intent, ms, calls in conn.execute(
        "SELECT at, intent, ms, llm_calls FROM usage_events ORDER BY at DESC LIMIT 10"):
    ago = (now - datetime.fromisoformat(at)).total_seconds() / 60
    print(f"  {at[11:19]} UTC  ({ago:6.1f} min ago)  {intent or '?':<11} "
          f"{(ms or 0) / 1000:4.0f}s  rounds={calls or 0}")

print()
print("=== the last 5 messages (timing only, no content) ===")
for at, role in conn.execute(
        "SELECT created_at, role FROM messages ORDER BY created_at DESC LIMIT 5"):
    ago = (now - datetime.fromisoformat(at)).total_seconds() / 60
    print(f"  {at[11:19]} UTC  ({ago:6.1f} min ago)  {role}")

conn.close()
