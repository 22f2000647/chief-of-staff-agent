# Chief-of-Staff Agent

**One sentence:** A chief-of-staff agent that takes one everyday errand in plain words - starting with chasing a refund - plans the steps, does the work over your (sample) mail, calendar and the web, asks your approval before anything external happens, and reports back with proof.

Built for Homingo Hack Days Edition 01, Agents track, statement A3 "A personal staff for everyone".

## What it does

- Takes an errand in plain language ("my order never arrived, get my money back").
- Plans the steps, then executes them with tools: sample mailbox, sample calendar, live web data.
- Every external action (send, book, pay) stops at an approval queue - nothing happens without a human yes.
- Every claim in its final report carries a source it checked itself.

Runs on open/sample data only. No real personal data is in this repository.

## AI tools, models and libraries

- Model: openai/gpt-oss-120b via Groq (free tier) - planning, drafting, checking.
- Web data: Olostep API (Homingo partner credits).
- Agent tools: Model Context Protocol (MCP) server exposing mailbox/calendar/web/approval tools.
- Language: Python 3.

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and fill in your own keys (never commit `.env`).
4. `python src/agent.py "My ShopKart order never arrived. Get my money back"`
5. MCP server for any MCP client: `python src/mcp_server.py` (stdio)

## Repo layout

- `src/` - agent loop (`agent.py`), tools (`tools_impl.py`), MCP server (`mcp_server.py`, read/draft tools only - acting requires the approval queue in the agent).
- `data/` - synthetic sample mailbox/calendar fixtures.
- `tests/` - example inputs rerun after every significant change.
