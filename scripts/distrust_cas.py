"""Remove distrusted root CAs from an image's trust stores, at build time.

Two stores matter in our Python images: the Debian system store (urllib, openssl, curl) and
certifi's bundle (httpx, requests, openai), which ships its own copy of the roots and ignores the
system one. Both must be cleaned or the distrust is only half applied.

Why: eMudhra (emSign) CA compromise, advisory received 2026-10-27. Ubuntu's ca-certificates
20260816 dropped only the ECC G3 root; the rest are still shipped by Debian and by certifi.
None of our outbound endpoints chains to emSign (checked 2026-10-27), so removal costs nothing.

Run as root, before `USER app`:  python /app/scripts/distrust_cas.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DISTRUSTED = ("emSign",)
_CONF = Path("/etc/ca-certificates.conf")
_MIN_LEFT = 100  # a bundle this small means the filter matched far more than intended


def _system_store() -> int:
    if not _CONF.exists():
        return 0
    lines = _CONF.read_text().splitlines()
    hits = 0
    for i, line in enumerate(lines):
        if not line.startswith(("#", "!")) and any(name in line for name in DISTRUSTED):
            lines[i] = "!" + line
            hits += 1
    _CONF.write_text("\n".join(lines) + "\n")
    subprocess.run(["update-ca-certificates", "--fresh"], check=True, stdout=subprocess.DEVNULL)
    return hits


def _certifi_store() -> int:
    try:
        import certifi
    except ImportError:
        return 0
    path = Path(certifi.where())
    blocks = re.split(r"\n(?=\n# Issuer:)", path.read_text())
    keep = [b for b in blocks if not any(f"Label: \"{name}" in b for name in DISTRUSTED)]
    if sum("BEGIN CERTIFICATE" in b for b in keep) < _MIN_LEFT:
        sys.exit(f"refusing to write {path}: fewer than {_MIN_LEFT} roots would remain")
    path.write_text("\n".join(keep))
    return len(blocks) - len(keep)


if __name__ == "__main__":
    print(f"distrusted: system={_system_store()} certifi={_certifi_store()}")
