"""Read-only scan of the live Qdrant collection: distinct ref prefixes -> [points, first ref].

Run it ON the host that serves Qdrant and save stdout, then feed that to build_catalog.py --works:
    ssh -i ~/.ssh/chavruta_nebius chavruta@<host> 'nice -n 10 python3 -' < scripts/scan_collection_works.py > scan.json
Fetches only the `ref` payload field, 2000 points a page, with a short pause between pages.
"""
import json, re, sys, time, urllib.request
URL = "http://localhost:6333/collections/chavruta_commercial/points/scroll"
TAIL = re.compile(r"(?:[.\s]\d+[ab]?)+$")
nat = lambda r: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", r)]
works = {}
off = None
n = 0
while True:
    body = {"limit": 2000, "with_payload": {"include": ["ref"]}, "with_vector": False}
    if off is not None: body["offset"] = off
    req = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=60))["result"]
    for p in r["points"]:
        ref = (p.get("payload") or {}).get("ref") or ""
        t = TAIL.sub("", ref)
        w = works.setdefault(t, [0, ref])
        w[0] += 1
        if nat(ref) < nat(w[1]): w[1] = ref
    n += len(r["points"])
    off = r.get("next_page_offset")
    if off is None: break
    time.sleep(0.05)
json.dump({"points": n, "works": works}, sys.stdout, ensure_ascii=False)
