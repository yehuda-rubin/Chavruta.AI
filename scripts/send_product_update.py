"""Send the product-update email to users who opted in, through Amazon SES.

Safe by default: with no flags it only counts and previews (a dry run). Sending needs --send, a
sender identity (MAIL_SENDER_IDENTITY, required for an advertising email) and UNSUBSCRIBE_SECRET.

    python scripts/send_product_update.py                       # dry run: counts, first few, subject
    python scripts/send_product_update.py --test-to me@x.com    # one real message to yourself
    python scripts/send_product_update.py --send --limit 40     # a first slice
    python scripts/send_product_update.py --send --offset 40    # the rest

Recipients come from Supabase with `user_metadata.marketing_consent == true` (app/marketing.py), never
from the full user list. Every message carries its own signed withdrawal link and the one-click
`List-Unsubscribe` headers (RFC 8058). Run it on the server (it needs the Supabase service key).
"""
from __future__ import annotations

import argparse
import email.message
import os
import re
import smtplib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from app import marketing  # noqa: E402

# "פרסומת" at the start of the subject is a legal requirement for advertising mail in Israel.
SUBJECT = "פרסומת: חברותא התחדשה, עם מודל משודרג, חיפוש בספרים ודף יומי"
TEMPLATE = Path(__file__).with_name("product_update_email.html")


def render(user_id: str, identity: str) -> tuple[str, str, str]:
    """(html, plain text, unsubscribe url) for one recipient."""
    url = marketing.unsubscribe_url(user_id)
    html = TEMPLATE.read_text(encoding="utf-8").replace("{{unsubscribe_url}}", url).replace("{{identity}}", identity)
    text = re.sub(r"<[^>]+>", "", re.sub(r"</(p|h1|tr)>|<br\s*/?>", "\n", html))
    text = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()
    return html, text, url


def build(to: str, user_id: str, identity: str, from_header: str) -> email.message.EmailMessage:
    html, text, url = render(user_id, identity)
    msg = email.message.EmailMessage()
    msg["Subject"] = SUBJECT
    msg["From"] = from_header
    msg["To"] = to
    msg["List-Unsubscribe"] = f"<{url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg["Precedence"] = "bulk"
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _connect(host: str, port: int, user: str, password: str) -> smtplib.SMTP:
    server = smtplib.SMTP(host, port, timeout=30)
    server.starttls()
    server.login(user, password)
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--send", action="store_true", help="actually send (default is a dry run)")
    ap.add_argument("--test-to", metavar="ADDRESS", help="send ONE message to this address and stop")
    ap.add_argument("--limit", type=int, default=0, help="send to at most N recipients (0 = all)")
    ap.add_argument("--offset", type=int, default=0, help="skip the first N recipients (for staged sends)")
    ap.add_argument("--delay", type=float, default=0.1, help="seconds between messages (default 0.1)")
    args = ap.parse_args()

    identity = os.environ.get("MAIL_SENDER_IDENTITY", "").strip()
    host = os.environ.get("AWS_SES_SMTP_HOST", "").strip()
    port = int(os.environ.get("AWS_SES_SMTP_PORT", "587"))
    user = os.environ.get("AWS_SES_SMTP_USER", "").strip()
    password = os.environ.get("AWS_SES_SMTP_PASSWORD", "").strip()
    from_header = os.environ.get("AWS_SES_FROM", "").strip() or "צוות חברותא AI בית מדרש <hello@chavrutaai.org>"
    live = bool(args.send or args.test_to)

    if live:
        if not identity:
            raise SystemExit("Set MAIL_SENDER_IDENTITY (the sender's name and a contact address): an "
                             "advertising email must identify who sends it.")
        if not (host and user and password):
            raise SystemExit("Missing AWS_SES_SMTP_HOST / AWS_SES_SMTP_USER / AWS_SES_SMTP_PASSWORD")
    if not os.environ.get("UNSUBSCRIBE_SECRET", "").strip():
        raise SystemExit("Set UNSUBSCRIBE_SECRET: without it the withdrawal link would be refused.")

    if args.test_to:
        recipients = [("test-preview", args.test_to.strip().lower())]
    else:
        recipients = marketing.list_marketing_recipients()
        if not recipients:
            raise SystemExit("No opted-in recipients (or Supabase is not configured here).")
        recipients = recipients[args.offset:]
        if args.limit:
            recipients = recipients[: args.limit]

    print(f"Subject: {SUBJECT}")
    print(f"From: {from_header}")
    print(f"Opted-in recipients in this run: {len(recipients)}")
    if not live:
        print("First 3:", [f"{e[:2]}***@{e.split('@')[-1]}" for _, e in recipients[:3]])
        print("[DRY RUN: nothing was sent. Use --test-to ADDRESS first, then --send.]")
        return

    server = _connect(host, port, user, password)
    sent = failed = 0
    for i, (uid, addr) in enumerate(recipients, 1):
        msg = build(addr, uid, identity, from_header)
        try:
            server.send_message(msg)
            sent += 1
        except Exception as exc:          # noqa: BLE001 — one retry on a fresh connection, then move on
            try:
                server = _connect(host, port, user, password)
                server.send_message(msg)
                sent += 1
            except Exception as retry:    # noqa: BLE001
                failed += 1
                print(f"[{i}/{len(recipients)}] FAILED {addr[:2]}***@{addr.split('@')[-1]}: {retry or exc}")
        if i % 25 == 0 or i == len(recipients):
            print(f"[{i}/{len(recipients)}] sent={sent} failed={failed}")
        time.sleep(max(args.delay, 0))
    try:
        server.quit()
    except Exception:                     # noqa: BLE001
        pass
    print(f"Done: sent {sent}, failed {failed}.")


if __name__ == "__main__":
    main()
