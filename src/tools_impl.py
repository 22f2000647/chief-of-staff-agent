"""Tool implementations for the chief-of-staff agent.

Day-one version: direct Python functions over synthetic fixtures.
Next iteration: expose these as an MCP server so any MCP client can call them.
All external-effect actions go through the approval queue first.
"""
import json, os, time, uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(ROOT, "audit.log")

def _audit(entry):
    entry = dict(entry); entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(AUDIT, "a") as f:
        f.write(json.dumps(entry) + "\n")

def _load(name):
    with open(os.path.join(ROOT, "data", name)) as f:
        return json.load(f)

def mail_search(query: str):
    """Keyword search over the sample mailbox. Returns matching message ids + snippets."""
    q = query.lower().split()
    out = []
    for m in _load("mailbox.json")["messages"]:
        hay = (m["from"] + " " + m["subject"] + " " + m["body"]).lower()
        if any(w in hay for w in q):
            out.append({"id": m["id"], "from": m["from"], "date": m["date"],
                        "subject": m["subject"], "snippet": m["body"][:140]})
    _audit({"tool": "mail_search", "query": query, "hits": len(out)})
    return out

def mail_read(message_id: str):
    """Read one full message by id."""
    for m in _load("mailbox.json")["messages"]:
        if m["id"] == message_id:
            _audit({"tool": "mail_read", "id": message_id})
            return m
    return {"error": f"no message {message_id}"}

def calendar_list():
    """List sample calendar events."""
    ev = _load("calendar.json")["events"]
    _audit({"tool": "calendar_list", "count": len(ev)})
    return ev

def web_lookup(url_or_query: str):
    """Look up a public web page (refund policy, opening hours) via Olostep.

    Returns fixture data until OLOSTEP_API_KEY is set; then calls the live API.
    """
    key = os.environ.get("OLOSTEP_API_KEY")
    _audit({"tool": "web_lookup", "target": url_or_query, "live": bool(key)})
    if not key:
        return {"fixture": True, "source": "data/policies.json",
                "result": _load("policies.json").get("shopkart_refund")}
    import urllib.request
    req = urllib.request.Request(
        "https://api.olostep.com/v1/scrapes",
        data=json.dumps({"url_to_scrape": url_or_query}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def draft_create(to: str, subject: str, body: str):
    """Create (not send) a draft message. Returns a draft id for the approval queue."""
    did = "d" + uuid.uuid4().hex[:6]
    _audit({"tool": "draft_create", "to": to, "subject": subject, "draft_id": did})
    return {"draft_id": did, "to": to, "subject": subject, "body": body, "state": "draft"}

def approval_request(action_summary: str, details: dict):
    """STOP POINT. Every external action (send, book, pay, cancel) must pass through here.
    The human sees the summary and details and must approve before execution."""
    print("\n=== APPROVAL REQUIRED ===")
    print(action_summary)
    print(json.dumps(details, indent=2))
    ans = input("Approve? [y/N] ").strip().lower()
    approved = ans == "y"
    _audit({"tool": "approval_request", "action": action_summary,
            "approved": approved, "details": details})
    return {"approved": approved}

def execute_approved(action: str, params: dict, approval: dict):
    """Runs an action only if the approval queue approved it. Simulated effects on day one."""
    if not approval.get("approved"):
        _audit({"tool": "execute_approved", "action": action, "blocked": True})
        return {"executed": False, "reason": "not approved"}
    _audit({"tool": "execute_approved", "action": action, "params": params})
    return {"executed": True, "action": action, "simulated": True}

TOOLS = {
    "mail_search": (mail_search, {"query": "string"}, "Search the sample mailbox"),
    "mail_read": (mail_read, {"message_id": "string"}, "Read one mail by id"),
    "calendar_list": (calendar_list, {}, "List calendar events"),
    "web_lookup": (web_lookup, {"url_or_query": "string"}, "Fetch a public web page/policy"),
    "draft_create": (draft_create, {"to": "string", "subject": "string", "body": "string"}, "Create a draft (never sends)"),
    "approval_request": (approval_request, {"action_summary": "string", "details": "object"}, "Ask the human before any external action"),
    "execute_approved": (execute_approved, {"action": "string", "params": "object", "approval": "object"}, "Execute only what was approved"),
}
