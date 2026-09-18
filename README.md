# Flowdesk Triage Agent — Course Starter Package

A complete, minimal AI agent: a model, three tools, and a loop. This is the
reference project for the course. It runs on the Claude Agent SDK, so it
authenticates through your logged-in Claude Code CLI session — no
`ANTHROPIC_API_KEY` needed.

## Setup (10 minutes)

1. Python 3.10 or newer.
2. Install and log in to Claude Code, if you haven't already: `npm install -g
   @anthropic-ai/claude-code`, then `claude` and follow the login prompt.
3. `pip install -r requirements.txt` (installs `claude-agent-sdk` and `qdrant-client`).
4. Build the knowledge base index: `python build_index.py` — embeds every
   article in `kb/` into a local Qdrant collection on disk (`qdrant_data/`).
   The first run downloads a small embedding model (~130MB) from Hugging
   Face; after that it's fully offline. Re-run this any time `kb/` changes.
5. Test: `python agent.py` — you should watch it classify a ticket, search
   the knowledge base, and draft a reply.

## What's in the box

| File | What it is | Course day |
|---|---|---|
| `agent.py` | The agent loop. Read this first, top to bottom. | Day 1 |
| `tools.py` | The three tools and their schemas. | Day 2 |
| `kb/` | 12 support articles — the knowledge base the agent searches. | Day 3 |
| `build_index.py` | Embeds `kb/` into a local Qdrant collection. Run before `agent.py`/`eval.py`, and again after editing `kb/`. | Day 3 |
| `qdrant_data/` | Created at runtime by `build_index.py` — the on-disk vector index. Not committed; rebuild it instead. | Day 3 |
| `tickets.json` | 50 labeled test tickets (category + escalation labels). | Day 7 |
| `eval.py` | Runs the test set, prints your results table. | Day 7 |
| `escalations.log` | Created at runtime — where escalations land. | Day 4 |

## Reading order

1. `agent.py` — the loop. ~100 lines including comments. Everything else
   in the course is scaffolding around this file.
2. `tools.py` — schemas first (what the model reads), then the functions
   (what actually runs).
3. One or two articles in `kb/`, then run `python agent.py "your own ticket"`
   (or `python agent.py --random` to sample one from `tickets.json`) a few
   times and watch which tools it picks.
4. `eval.py` last — run `python eval.py 10` for a quick pass.

## Making it yours

- **Change the agent's behavior:** edit `SYSTEM_PROMPT` in `agent.py`.
  The escalation line lives there. This is most of agent development.
- **Change what it can do:** add a tool in `tools.py` — a function, a schema,
  one line in the dispatch table. The loop needs no changes.
- **Different project from the menu?** Same loop, your tools, your test data.
  Replace `kb/` with your documents and `tickets.json` with your cases.

## House rules (they will come up in interviews)

- The loop is capped at `MAX_TURNS` — every production agent bounds its loop.
- Tools have the narrowest powers that work: search reads, escalation logs,
  nothing emails customers or moves money.
- Ticket text is data, not instructions. See ticket 16 in the test set.
- Rerun `eval.py` after every change. The table is your compass.
- Qdrant's local mode is single-process, like SQLite — don't run
  `build_index.py` at the same time as `agent.py` or `eval.py`.
