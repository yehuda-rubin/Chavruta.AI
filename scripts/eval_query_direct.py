import sys
from chavruta.pipeline.pipeline import ChavrutaPipeline
from chavruta.corpus.schema import Query, Intent
from chavruta.intents.llm_planner import classify_and_distill


def test_query(question_text):
    print("="*60)
    print(f"QUESTION: {question_text}")
    print("="*60)

    # 1. Distill & plan
    dist = classify_and_distill(question_text, history=[], intent="qa")
    print(f"Distilled Query: {dist.distilled_query}")
    print(f"Action: {dist.action}")

    # 2. Pipeline query
    from chavruta.config import Profile
    pipe = ChavrutaPipeline(Profile.from_env())

    q = Query(
        text=question_text,
        lang="he",
        intent=Intent.QA,
        distilled_text=dist.distilled_query,
        search_text=dist.distilled_query or question_text,
        rerank=True,
    )
    ans = pipe.ask(q)

    print("\n" + "-"*30 + " ANSWER " + "-"*30)
    print(ans.text)
    print("\n" + "-"*30 + " CITATIONS " + "-"*30)

    for c in ans.citations:
        print(f"• {c.ref} | {c.commentator_id or ''}")

if __name__ == "__main__":
    q_in = sys.argv[1] if len(sys.argv) > 1 else "האם מותר להשתמש בדוד שמש בשבת?"
    test_query(q_in)
