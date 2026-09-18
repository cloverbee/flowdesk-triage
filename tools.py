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

import atexit
import datetime
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, create_sdk_mcp_server, query, tool
from qdrant_client import QdrantClient, models

ESCALATION_LOG = Path(__file__).parent / "escalations.log"

CATEGORIES = ["billing", "login", "bug", "feature_request", "other"]

# Must match build_index.py — that script is what populates this collection.
QDRANT_PATH = Path(__file__).parent / "qdrant_data"
KB_COLLECTION = "flowdesk_kb"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
KB_SCORE_THRESHOLD = 0.55  # cosine similarity below this: treat as "no relevant article"
# Calibrated against this KB: genuine matches score ~0.7-0.85, unrelated
# articles top out ~0.45-0.49 on off-topic queries. Retune if kb/ grows —
# eval.py's escalation-accuracy column is the signal to watch.

_qdrant = QdrantClient(path=str(QDRANT_PATH))
atexit.register(_qdrant.close)  # local mode holds a file lock; close it before __del__ races shutdown


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
# Semantic retrieval: embed the query, search a local Qdrant collection built
# by build_index.py, return the top two articles above a relevance floor.
# Embeddings run through FastEmbed's local ONNX models — no server, no API
# key. Swapping this function's implementation changes NOTHING about the
# agent loop (Day 3, Topic 2) — that's still the point.

@tool(
    "search_kb",
    "Searches the Flowdesk support knowledge base and returns the most relevant "
    "articles. Use a short query of the key terms (e.g. 'duplicate charge refund'), "
    "not the whole ticket. May be called more than once with different queries.",
    {"query": str},
)
async def search_kb(args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = _qdrant.query_points(
            collection_name=KB_COLLECTION,
            query=models.Document(text=args["query"], model=EMBED_MODEL),
            limit=2,
            score_threshold=KB_SCORE_THRESHOLD,
        )
    except Exception as exc:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"KB index unavailable ({exc}). Run `python build_index.py` first.",
                }
            ],
            "is_error": True,
        }

    if not result.points:
        text = "NO_RESULTS: no knowledge base article matched this query."
    else:
        parts = [
            f"--- ARTICLE: {point.payload['filename']} ---\n{point.payload['text']}"
            for point in result.points
        ]
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
