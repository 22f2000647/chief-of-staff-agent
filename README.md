# Chief-of-Staff Agent

One sentence: A chief-of-staff agent that takes one everyday errand in plain words - starting with chasing a refund - plans the steps, does the work over your (sample) mail, calendar and the web, asks your approval before anything external happens, and reports back with proof.

Built for Homingo Hack Days, Edition 01 - Agents track ("A personal staff for everyone").

## Why this is different

Most demo agents will happily say they sent the email. This one cannot:

- **Approval gate in the harness, not the prompt.** `approval_request` /
  `execute_approved` are enforced by the agent loop: a send approval without a
  prior `draft_create` is rejected by the runner itself, a refund claim without
  a prior `web_lookup` of the vendor policy is rejected, money requests always
  route through the queue with the exact amount. The model cannot skip the gate
  by phrasing its way around it.
- **Citation checking.** Every factual claim in the final report must carry a
  `[tool record_id]` citation; a second pass verifies each citation against the
  tool calls and results that actually happened in that run. Made-up ids fail.
- **Audit log.** Every tool call lands in `audit.log` with a timestamp.

## Errands covered (synthetic fixtures)

1. Refund chase (mail + web policy + draft + approval) - the deep one
2. Calendar questions and appointment replies/cancellations
3. Restaurant booking over sample data, approval before booking
4. Payment requests: always escalated to the approval queue with the amount
5. Risky bulk requests: flagged or refused, never silently done

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY (free at console.groq.com); OLOSTEP_API_KEY optional
python src/agent.py "My ShopKart order never arrived. Get my money back"
```

MCP server for any MCP client: `python src/mcp_server.py` (stdio) - exposes only
read/draft tools; acting stays behind the agent's approval queue.

## Test

```bash
python tests/run_regression.py        # all 10 example errands
python tests/run_regression.py 1 4    # a subset
```

The runner executes the real agent loop against the live model with approvals
auto-denied and web lookups forced to fixtures, then checks each expectation in
`tests/examples.json` (heuristic behavioral checks: which tools ran, in what
order, with which ids and amounts).

## Stack

- Model: Groq `openai/gpt-oss-120b` via the OpenAI-compatible chat API
- Web lookups: Olostep scrape API (fixture mode when no key / in tests)
- MCP: FastMCP
- No frameworks beyond that on purpose: the agent loop is ~150 readable lines.

## Layout

- `src/agent.py` - the loop: plan -> tools -> citation check -> approval gate -> cited report
- `src/tools_impl.py` - tools over synthetic fixtures (mail, calendar, restaurants, web, drafts, approval queue)
- `src/mcp_server.py` - MCP exposure of the read/draft tools
- `data/` - synthetic fixtures (no real personal data)
- `tests/examples.json` + `tests/run_regression.py` - the regression set
- `audit.log` - append-only tool audit trail (gitignored, created at runtime)

## Honest limits

- Effects are simulated: "sending" the approved email prints what would happen.
- Fixtures are tiny by design; the point is the control flow, not the data.
- Model behavior varies run to run; the harness preconditions and citation
  checker are what make the safety claims hold anyway.
- The risk gate is deterministic wording detection over the request and the
  answer. It catches the sweeping-request shapes it knows (ignore all, delete
  everything, silence for a week) and its coverage is limited to those shapes;
  it is an observed guardrail, not a proof of safe behavior.
- Regression runs are rate-limited by the free tier: one full 11-example suite
  costs roughly the whole 200k tokens/day allowance on openai/gpt-oss-120b, so
  a full suite is a once-a-day measurement. COS_CALL_SPACING,
  COS_REASONING_EFFORT and COS_MAX_TOKENS tune cost without changing defaults.
