import urllib.request
import json
import sys

def run_query(question, intent="halacha"):
    payload = json.dumps({"question": question, "lang": "he", "intent": intent}).encode("utf-8")
    req = urllib.request.Request(
        "http://localhost:8080/query",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))

if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "האם מותר להשתמש בדוד שמש בשבת?"
    print(f"Querying: {q}")
    res = run_query(q)
    print("\n" + "="*40 + " ANSWER " + "="*40)
    print(res.get("answer"))
    print("\n" + "="*40 + " CITATIONS " + "="*40)
    for c in res.get("citations", []):
        print(f"- {c.get('ref')} | {c.get('ref_he')} | {c.get('commentator')}")
