"""Broadcast legal update email to all registered users via Amazon SES.

Uses Amazon SES SMTP credentials from environment (.env).
Sends personalized emails (each recipient sees only their own address in 'To')
with a shared SMTP connection for optimal speed and reliability.
"""

from __future__ import annotations

import argparse
import email.message
import os
import smtplib
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

import app.accounts as accounts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Preview recipients without sending")
    ap.add_argument("--yes", action="store_true", help="Skip confirmation prompt and send immediately")
    ap.add_argument("--delay", type=float, default=0.08, help="Delay between emails in seconds (default: 0.08s ~ 12/s)")
    args = ap.parse_args()

    # Verify template exists
    template_path = Path(__file__).parent / "legal_update_email.html"
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")
    html_content = template_path.read_text(encoding="utf-8")

    subject = "עדכון תנאי השימוש ומדיניות הפרטיות — חברותא AI"

    # Fetch recipients
    raw_recipients = accounts.list_supabase_user_emails()
    if not raw_recipients:
        raise SystemExit("No recipients found in Supabase")

    # Clean & deduplicate
    recipients: list[str] = []
    seen = set()
    for r in raw_recipients:
        clean = (r or "").strip().lower()
        if clean and "@" in clean and clean not in seen:
            seen.add(clean)
            recipients.append(clean)

    print(f"Total unique recipients: {len(recipients)}")

    if args.dry_run:
        print("\n--- DRY RUN PREVIEW ---")
        print(f"Subject: {subject}")
        print(f"Sender: Chavruta.AI <auth@chavrutaai.org>")
        print(f"First 5 recipients: {recipients[:5]}")
        print(f"Last 5 recipients: {recipients[-5:]}")
        print("[DRY RUN COMPLETE: no emails were sent]")
        return

    # Check SES SMTP credentials
    host = os.environ.get("AWS_SES_SMTP_HOST", "").strip()
    port = int(os.environ.get("AWS_SES_SMTP_PORT", "587"))
    user = os.environ.get("AWS_SES_SMTP_USER", "").strip()
    password = os.environ.get("AWS_SES_SMTP_PASSWORD", "").strip()
    from_addr = os.environ.get("AWS_SES_FROM", "").strip() or "Chavruta.AI <auth@chavrutaai.org>"

    if not (host and user and password):
        raise SystemExit("Missing AWS SES SMTP credentials in environment")

    # Parse sender
    if "<" in from_addr and from_addr.endswith(">"):
        from_name, from_email = from_addr.split("<", 1)
        from_header = f"{from_name.strip()} <{from_email[:-1].strip()}>"
    else:
        from_header = f"Chavruta.AI <{from_addr.strip()}>"

    if not args.yes:
        print(f"\nAbout to broadcast email to {len(recipients)} users via Amazon SES ({host}).")
        print(f"From: {from_header}")
        print(f"Subject: {subject}")
        confirm = input("Type 'send' to proceed with live broadcast: ").strip().lower()
        if confirm != "send":
            raise SystemExit("Aborted by user.")

    # Send with persistent SMTP connection
    success_count = 0
    fail_count = 0
    failed_emails = []

    print(f"\nConnecting to Amazon SES SMTP ({host}:{port})...")
    server = smtplib.SMTP(host, port, timeout=30)
    server.starttls()
    server.login(user, password)
    print("Authenticated successfully. Starting dispatch...\n")

    start_time = time.time()

    for idx, recipient in enumerate(recipients, 1):
        msg = email.message.EmailMessage()
        msg["Subject"] = subject
        msg["From"] = from_header
        msg["To"] = recipient
        msg.set_content(html_content, subtype="html")

        try:
            server.send_message(msg)
            success_count += 1
            if idx % 10 == 0 or idx == len(recipients):
                print(f"[{idx}/{len(recipients)}] Sent to {recipient[:3]}***@{recipient.split('@')[-1]}")
        except Exception as exc:
            print(f"[{idx}/{len(recipients)}] ❌ Failed for {recipient}: {exc}")
            # Attempt reconnect once if connection was dropped
            try:
                server = smtplib.SMTP(host, port, timeout=30)
                server.starttls()
                server.login(user, password)
                server.send_message(msg)
                success_count += 1
                print(f"[{idx}/{len(recipients)}] Reconnected and sent successfully.")
            except Exception as retry_exc:
                fail_count += 1
                failed_emails.append((recipient, str(retry_exc)))

        if args.delay > 0:
            time.sleep(args.delay)

    try:
        server.quit()
    except Exception:
        pass

    duration = time.time() - start_time
    print(f"\n==========================================")
    print(f"Broadcast finished in {duration:.1f} seconds")
    print(f"✅ Success: {success_count}/{len(recipients)}")
    if fail_count > 0:
        print(f"❌ Failed: {fail_count}")
        for femail, err in failed_emails:
            print(f"  - {femail}: {err}")
    print(f"==========================================")


if __name__ == "__main__":
    main()
