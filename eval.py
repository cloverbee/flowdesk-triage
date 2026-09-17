"""
eval.py — Run the agent against the labeled test set and print the results table.

This is the Day 7 machinery: a fixed test set, objective checks, and the
table that goes in your final demo. Run it after every change you make to
the agent (Day 7: regression — fixes break other things quietly).

Usage:
    python eval.py           # run all 50 tickets (a few minutes, costs a few cents)
    python eval.py 10        # run only the first 10 (quick check while iterating)

After each run, read at least five failures end to end in eval_traces.json
before changing anything. The score says how bad; the traces say why.
"""

import json
import sys
from pathlib import Path

from agent import run_agent, MODEL

TICKETS = Path(__file__).parent / "tickets.json"
TRACES_OUT = Path(__file__).parent / "eval_traces.json"

# Price per million tokens for the model in use. CHECK CURRENT PRICING and
# update these two numbers — prices change, and quoting a stale cost per run
# in a demo is a bad look.
PRICE_PER_M_INPUT = 1.00
PRICE_PER_M_OUTPUT = 5.00


def infer_category(result: dict) -> str | None:
    """Pull the category the agent decided on out of its tool-call trace."""
    for call in result["trace"]:
        if call["tool"] == "classify_ticket":
            return call["result"]
    return None


def main(limit: int | None = None) -> None:
    tickets = json.loads(TICKETS.read_text())
    if limit:
        tickets = tickets[:limit]

    rows = []
    total_in, total_out = 0, 0

    for t in tickets:
        print(f"[{t['id']:>2}/{len(tickets)}] running...", flush=True)
        result = run_agent(t["text"], verbose=False)

        predicted_category = infer_category(result)
        rows.append({
            "id": t["id"],
            "ticket": t["text"],
            "expected_category": t["category"],
            "predicted_category": predicted_category,
            "category_correct": predicted_category == t["category"],
            "should_escalate": t["should_escalate"],
            "did_escalate": result["escalated"],
            "escalation_correct": result["escalated"] == t["should_escalate"],
            "final_message": result["final_message"],
            "trace": result["trace"],
        })
        total_in += result["usage"].get("input_tokens", 0)
        total_out += result["usage"].get("output_tokens", 0)

    # ---------------- objective checks ----------------
    n = len(rows)
    cat_right = sum(r["category_correct"] for r in rows)
    esc_right = sum(r["escalation_correct"] for r in rows)
    missed_esc = [r["id"] for r in rows if r["should_escalate"] and not r["did_escalate"]]
    extra_esc = [r["id"] for r in rows if r["did_escalate"] and not r["should_escalate"]]

    cost = (total_in / 1e6) * PRICE_PER_M_INPUT + (total_out / 1e6) * PRICE_PER_M_OUTPUT

    # ---------------- the results table ----------------
    print("\n" + "=" * 52)
    print(f"RESULTS  ({n} tickets, model: {MODEL})")
    print("=" * 52)
    print(f"Category accuracy:      {cat_right}/{n}  ({cat_right / n:.0%})")
    print(f"Escalation decisions:   {esc_right}/{n}  ({esc_right / n:.0%})")
    print(f"  missed escalations:   {missed_esc or 'none'}   <- read these first")
    print(f"  unnecessary escalations: {extra_esc or 'none'}")
    print(f"Total cost:             ${cost:.3f}   (${cost / n:.4f} per run)")
    print(f"Tokens:                 {total_in:,} in / {total_out:,} out")
    print("=" * 52)

    TRACES_OUT.write_text(json.dumps(rows, indent=2))
    print(f"\nFull traces written to {TRACES_OUT.name} — read five failures before changing anything.")

    # ---------------- YOUR EXTENSION: LLM as judge ----------------
    # The checks above are objective: category and escalation have labeled
    # right answers. Reply QUALITY does not — is the drafted reply accurate,
    # grounded in the KB article, and appropriate in tone?
    #
    # Day 7, Topic 2 covers the technique. Your task:
    #   1. Write a judge prompt: give a model the ticket, the KB article(s)
    #      from the trace, the final_message, and a short rubric.
    #   2. Ask for a 1-5 score and a one-line reason.
    #   3. Add the average score to the table above, and spot-check five of
    #      the judge's grades yourself before trusting it.
    #
    # def judge_reply(ticket: str, kb_context: str, reply: str) -> tuple[int, str]:
    #     ...


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit)
