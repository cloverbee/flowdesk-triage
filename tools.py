"""
tools.py — The agent's three tools, as Claude Agent SDK tools.

A tool is two things:
  1. A schema — how the tool is DESCRIBED to the model, given via @tool's
     name/description/input_schema. The model chooses tools by reading
     these descriptions (Day 2: the description IS the interface). If your
     agent picks the wrong tool, look here first.
  2. A handler — what actually runs when the model asks for it.

The agent can only ever do what these functions allow. No tools, no hands.
Everything below runs through the Claude Agent SDK, which authenticates
with your logged-in Claude Code CLI session — no ANTHROPIC_API_KEY needed.
"""

import datetime
import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, create_sdk_mcp_server, query, tool

KB_DIR = Path(__file__).parent / "kb"
ESCALATION_LOG = Path(__file__).parent / "escalations.log"

CATEGORIES = ["billing", "login", "bug", "feature_request", "other"]


# ---------------------------------------------------------------------------
# Tool 1: classify_ticket
# ---------------------------------------------------------------------------
# Implemented as a SECOND, tightly-constrained agent call: a single-turn
# query with no tools of its own. This is deliberate: it demonstrates that
# a "tool" can itself run a model, and it previews model routing (Day 8) —
# a small, cheap call doing a small, cheap job. It spins up its own Claude
# Code subprocess, so it's slower than a raw API call — the tradeoff for
# needing no separate credential.

@tool(
    "classify_ticket",
    "Assigns a support ticket to one of five categories: billing, login, "
    "bug, feature_request, other. Call this first, once, with the full ticket text.",
    {"ticket_text": str},
)
async def classify_ticket(args: dict[str, Any]) -> dict[str, Any]:
    options = ClaudeAgentOptions(
        system_prompt=(
            "Classify the support ticket into exactly one category. "
            f"Answer with one word from this list and nothing else: {', '.join(CATEGORIES)}. "
            "billing = charges, refunds, invoices, plan prices. "
            "login = passwords, 2FA, being locked out, sign-in errors. "
            "bug = the product misbehaving, errors, data not saving or loading. "
            "feature_request = asking for something the product doesn't do. "
            "other = anything else, including account deletion, data export, security questions."
        ),
        tools=[],
        max_turns=1,
        strict_mcp_config=True,
    )

    answer = ""
    async for message in query(prompt=args["ticket_text"], options=options):
        if isinstance(message, ResultMessage) and message.result:
            answer = message.result.strip().lower()

    category = answer if answer in CATEGORIES else "other"
    return {"content": [{"type": "text", "text": category}]}


# ---------------------------------------------------------------------------
# Tool 2: search_kb
# ---------------------------------------------------------------------------
# A deliberately simple keyword search over the kb/ folder: score each
# article by how many of the query's words it contains, return the top two.
#
# Production retrieval uses embeddings and a vector database (Day 3,
# Topic 2). We use keyword scoring here so the whole package runs with no
# extra infrastructure — and so you can read every line of how retrieval
# happens. Swapping this function for an embedding search changes NOTHING
# about the agent loop. That is the point.

@tool(
    "search_kb",
    "Searches the Flowdesk support knowledge base and returns the most relevant "
    "articles. Use a short query of the key terms (e.g. 'duplicate charge refund'), "
    "not the whole ticket. May be called more than once with different queries.",
    {"query": str},
)
async def search_kb(args: dict[str, Any]) -> dict[str, Any]:
    query_words = set(re.findall(r"[a-z]+", args["query"].lower())) - {
        "the", "a", "an", "is", "are", "to", "of", "my", "i", "and", "for", "in", "on", "it",
    }

    scored = []
    for path in sorted(KB_DIR.glob("*.md")):
        text = path.read_text().lower()
        score = sum(text.count(w) for w in query_words)
        scored.append((score, path))

    scored.sort(reverse=True, key=lambda pair: pair[0])
    top = [path for score, path in scored[:2] if score > 0]

    if not top:
        text = "NO_RESULTS: no knowledge base article matched this query."
    else:
        parts = [f"--- ARTICLE: {path.name} ---\n{path.read_text().strip()}" for path in top]
        text = "\n\n".join(parts)

    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------------------
# Tool 3: escalate_to_human
# ---------------------------------------------------------------------------
# In this package, escalation writes to a log file. In production it would
# file a case in the ticketing system. Note what it does NOT do: it cannot
# email customers, refund money, or delete anything (Day 8: least privilege).

@tool(
    "escalate_to_human",
    "Hands the ticket to a human support agent. Use when the knowledge base does "
    "not cover the issue, or the ticket involves a legal threat, a security concern, "
    "possible data loss, or an extremely upset customer.",
    {"summary": str, "reason": str},
)
async def escalate_to_human(args: dict[str, Any]) -> dict[str, Any]:
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    entry = f"[{stamp}] ESCALATED — reason: {args['reason']}\n  summary: {args['summary']}\n"
    with open(ESCALATION_LOG, "a") as f:
        f.write(entry)
    return {
        "content": [
            {"type": "text", "text": "Escalated to a human agent. A summary has been filed."}
        ]
    }


# ---------------------------------------------------------------------------
# The in-process MCP server — what agent.py passes to ClaudeAgentOptions
# ---------------------------------------------------------------------------

TOOL_SERVER = create_sdk_mcp_server(
    name="flowdesk",
    version="1.0.0",
    tools=[classify_ticket, search_kb, escalate_to_human],
)

# Fully-qualified names (mcp__{server_name}__{tool_name}), for allowed_tools.
TOOL_NAMES = [
    "mcp__flowdesk__classify_ticket",
    "mcp__flowdesk__search_kb",
    "mcp__flowdesk__escalate_to_human",
]
