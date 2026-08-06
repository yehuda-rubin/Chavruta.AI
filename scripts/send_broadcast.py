"""Operator CLI for sending broadcast emails to all registered users.

Sends an email to every user in the Supabase auth database via Resend. Recipients are sent via
BCC for privacy — no recipient sees another recipient's address. The script requires explicit
confirmation before sending (or --yes to skip), and supports --dry-run to preview without sending.

    python scripts/send_broadcast.py --subject "Policy Update" --body-file message.html --html
    python scripts/send_broadcast.py --subject "Policy Update" --body-file message.txt --dry-run
    python scripts/send_broadcast.py --subject "Policy Update" --body-file message.html --html --yes

Requires RESEND_API_KEY and RESEND_FROM in the environment, and Supabase credentials
(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY) to fetch the recipient list.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.accounts as accounts  # noqa: E402
import app.email as email  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--subject", required=True, help="Email subject line")
    ap.add_argument("--body-file", required=True, help="Path to file containing email body (text or HTML)")
    ap.add_argument("--html", action="store_true", help="Treat body-file as HTML (default: plain text)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be sent without actually sending")
    ap.add_argument("--yes", action="store_true",
                    help="Skip confirmation prompt and send immediately")
    args = ap.parse_args()

    # Read body file
    body_path = Path(args.body_file)
    if not body_path.exists():
        raise SystemExit(f"body file not found: {args.body_file}")
    body = body_path.read_text(encoding="utf-8")
    if not body.strip():
        raise SystemExit("body file is empty")

    # Get recipient list
    recipients = accounts.list_supabase_user_emails()
    if not recipients:
        print("No recipients found (Supabase may not be configured or no users exist)")
        return

    print(f"Recipients: {len(recipients)} user(s)")
    if args.dry_run:
        print(f"Subject: {args.subject}")
        print(f"Body type: {'HTML' if args.html else 'plain text'}")
        print(f"Body length: {len(body)} characters")
        print(f"Body preview: {body[:200]}{'...' if len(body) > 200 else ''}")
        print("\n[DRY RUN: would send but not actually sending]")
        return

    # Confirm before sending
    if not args.yes:
        print(f"About to send to {len(recipients)} recipient(s)")
        print(f"Subject: {args.subject}")
        print(f"Body type: {'HTML' if args.html else 'plain text'}")
        response = input("Type 'send' to proceed: ").strip().lower()
        if response != "send":
            raise SystemExit("aborted")

    # Send email
    html_body = body if args.html else None
    text_body = None if args.html else body
    success = email.send_email(
        to=recipients,
        subject=args.subject,
        html=html_body or "",
        text=text_body,
    )

    if success:
        print(f"✅ Email sent successfully to {len(recipients)} recipient(s)")
    else:
        print("❌ Email send failed (check logs for details)")
        sys.exit(1)


if __name__ == "__main__":
    main()
