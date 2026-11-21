"""Chief-of-staff agent loop: plan -> tools -> check -> approval gate -> act -> cited report.

Model: any OpenAI-compatible chat endpoint (Groq by default), function-calling style
implemented via explicit JSON tool-call instructions so the loop stays provider-agnostic.
"""
import json, os, sys, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools_impl import TOOLS

API_KEY = os.environ.get("GROQ_API_KEY", "")
BASE_URL = os.environ.get("MODEL_BASE_URL", "https://api.groq.com/openai/v1")
MODEL = os.environ.get("MODEL_NAME", "openai/gpt-oss-120b")

SYSTEM = """You are a careful chief-of-staff agent for one user.
Rules you must always follow:
1. Plan first: write 2-4 steps before acting.
2. Use tools for facts. Never invent order ids, dates, addresses or policies.
3. Before ANY external effect (sending mail, booking, paying, cancelling), call
   approval_request with a plain summary and full details, then execute_approved.
   Creating drafts is fine without approval.
4. Money: always show the exact amount in the approval request.
5. Your final answer must cite the tool results it relies on, like [mail_read m001].
Reply with exactly one JSON object per turn:
{"thought": "...", "tool": "<name>", "args": {...}}  or
{"thought": "...", "final": "answer with citations"}"""

def chat(messages):
    body = json.dumps({
        "model": MODEL, "messages": messages,
        "temperature": 0.2, "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(BASE_URL + "/chat/completions", data=body, headers={
        "Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "User-Agent": "chief-of-staff-agent/0.1 (python requests)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return data["choices"][0]["message"]["content"]

def tool_manifest():
    return {name: {"args": args, "about": about} for name, (fn, args, about) in TOOLS.items()}

def check_report(report, tool_log):
    """Second-pass self-check: every bracketed citation must name a real tool call."""
    import re
    cited = set(re.findall(r"\[(\w+)([^\]]*)\]", report))
    real = {(t, "") for t in tool_log}
    bad = [c for c in cited if not any(c[0] == t for t, _ in real)]
    return bad

def run(task, max_steps=12):
    messages = [
        {"role": "system", "content": SYSTEM + "\nTools:\n" + json.dumps(tool_manifest(), indent=1)},
        {"role": "user", "content": task},
    ]
    tool_log = []
    for step in range(max_steps):
        raw = chat(messages)
        try:
            turn = json.loads(raw)
        except json.JSONDecodeError:
            messages.append({"role": "user", "content": "Reply with ONE valid JSON object only."})
            continue
        if "final" in turn:
            bad = check_report(turn["final"], [t for t, _ in tool_log])
            if bad:
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content":
                    f"Your answer cites {bad} which you never called. Fix or remove those citations."})
                continue
            return turn["final"], tool_log
        name, args = turn.get("tool"), turn.get("args", {})
        if name not in TOOLS:
            result = {"error": f"unknown tool {name}"}
        else:
            result = TOOLS[name][0](**args)
            tool_log.append((name, args))
        messages.append({"role": "assistant", "content": raw})
        messages.append({"role": "user", "content": "Tool result: " + json.dumps(result)[:1500]})
    return "Stopped: step limit reached without a finished answer.", tool_log

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "My ShopKart order never arrived. Get my money back."
    answer, log = run(task)
    print("\n=== ANSWER ===\n" + answer)
    print("\n=== TOOL LOG ===")
    for name, args in log:
        print(f"  {name} {json.dumps(args)[:100]}")
