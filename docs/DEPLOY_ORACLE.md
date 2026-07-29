# Deploying Chavruta.AI on Oracle Cloud (Always Free)

**Written 2026-07-29, before an Oracle account existed.** Decided over GCP Always Free (1GB/month
egress — too thin for live traffic), Qdrant Cloud free tier (1GB RAM/4GB disk — smaller than the
collection), HF Spaces (ephemeral disk — the index gets wiped on every restart), and Render/
Railway/Fly.io (no real free production tier). One Oracle "Always Free" Ampere A1 VM runs the
whole stack — API + Qdrant + the Next.js UI — behind nginx.

⚠️ Oracle cut this tier's Ampere A1 allowance in half (4 OCPU/24GB → 2 OCPU/12GB) on 2026-06-15
without announcing it. Treat "Always Free" as **currently** free, not permanently guaranteed — if
it's cut or killed again, the fallback is re-provisioning elsewhere and restoring from the HF
snapshot (see step 5); that path should stay tested, not just assumed.

Launching **free** (no paying customers yet): PayPlus/Green Invoice stay unconfigured or in
`sandbox` mode the whole time (billing is fully optional — unset env vars mean it's simply off).
Flip `PAYPLUS_MODE=production` and swap in real keys only once you're ready to actually charge —
no code change needed for that switch, see `.env.example`.

---

## 1. Account + VM — steps only you can do

These need your own identity/payment verification; skip to §2 once the VM exists.

1. Create an Oracle Cloud account at [cloud.oracle.com](https://cloud.oracle.com) (personal email,
   phone verification, a card for identity verification — no charge on the Always Free tier itself).
2. Console → **Compute → Instances → Create Instance**.
   - **Image:** Ubuntu 24.04 (Canonical, "Always Free Eligible" tagged images only).
   - **Shape:** `VM.Standard.A1.Flex` — set **2 OCPU / 12 GB RAM** (the current Always Free ceiling;
     the console will refuse a bigger shape as non-free).
   - **Networking:** create/use a VCN with a public subnet, "Assign a public IPv4 address" checked.
   - **SSH keys:** let the console generate a key pair and download the private key (or paste your
     own public key) — you'll need it to log in.
3. **Open firewall ports — this is the #1 Oracle gotcha.** Two independent firewalls exist and
   BOTH must allow 80/443, or the app is unreachable despite a "running" instance:
   - **OCI Security List / Network Security Group** (Console → your VCN → Security Lists): add
     ingress rules for TCP 80 and 443 from `0.0.0.0/0`.
   - **The instance's own `iptables`** (Oracle's Ubuntu images ship with restrictive default rules):
     ```bash
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save   # or: sudo iptables-save > /etc/iptables/rules.v4
     ```
4. Note the instance's public IP. SSH in: `ssh -i <your-key>.key ubuntu@<public-ip>`.

Once you're logged in, everything below is copy-paste.

---

## 2. Docker + repo

```bash
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker    # re-login (or newgrp) so `docker` needs no sudo

git clone <your-repo-url> chavruta && cd chavruta
cp .env.example .env
```

Edit `.env`:
- `NEBIUS_API_KEY=<your real key>` — **required**, generation fails fast at boot without it.
- Leave every `PAYPLUS_*` / `GREENINVOICE_*` line commented out for a free-only launch — billing
  stays off. When you're ready to start charging, fill these in with `PAYPLUS_MODE=production` and
  real keys; nothing else in the code needs to change (see `.env.example` §Billing).
- `CHAVRUTA_PUBLIC_URL` — set once you have a domain (§4). PayPlus's callback needs this to be a
  real reachable URL, so it's fine to leave unset until billing is actually turned on.

---

## 3. Bring up the stack (Qdrant first, corpus before the app)

```bash
docker compose up -d qdrant
```

Wait for it to report healthy (`docker compose ps`), then restore the **production** collection —
**not** `scripts/load_all_indexes.py`, which builds a different, non-commercial collection and must
never be pointed at `chavruta_commercial` (see that script's own warning, and
`docs/COMMERCIAL_CORPUS.md`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install huggingface_hub requests
QDRANT_CONTAINER=chavruta-qdrant python3 scripts/restore_commercial_snapshot.py
```

`QDRANT_CONTAINER` is what makes this RAM-safe: it copies the snapshot into the container's own
filesystem and recovers from that local file, instead of uploading tens of GB over HTTP — the
direct-upload path buffers the whole snapshot in Qdrant's request pipeline and drove a 15.7GB
machine into swap in testing. On a 12GB box, always set it.

Then, required or ref-anchoring times out:

```bash
python3 scripts/create_payload_indexes.py
```

Bring up the rest:

```bash
docker compose up -d --build
curl -f http://localhost:5173/api/ready   # should return 200 once the collection has points
```

---

## 4. A real domain + TLS (do this before advertising the URL)

The shipped `web` service (nginx) publishes plain HTTP on `:5173` — fine for testing over the IP,
not for a public launch. Cheapest path: point a domain's A record at the instance's public IP, then
put [Caddy](https://caddyserver.com/) in front for automatic Let's Encrypt TLS (simplest option —
one file, no certbot timers to babysit):

```bash
sudo docker run -d --name caddy --network host \
  -v /etc/caddy/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/data caddy:2
```

with `/etc/caddy/Caddyfile`:

```
your-domain.com {
    reverse_proxy localhost:5173
}
```

Once the domain resolves, set `CHAVRUTA_PUBLIC_URL=https://your-domain.com` in `.env` and
`docker compose up -d api` to pick it up (needed for PayPlus callbacks once billing turns on, and
for `CORS_ORIGINS` if the UI and API ever end up on different hosts).

---

## 5. If Oracle's free tier goes away

Provision a replacement VM anywhere with ≥12GB RAM and Docker, repeat §2–4, and restore the corpus
from the same HF snapshot (`Yehuda-Rubin/chavruta-commercial-index`) via
`scripts/restore_commercial_snapshot.py` — that's the whole migration; nothing else is Oracle-
specific. Keep the `.env` and the domain's DNS record as the only two things to carry over by hand.
