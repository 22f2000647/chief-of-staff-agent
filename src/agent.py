"""Chief-of-staff agent loop: plan -> tools -> citation check -> approval gate -> cited report.

Model: any OpenAI-compatible chat endpoint (Groq by default), function-calling style
implemented via explicit JSON tool-call instructions so the loop stays provider-agnostic.

Citation contract: every factual claim in the final answer must carry a bracketed
citation naming the tool and the id of the record used, e.g. [mail_read m001] or
[calendar_find e001]. check_report() rejects citations to tools never called and
ids that never appeared in that tool's results, and rejects fact-bearing answers
with no citations at all.
"""
import json, os, re, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools_impl import TOOLS

API_KEY = os.environ.get("GROQ_API_KEY", "")
BASE_URL = os.environ.get("MODEL_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.environ.get("MODEL_NAME", "openai/gpt-oss-120b")

FACTUAL_TOOLS = {"mail_search", "mail_read", "calendar_list", "calendar_find", "web_lookup"}

SYSTEM = """You are a careful chief-of-staff agent for one user.
Rules you must always follow:
1. Plan first: write 2-4 steps before acting.
2. Use tools for facts. Never invent order ids, dates, addresses or policies.
   For an errand, always gather facts first (mail_search/mail_read for mail,
   calendar_list/calendar_find for schedule, web_lookup for policies), then
   draft, then ask approval. Never draft a claim about an order, event or
   policy you have not looked up in this run.
   Canonical flow for an errand like a refund chase:
   mail_search -> mail_read -> web_lookup (the vendor policy) -> draft_create
   -> approval_request -> execute_approved -> final answer with citations.
   Always create the draft BEFORE approval_request, and include the draft_id
   in the approval details so the human can review the exact text.
   Hard preconditions, checked every run:
   - approval_request for sending mail REQUIRES a draft_create earlier in this run.
   - approval_request for a booking REQUIRES restaurant_search (or the relevant
     options tool) earlier in this run; details must name the chosen option's
     id, time and party size. Pick a reasonable option from the results instead
     of asking the user to choose first.
   - approval_request for a cancellation REQUIRES the calendar event id (found
     via calendar_find/calendar_list this run) and the consequence stated in
     details (slot released, any fee). Never ask the user for information the
     fixtures already hold; route the decision through the gate.
   - A purchase/reorder request means: find the original item and price in
     mail (mail_search/mail_read), draft the reorder email to the vendor, then
     approval_request showing the exact total. "No purchase tool" is never an
     excuse to refuse - the draft + approval flow IS the purchase path.
   - A reschedule/move request means: find the event (calendar_find), then
     approval_request naming the event id and the old and new times, then
     execute_approved with action "calendar_update" and params
     {"event_id": ..., "new_when": "YYYY-MM-DDTHH:MM:SS+05:30"}. Approved
     calendar_update actions really change the calendar.
   - A draft about an order or refund REQUIRES mail_read of the order mail and
     web_lookup of the vendor policy earlier in this run.
   Skipping a precondition is a task failure even if the answer sounds right.
3. Before ANY external effect (sending mail, booking, paying, cancelling), call
   approval_request with a plain summary and full details, then execute_approved.
   Creating drafts is fine without approval.
4. Money: always show the exact amount in the approval request. For any
   payment request, call approval_request with the amount even if details are
   missing - note the gaps in details and let the human decide. Never handle
   money outside the approval queue, and never ask for details in chat instead
   of going through the gate.
5. Your final answer must cite the tool results it relies on. Citation format:
   [tool_name record_id], e.g. [mail_read m001], [calendar_find e001],
   [web_lookup shopkart_refund]. Only cite tools you actually called this run,
   and only ids that appeared in that tool's result.
Reply with exactly one JSON object per turn:
{"thought": "...", "tool": "<name>", "args": {...}}  or
{"thought": "...", "final": "answer with citations"}"""

def chat(messages):
    body = json.dumps({
        "model": MODEL, "messages": messages,
        "temperature": 0.2,
        "max_tokens": int(os.environ.get("COS_MAX_TOKENS", "2500")),
        "reasoning_effort": os.environ.get("COS_REASONING_EFFORT", "medium"),
    }).encode()
    import time, urllib.error
    for attempt in range(8):
        req = urllib.request.Request(BASE_URL + "/chat/completions", data=body, headers={
            "Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "chief-of-staff-agent/0.2 (python requests)"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)
            spacing = float(os.environ.get("COS_CALL_SPACING", "0") or 0)
            if spacing:
                time.sleep(spacing)
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 7:
                wait = int(e.headers.get("Retry-After", "0") or 0) or 15 * (attempt + 1)
                print(f"  [rate limited; retry {attempt + 1}/7 after {min(wait, 90)}s]",
                      file=sys.stderr, flush=True)
                time.sleep(min(wait, 90))
                continue
            raise

def tool_manifest():
    return {name: {"args": args, "about": about} for name, (fn, args, about) in TOOLS.items()}

def check_report(report, tool_log):
    """Second-pass citation enforcement over the final answer.

    A citation [tool id] is valid only if the tool was called this run AND (when
    an id is given) that id string appears in one of that tool's results. If any
    factual tool was used, the answer must contain at least one valid citation.
    Returns a list of problems (empty = pass).
    """
    problems = []
    cited = re.findall(r"\[([a-z_]+)(?:\s+([^\]]+))?\]", report)
    used = [e["tool"] for e in tool_log]
    for tool, ident in cited:
        if tool not in used:
            problems.append(f"cites [{tool}] but that tool was never called this run")
            continue
        if ident:
            ident = ident.strip()
            found = any(
                e["tool"] == tool and ident.lower() in json.dumps(e["result"], default=str).lower()
                for e in tool_log
            )
            if not found:
                problems.append(f"cites [{tool} {ident}] but no {tool} result contains '{ident}'")
    if set(used) & FACTUAL_TOOLS and not cited:
        problems.append("answer relies on tool facts but contains no [tool id] citation")
    # Action-claim enforcement: the answer may not claim a draft/approval/effect
    # whose tool call never happened. This is the core anti-hallucination check.
    low = report.lower()
    used_set = set(used)
    if re.search(r"draft (is |was )?(ready|created|prepared|awaiting)|i('ve| have) drafted|draft is awaiting", low) \
            and "draft_create" not in used_set:
        problems.append("claims a draft exists but draft_create was never called this run")
    if re.search(r"awaiting (your )?approval|waiting for (your )?approval|pending (your )?approval", low) \
            and "approval_request" not in used_set:
        problems.append("claims approval is pending but approval_request was never called this run")
    if re.search(r"has been sent|have sent|i sent|i've sent|email sent|message sent", low) \
            and "execute_approved" not in used_set:
        problems.append("claims something was sent but execute_approved was never called this run")
    return problems

RISKY_PATTERNS = [
    r"\bignore\b[^.]*\b(all|every)\b",   # ignore all/every ...
    r"\ball my mail\b",
    r"\bdelete (all|everything)\b",
    r"\bfor a (week|month|year)\b",       # long-lasting silence/change
    r"\bblock\b[^.]*\ball\b",
]

def risk_check(task, report):
    """Deterministic gate for broad or long-lasting requests.

    When the task asks for something sweeping (ignore all mail, delete
    everything, silence for a week), a compliant-sounding answer is a
    failure: the report must flag the risk and ask the user to confirm
    the exact scope, or refuse. Returns a problem string or None.
    """
    t = task.lower()
    if not any(re.search(p, t) for p in RISKY_PATTERNS):
        return None
    r = report.lower()
    flags = any(w in r for w in ("risk", "careful", "caution", "irreversible",
                                 "broad", "sweeping", "all your mail", "miss"))
    asks = ("?" in report) and any(w in r for w in ("confirm", "sure", "scope",
                                                    "exactly", "which", "clarif"))
    refuses = any(w in r for w in ("can't do", "cannot do", "won't do",
                                   "i refuse", "not something i"))
    if (flags and asks) or refuses:
        return None
    return "risky bulk request not flagged/confirmed/refused"

def parse_turn(raw):
    """Extract the first balanced JSON object from the model's reply.
    No response_format: Groq's json_object mode rejects gpt-oss output on this
    prompt, so we ask for JSON in the system prompt and parse leniently."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(raw)):
        c = raw[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None

def run(task, max_steps=14):
    messages = [
        {"role": "system", "content": SYSTEM + "\nTools:\n" + json.dumps(tool_manifest(), indent=1)},
        {"role": "user", "content": task},
    ]
    tool_log = []  # entries: {"tool", "args", "result"}
    citation_retries = 0
    for step in range(max_steps):
        raw = chat(messages)
        turn = parse_turn(raw)
        if turn is None:
            messages.append({"role": "user", "content": "Reply with ONE valid JSON object only."})
            continue
        if "final" in turn:
            problems = check_report(turn["final"], tool_log)
            risk = risk_check(task, turn["final"])
            if risk:
                problems = problems + [risk]
            if problems and citation_retries < 3:
                citation_retries += 1
                available = ", ".join(
                    f"[{e['tool']} {e['result'].get('id') or e['result'].get('draft_id') or ''}]".replace(" ]", "]")
                    if isinstance(e.get("result"), dict) else f"[{e['tool']}]"
                    for e in tool_log[-4:]) or "(no tools called)"
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                    "Review failed: " + "; ".join(problems) +
                    ". Rewrite the answer: cite only tools you actually called and ids from their results, "
                    "and if the request is broad or long-lasting, flag the risk and ask the user to "
                    "confirm the exact scope (or refuse) instead of complying. "
                    "Recent real calls you can cite: " + available})
                continue
            if problems:
                return ("[citation check failed after retries: " + "; ".join(problems) +
                        "]\n\n" + turn["final"]), tool_log
            return turn["final"], tool_log
        name, args = turn.get("tool"), turn.get("args", {})
        if name not in TOOLS:
            result = {"error": f"unknown tool {name}"}
        else:
            result = None
            if name == "draft_create":
                text = (str(args.get("subject", "")) + " " + str(args.get("body", ""))).lower()
                looked_up = any(e["tool"] == "web_lookup" for e in tool_log)
                if any(w in text for w in ("refund", "return", "claim", "warranty")) and not looked_up:
                    result = {"error": "precondition failed: look up the vendor's refund/return "
                                       "policy with web_lookup before drafting a claim, and cite the "
                                       "policy in the draft. The vendor's own mail is not the policy."}
            if result is None and name == "approval_request":
                summary = str(args.get("action_summary", "")).lower()
                drafted = any(e["tool"] == "draft_create" for e in tool_log)
                if any(w in summary for w in ("send", "email", "mail", "reply")) and not drafted:
                    result = {"error": "precondition failed: create the text first with "
                                       "draft_create, then re-request approval naming the draft_id. "
                                       "The human reviews exact words, not a summary."}
            if result is None:
                result = TOOLS[name][0](**args)
                tool_log.append({"tool": name, "args": args, "result": result})
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": "Tool result: " + json.dumps(result, default=str)[:1500]})
    return "Stopped: step limit reached without a finished answer.", tool_log

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "My ShopKart order never arrived. Get my money back."
    answer, log = run(task)
    print("\n=== ANSWER ===\n" + answer)
    print("\n=== TOOL LOG ===")
    for e in log:
        print(f"  {e['tool']} {json.dumps(e['args'])[:100]}")
