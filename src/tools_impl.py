"""Tool implementations for the chief-of-staff agent.

Tools are split in two classes:
- read/draft tools (mail_search, mail_read, calendar_list, calendar_find,
  web_lookup, draft_create): safe, also exposed over MCP (src/mcp_server.py).
- effect tools (approval_request, execute_approved): every external effect
  (send, book, pay, cancel) must pass the human approval queue first.

Approval mode: COS_APPROVAL_MODE=interactive (default, asks on stdin),
approve or deny (non-interactive, used by the regression runner).
Web mode: COS_WEB_MODE=fixture forces fixture policy data even when
OLOSTEP_API_KEY is set; otherwise a set key makes web_lookup live (Olostep).
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
    q = [w[3:] if w.startswith("is:") else w for w in query.lower().split()]
    unread_only = "unread" in q
    words = [w for w in q if w not in ("unread", "mail", "mails", "email", "emails", "inbox")]
    out = []
    for m in _load("mailbox.json")["messages"]:
        hay = (m["from"] + " " + m["subject"] + " " + m["body"]).lower()
        if unread_only and not m.get("unread"):
            continue
        if words and not any(w in hay for w in words):
            continue
        out.append({"id": m["id"], "from": m["from"], "date": m["date"],
                    "subject": m["subject"], "unread": m.get("unread", False),
                    "snippet": m["body"][:140]})
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
    """List all sample calendar events."""
    ev = _load("calendar.json")["events"]
    _audit({"tool": "calendar_list", "count": len(ev)})
    return ev

MONTHS = ["january","february","march","april","may","june","july",
          "august","september","october","november","december"]

def _event_hay(e):
    """Searchable text for one event: title, place, aliases and the date written
    every way a user might type it ('24 november', 'nov 24', '2026-11-24')."""
    parts = [e["title"], e.get("where", ""), " ".join(e.get("aliases", [])), e.get("when", "")]
    try:
        d = time.strptime(e["when"][:10], "%Y-%m-%d")
        parts += [f"{d.tm_mday} {MONTHS[d.tm_mon-1]}", f"{MONTHS[d.tm_mon-1]} {d.tm_mday}",
                  f"{d.tm_mday} {MONTHS[d.tm_mon-1][:3]}", f"{MONTHS[d.tm_mon-1][:3]} {d.tm_mday}"]
    except (ValueError, KeyError, IndexError):
        pass
    return " ".join(parts).lower()

def calendar_find(query: str):
    """Find calendar events matching a keyword (title, place, aliases or date), e.g. 'dentist'
    or '24 november'. If this returns nothing, call calendar_list to see all events before giving up."""
    q = query.lower().split()
    out = []
    for e in _load("calendar.json")["events"]:
        hay = _event_hay(e)
        if any(w in hay for w in q):
            out.append(e)
    _audit({"tool": "calendar_find", "query": query, "hits": len(out)})
    return out

def restaurant_search(query: str):
    """Search sample restaurants by cuisine, area or name. Returns matches with tonight's slots."""
    q = query.lower().split()
    out = []
    for r in _load("restaurants.json")["restaurants"]:
        hay = (r["name"] + " " + r["cuisine"] + " " + r["area"]).lower()
        if not q or any(w in hay for w in q):
            out.append(r)
    if not out and q:
        # generic words like 'table for two tonight' match nothing; offer everything
        out = list(_load("restaurants.json")["restaurants"])
    _audit({"tool": "restaurant_search", "query": query, "hits": len(out)})
    return out

def web_lookup(url_or_query: str):
    """Look up a public web page (refund policy, opening hours).

    Fixture mode (default without a key, or COS_WEB_MODE=fixture) returns
    data/policies.json. Live mode calls the Olostep scrape API (1 credit/call).
    """
    key = os.environ.get("OLOSTEP_API_KEY")
    live = bool(key) and os.environ.get("COS_WEB_MODE", "live") != "fixture"
    _audit({"tool": "web_lookup", "target": url_or_query, "live": live})
    if not live:
        return {"fixture": True, "source": "data/policies.json",
                "result": _load("policies.json").get("shopkart_refund")}
    import urllib.request
    req = urllib.request.Request(
        "https://api.olostep.com/v1/scrapes",
        data=json.dumps({"url_to_scrape": url_or_query}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "chief-of-staff-agent/0.1"})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = json.load(r)
    res = data.get("result") or {}
    return {"source": url_or_query,
            "markdown": (res.get("markdown_content") or "")[:4000],
            "status": (res.get("page_metadata") or {}).get("status_code"),
            "credits_used": data.get("credits_consumed")}

def draft_create(to: str, subject: str, body: str):
    """Create (not send) a draft message. Returns a draft id for the approval queue."""
    did = "d" + uuid.uuid4().hex[:6]
    _audit({"tool": "draft_create", "to": to, "subject": subject, "draft_id": did})
    return {"draft_id": did, "to": to, "subject": subject, "body": body, "state": "draft"}

def approval_request(action_summary: str, details: dict):
    """STOP POINT. Every external action (send, book, pay, cancel) must pass through here.
    The human sees the summary and details and must approve before execution.
    Money actions must include the exact amount in details."""
    mode = os.environ.get("COS_APPROVAL_MODE", "interactive")
    if mode == "interactive":
        print("\n=== APPROVAL REQUIRED ===")
        print(action_summary)
        print(json.dumps(details, indent=2))
        ans = input("Approve? [y/N] ").strip().lower()
        approved = ans == "y"
    else:
        approved = mode == "approve"
        print(f"[approval queue: auto-{mode}] {action_summary}")
    _audit({"tool": "approval_request", "action": action_summary,
            "approved": approved, "details": details})
    return {"approved": approved, "mode": mode}

def _save(name, data):
    with open(os.path.join(ROOT, "data", name), "w") as f:
        json.dump(data, f, indent=2)

def _apply_effect(action, params):
    """Real fixture mutation for approved actions. Returns (applied, detail)."""
    if action == "calendar_update":
        cal = _load("calendar.json")
        for e in cal["events"]:
            if e["id"] == params.get("event_id"):
                if params.get("new_when"):
                    e["when"] = params["new_when"]
                if params.get("note"):
                    e["note"] = params["note"]
                _save("calendar.json", cal)
                return True, {"updated_event": e}
        return False, {"error": f"no event {params.get('event_id')}"}
    return False, {"simulated": True}

def execute_approved(action: str, params: dict, approval: dict):
    """Runs an action only if the approval queue approved it.
    Approved calendar_update actions really change the fixture calendar (so the
    demo shows an actual effect); anything else is simulated."""
    if not approval.get("approved"):
        _audit({"tool": "execute_approved", "action": action, "blocked": True})
        return {"executed": False, "reason": "not approved"}
    applied, detail = _apply_effect(action, params)
    _audit({"tool": "execute_approved", "action": action, "params": params, "applied": applied})
    return {"executed": True, "action": action, "applied_to_fixture": applied, **detail}

TOOLS = {
    "mail_search": (mail_search, {"query": "string"}, "Search the sample mailbox"),
    "mail_read": (mail_read, {"message_id": "string"}, "Read one mail by id"),
    "calendar_list": (calendar_list, {}, "List calendar events"),
    "calendar_find": (calendar_find, {"query": "string"}, "Find calendar events by keyword"),
    "restaurant_search": (restaurant_search, {"query": "string"}, "Search sample restaurants (name/cuisine/area; empty lists all)"),
    "web_lookup": (web_lookup, {"url_or_query": "string"}, "Fetch a public web page/policy"),
    "draft_create": (draft_create, {"to": "string", "subject": "string", "body": "string"}, "Create a draft (never sends)"),
    "approval_request": (approval_request, {"action_summary": "string", "details": "object"}, "Ask the human before any external action"),
    "execute_approved": (execute_approved, {"action": "string", "params": "object", "approval": "object"}, "Execute only what was approved"),
}
