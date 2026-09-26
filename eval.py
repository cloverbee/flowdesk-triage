"""
eval.py — Run the agent against the labeled test set and print the results table.

This is the Day 7 machinery: a fixed test set, objective checks, and the
table that goes in your final demo. Run it after every change you make to
the agent (Day 7: regression — fixes break other things quietly).

Usage:
    python eval.py           # run all 50 tickets (a few minutes, costs a few cents)
    python eval.py 10        # run only the first 10 (quick check while iterating)
    python eval.py --tickets tickets_grafana.json   # Grafana set; needs SCENARIO=sync_outage

After each run, read at least five failures end to end in eval_traces.json
before changing anything. The score says how bad; the traces say why.
"""

import json
import sys
from pathlib import Path

from agent import run_agent, MODEL, GRAFANA_ENABLED, GRAFANA_TOOL_NAMES
from report import write_html_report

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


GRAFANA_TOOLS = {name.rsplit("__", 1)[-1] for name in GRAFANA_TOOL_NAMES}
INCIDENT_PHRASE = "this is a known issue"  # the sentence kb/active-incidents.md tells the agent to use


def grafana_checks(ticket: dict, result: dict) -> dict:
    """Optional per-ticket checks, used by tickets_grafana.json. A check only
    runs when the ticket carries its expect_* / reply_must_not_contain field."""
    checks = {}
    if "expect_grafana_check" in ticket:
        did = any(call["tool"] in GRAFANA_TOOLS for call in result["trace"])
        checks["grafana_check_correct"] = did == ticket["expect_grafana_check"]
    if "expect_incident_notice" in ticket:
        did = INCIDENT_PHRASE in result["final_message"].lower()
        checks["incident_notice_correct"] = did == ticket["expect_incident_notice"]
    if "reply_must_not_contain" in ticket:
        reply = result["final_message"].lower()
        checks["no_leak_correct"] = not any(s.lower() in reply for s in ticket["reply_must_not_contain"])
    return checks


def _truncate(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def print_results_table(rows: list[dict]) -> None:
    """Per-ticket expected-vs-actual table — the client-facing artifact."""
    TICKET_W = 42

    def cat_col(r):
        return f"{r['expected_category']} -> {r['predicted_category']}"

    def esc_col(r):
        exp = "escalate" if r["should_escalate"] else "reply"
        got = "escalate" if r["did_escalate"] else "reply"
        return f"{exp} -> {got}"

    id_w = max(2, max(len(str(r["id"])) for r in rows))
    cat_w = max(len("CATEGORY (expected -> actual)"), max(len(cat_col(r)) for r in rows))
    esc_w = max(len("ESCALATION (expected -> actual)"), max(len(esc_col(r)) for r in rows))

    header = (
        f"{'ID':<{id_w}}  {'TICKET':<{TICKET_W}}  "
        f"{'CATEGORY (expected -> actual)':<{cat_w}}  "
        f"{'ESCALATION (expected -> actual)':<{esc_w}}  PASS"
    )
    print(header)
    print("-" * len(header))
    for r in rows:
        passed = r["category_correct"] and r["escalation_correct"]
        print(
            f"{r['id']:<{id_w}}  {_truncate(r['ticket'], TICKET_W):<{TICKET_W}}  "
            f"{cat_col(r):<{cat_w}}  {esc_col(r):<{esc_w}}  {'✓' if passed else '✗'}"
        )


def main(limit: int | None = None, tickets_path: Path = TICKETS) -> None:
    tickets = json.loads(tickets_path.read_text())
    if limit:
        tickets = tickets[:limit]

    rows = []
    errors = []  # tickets whose run crashed (network, SDK, Docker) — skipped, not scored
    total_in, total_out = 0, 0

    for t in tickets:
        print(f"[{t['id']:>2}/{len(tickets)}] running...", flush=True)
        try:
            result = run_agent(t["text"], verbose=False)
        except Exception as exc:
            print(f"  ERROR, skipping ticket {t['id']}: {exc}", flush=True)
            errors.append({"id": t["id"], "error": str(exc)})
            continue

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
            **grafana_checks(t, result),
        })
        total_in += result["usage"].get("input_tokens", 0)
        total_out += result["usage"].get("output_tokens", 0)

        # Save after every ticket, so a crash late in the run keeps what finished.
        TRACES_OUT.write_text(json.dumps(rows, indent=2))

    if not rows:
        raise SystemExit(f"Every ticket errored — nothing to score. First error: {errors[0]['error']}")

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
    print_results_table(rows)
    print("=" * 52)
    print(f"Category accuracy:      {cat_right}/{n}  ({cat_right / n:.0%})")
    print(f"Escalation decisions:   {esc_right}/{n}  ({esc_right / n:.0%})")
    print(f"  missed escalations:   {missed_esc or 'none'}   <- read these first")
    print(f"  unnecessary escalations: {extra_esc or 'none'}")
    if errors:
        print(f"Errored, not scored:    {[e['id'] for e in errors]}   <- rerun these; see the log above")
    print(f"Total cost:             ${cost:.3f}   (${cost / n:.4f} per run)")
    print(f"Tokens:                 {total_in:,} in / {total_out:,} out")
    print(f"Grafana:                {'on' if GRAFANA_ENABLED else 'off (no grafana/.env)'}")
    for key, label in [
        ("grafana_check_correct", "Grafana checked when it should"),
        ("incident_notice_correct", "Incident notice right"),
        ("no_leak_correct", "No internal data in reply"),
    ]:
        scored = [r for r in rows if key in r]
        if scored:
            right = sum(r[key] for r in scored)
            wrong = [r["id"] for r in scored if not r[key]]
            print(f"{label + ':':<33}{right}/{len(scored)}   failed: {wrong or 'none'}")
    print("=" * 52)

    TRACES_OUT.write_text(json.dumps(rows, indent=2))
    print(f"\nFull traces written to {TRACES_OUT.name} — read five failures before changing anything.")

    report_path = write_html_report(rows, MODEL, cost)
    print(f"HTML report written to {report_path.name} — open it in a browser to share.")

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
    args = sys.argv[1:]
    tickets_path = TICKETS
    if "--tickets" in args:
        i = args.index("--tickets")
        tickets_path = Path(args[i + 1])
        del args[i : i + 2]
    limit = int(args[0]) if args else None
    main(limit, tickets_path)
