import sys; sys.path.insert(0, ".")
from src.rag_pipeline import ChavrutaPipeline
p = ChavrutaPipeline()

tests = [
    ("What does Rashi say about the creation of light?",          "rashi"),
    ("What is the difference between Rashi and Ramban on Genesis?","comparison"),
    ("What does Ramban say about Abraham?",                        "ramban"),
    ("What is written in the Torah about Shabbat?",               "chumash"),
    ("Why did God create the world?",                             "general"),
    ('מה אומר רש"י על בריאת האור?',                               "rashi"),
    ('מה ההבדל בין רש"י לרמב"ן?',                                 "comparison"),
]

print(f"{'intent':12} {'expected':12} {'types'}")
print("-" * 60)
ok = 0
for q, expected in tests:
    intent = p._detect_intent(q)
    chunks = p.retrieve(q)
    types  = [c["meta"]["chunk_type"] for c in chunks]
    match  = "✅" if intent == expected else "❌"
    print(f"{match} [{intent:10}] [{expected:10}] {types}")
    print(f"    {q[:55]}")
    if intent == expected:
        ok += 1

print(f"\nדיוק: {ok}/{len(tests)}")
