<!--
  Deploying Chavruta.AI on a Hugging Face Space (Docker SDK, free CPU tier) — $0.
  Written 2026-07-31 as a parallel path to docs/DEPLOY_ORACLE.md while Oracle's Always Free A1
  capacity keeps coming back "Out of host capacity". Both can run at once; whichever comes up
  first is the one you actually share.
-->

# Deploying Chavruta.AI on Hugging Face Spaces (Docker SDK, free tier)

**The tradeoff vs Oracle:** no capacity lottery — this always provisions instantly. In exchange,
the free tier's disk is **ephemeral** (wiped whenever the Space restarts), so the corpus snapshot
(17GB) has to be restored from HF on every cold start instead of once. The keep-alive workflow
below (§4) is what keeps cold starts rare rather than routine — set it up, don't skip it.

Everything here runs in **one container** (`docker/Dockerfile.hfspace`) — unlike
`docker-compose.yml`'s four services, because HF Spaces exposes exactly one port and runs exactly
one container. `docker/entrypoint.hfspace.sh` starts nginx immediately (so the platform's own
"is the port listening" check never sees a closed port), then Qdrant, then restores the corpus
(skipped if it's somehow already there), then the API, then the UI.

---

## 1. Account + Space — steps only you can do

1. Create a Hugging Face account at [huggingface.co/join](https://huggingface.co/join) — email
   only, no payment info needed for the free tier.
2. Go to [huggingface.co/new-space](https://huggingface.co/new-space):
   - **Space name:** e.g. `chavruta-ai`.
   - **License:** whatever fits (this doesn't affect the free compute tier).
   - **SDK:** **Docker** → template **Blank**.
   - **Hardware:** the default free **CPU basic** (2 vCPU, 16GB RAM).
   - **Visibility:** Public or Private — private still works for testers you invite, and keeps the
     Space off the public HF gallery if you'd rather not advertise it there yet.
3. Once created, HF shows you the Space's own git remote URL:
   `https://huggingface.co/spaces/<your-username>/chavruta-ai`.

---

## 2. Add secrets — before the first push

**Space page → Settings → Variables and secrets → New secret.** At minimum:

- `NEBIUS_API_KEY` — your Nebius API key (Secret, not Variable — it's sensitive). This is the only
  one strictly required for the app to answer anything at all.

Optional, add later if/when wanted (all unset = that feature is simply off, matching local dev):
- `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` — real per-user
  accounts and quotas instead of everyone sharing one anonymous bucket. Without these the app still
  works, just without login.
- `CHAVRUTA_CORS_ORIGINS` — only needed if you ever call the API from a domain other than the
  Space's own.

Runtime variables/secrets are injected as normal environment variables — `app/api.py` reads them
exactly the same way it does locally via `.env`.

---

## 3. Push the code

The Dockerfile lives at `docker/Dockerfile.hfspace` in this repo, but HF's Docker SDK requires a
file literally named `Dockerfile` at the **repo root** of the Space itself (same for `README.md`,
which needs the SDK/port frontmatter — see `deploy/huggingface/README.md`). Rather than keep a
second root-level `Dockerfile` permanently sitting in the main branch (confusing — `docker build .`
locally would pick the wrong one up), copy the two files into place only for the push:

```bash
# from the repo root, one-time setup:
git remote add space https://huggingface.co/spaces/<your-username>/chavruta-ai

# every time you want to (re)deploy:
cp docker/Dockerfile.hfspace Dockerfile
cp deploy/huggingface/README.md README.md.hfspace-tmp && mv README.md README.md.orig-tmp && mv README.md.hfspace-tmp README.md
git add -f Dockerfile README.md
git commit -m "deploy: HF Space snapshot"
git push space HEAD:main --force
# clean up so the main branch stays as it was:
git reset --soft HEAD~1
mv README.md.orig-tmp README.md
rm Dockerfile
git checkout -- README.md 2>/dev/null || true
```

HF starts building the moment it receives the push — watch progress under the Space's **Logs** tab
(build logs, then container/runtime logs once it starts). The build itself (installing torch, Node,
downloading bge-m3) takes several minutes the first time; that's normal and only happens on a code
change, not on every cold start.

---

## 4. Keep it awake — don't skip this

Free CPU Spaces sleep after **48 hours with no traffic**, and sleeping means the ephemeral disk
gets wiped on the next wake (a fresh multi-GB corpus restore, several minutes, before anyone's first
question works). A scheduled ping well inside that window prevents the Space from ever crossing the
threshold, so it never sleeps in the first place. See `.github/workflows/keepalive.yml` — it's
already in this repo (this repo is public, so GitHub Actions runs it for free), just fill in the
Space's URL in the workflow file once you know it.

---

## 5. If you outgrow this

Free CPU Spaces don't support multiple replicas or autoscaling (that needs paid hardware, or a
different HF product — "Inference Endpoints" — entirely). If load ever genuinely needs more than
one instance's worth of capacity, that's a real architecture conversation to have then, not now —
the concurrency gate in `app/api.py` (`CHAVRUTA_MAX_CONCURRENT_GENERATIONS`) is what keeps a single
free instance from falling over under a burst in the meantime.
