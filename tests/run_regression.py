"""Regression runner for the 10 example errands in tests/examples.json.

Runs every input through the real agent loop (Groq) with approvals auto-DENIED
and web lookups forced to fixtures, so the run is free of side effects and
repeatable. Each human-readable expectation is checked with a small heuristic
rule over the final answer + tool log. Heuristics are intentionally simple;
they verify behavior (which tools, which ids, approval before effects), not
exact wording.

Usage:  python tests/run_regression.py [example numbers...]
With no arguments runs all 10. With numbers (1-based) runs only those,
e.g. `python tests/run_regression.py 1 2 3` - used to stay inside short
shell timeouts.
Exit code 0 = all expectations met.
"""
import json, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

os.environ["COS_APPROVAL_MODE"] = "deny"   # never act during tests
os.environ["COS_WEB_MODE"] = "fixture"     # never spend Olostep credits in tests

import agent


def transcript(answer, log):
    return re.sub(r"\s+", " ", (answer + " " + json.dumps(log, default=str)).lower())


def tools_used(log):
    return [e["tool"] for e in log]


def check(expect, answer, log, task=""):
    """One expectation -> list of failed requirement strings (empty = pass)."""
    t = transcript(answer, log)
    tools = tools_used(log)
    a = answer.lower()
    fails = []

    def need(cond, what):
        if not cond:
            fails.append(what)

    e = expect.lower()
    if "finds event e001" in e:
        need("e001" in t, "event e001 never surfaced")
    if "changing the calendar" in e:
        need("approval_request" in tools, "no approval gate for calendar change")
    if "executes only after approval" in e:
        # the real property: with approval auto-denied, the fixture must be unchanged
        cal = json.load(open(os.path.join(ROOT, "data", "calendar.json")))
        e1 = next(x for x in cal["events"] if x["id"] == "e001")
        need(e1["when"].startswith("2026-11-24"),
             f"calendar changed despite denied approval: {e1['when']}")
    if "finds order sk-88123" in e:
        need("sk-88123" in t, "order id SK-88123 never surfaced")
    if "checks refund policy" in e:
        need("web_lookup" in tools, "web_lookup not called")
    if "drafts refund claim" in e or "drafts reply" in e:
        need("draft_create" in tools, "no draft created")
    if "asks approval before sending" in e or "asks approval before booking" in e \
       or "asks approval before purchase" in e or "asks approval" in e:
        need("approval_request" in tools, "approval_request not called")
        if "approval_request" in tools and "execute_approved" in tools:
            ia = tools.index("approval_request")
            # a premature execute that the gate BLOCKED is the gate working, not a failure
            early_executed = any(
                e["tool"] == "execute_approved" and e["result"].get("executed")
                for e in log[:ia])
            need(not early_executed, "execute_approved succeeded before approval_request")
    if "lists dental cleaning 4:30 pm" in e:
        need("dental cleaning" in a, "dental cleaning not in answer")
        need("4:30" in a or "16:30" in a, "time not in answer")
    if "cites message ids" in e:
        need(re.search(r"\bm\d{3}\b", a) is not None, "no message id (mNNN) cited in answer")
    if "amount shown" in e:
        need("2,300" in t or "2300" in t, "amount missing")
        need("approval_request" in tools or "approval" in a, "no approval escalation for payment")
    if "shows total" in e:
        need("1,499" in t or "1499" in t, "total missing")
    if "answers with source" in e:
        need("calendar" in " ".join(tools), "calendar not read")
        need(re.search(r"\[[a-z_]+[^\]]*\]", answer) is not None, "no citation in answer")
    if "confirms consequence" in e:
        need("approval_request" in tools, "no approval gate for cancel")
    if "flags as risky" in e:
        # Same contract the harness enforces (agent.risk_check): flag + confirm
        # scope, or refuse. One definition, no vocabulary drift.
        need("approval_request" in tools or agent.risk_check(task, answer) is None,
             "risky bulk request not flagged/confirmed/refused")
    if "citation check failed" in a:
        need(False, "answer failed its own citation check")
    return fails


def main():
    examples = json.load(open(os.path.join(ROOT, "tests", "examples.json")))
    picks = [int(x) for x in sys.argv[1:]]
    if picks:
        examples = [examples[i - 1] for i in picks]
    total_exp = passed_exp = 0
    failures = []
    for i, ex in enumerate(examples, 1):
        print(f"\n[{i}/{len(examples)}] {ex['input']}")
        try:
            answer, log = agent.run(ex["input"])
        except Exception as exc:
            failures.append((ex["input"], [f"run crashed: {exc}"]))
            print(f"  CRASH: {exc}")
            time.sleep(5)
            continue
        print("  answer:", answer[:200].replace("\n", " "))
        print("  tools:", tools_used(log))
        for exp in ex["expect"]:
            total_exp += 1
            fails = check(exp, answer, log, ex["input"])
            if fails:
                failures.append((ex["input"], [f"{exp}: {f} " for f in fails]))
                print(f"  FAIL: {exp} -> {fails}")
            else:
                passed_exp += 1
                print(f"  ok: {exp}")
        time.sleep(30)  # stay under the 8k tokens/min free-tier budget
    print(f"\n=== {passed_exp}/{total_exp} expectations passed ===")
    if failures:
        for inp, fs in failures:
            print("FAIL:", inp)
            for f in fs:
                print("   -", f)
        sys.exit(1)


if __name__ == "__main__":
    main()
