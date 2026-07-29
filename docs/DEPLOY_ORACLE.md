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

**Decided 2026-07-30: launch fully free, billing untouched entirely.** No PayPlus/Green Invoice
setup at all for now — not even sandbox. Real charges would need a registered Israeli business (at
minimum "עוסק פטור") to open a merchant account and legally issue a tax invoice, which for the
founder also means clearing it with his unit first (he's about to start IDF/hesder service — see
the 2026-07-30 addendum in `docs/legal/REVIEW-2026-07-27.md` for what that involves). Rather than
resolve that now, the call is to **launch free, watch real usage, and only deal with business
registration once there are enough users that monetizing is actually worth the army-approval +
registration process.** `PAYPLUS_*` / `GREENINVOICE_*` all stay unset in `.env` — billing is fully
optional and simply off (see `.env.example`); the plans/billing UI can stay hidden or marked
"coming soon" for this phase. Revisit this whole section when that day comes.

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
- **Generation now runs on Google Gemini, not Nebius** — a per-founder decision to launch on
  Google's free tier while the product itself is still free (see `docs/legal/REVIEW-2026-07-27.md`'s
  2026-07-29 addendum: **no Terms/Privacy update was needed for this** — §3 of both already names
  "our AI model provider" generically, never "Nebius" specifically, precisely so a provider switch
  is a config change, not a legal one). Get a free API key from
  [Google AI Studio](https://aistudio.google.com/apikey) (a personal action — I can't create one on
  your behalf) and set:
  ```
  CHAVRUTA_LLM_BACKEND=nebius        # really just means "OpenAI-compatible transport" — see presets.py
  CHAVRUTA_LLM_PRESET=gemini         # fills in Gemini's base URL + the free-tier-eligible Flash model
  CHAVRUTA_LLM_API_KEY=<your Gemini API key>
  ```
  ⚠️ **Switch to Gemini's paid tier (enable billing on the Google Cloud project behind that key) the
  moment you have a first paying customer, not before** — the free tier trains on input and is read
  by human reviewers per Google's ToS; that's tolerable for a free product, not for a paying one.
  Same shape as the future PayPlus switch below: a config change, no code change either way. Also
  unmeasured against this product's eval yet (the baseline is Nebius/Qwen3-235B) — watch answer
  quality once live, and keep `NEBIUS_API_KEY` in `.env` (commented) as a one-line rollback.
- **`PAYPLUS_*` / `GREENINVOICE_*` — leave every line commented out.** No signup, no keys, nothing
  to do here for this launch (see the top-of-file decision). Billing is simply off.
- `CHAVRUTA_PUBLIC_URL` — set once you have a domain (§4), or the instance's public IP as an interim
  (`http://<public-ip>:5173`).

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
