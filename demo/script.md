# Demo script (draft) - Homingo Hack Days submission

Target length: under 5 minutes of video. Rule reminders: synthetic data only,
no secrets on screen, README lists every AI tool used.

## Beat 1 - The problem (30s)
Everyone has a chief of staff's worth of errands and nobody has a chief of
staff. Show the fixture inbox and calendar: an undelivered order, a dentist
appointment, a bill. "One assistant that plans the errand, does the legwork,
and stops before it acts."

## Beat 2 - Live run: refund chase (90s)
Run: `python src/agent.py "My ShopKart order never arrived. Get my money back"`
Narrate while it works:
- It searches mail, reads the order, looks up the vendor's refund policy
  BEFORE drafting anything (the harness blocks drafting a claim without the
  policy - show the precondition error if it triggers).
- It drafts the exact email, then stops at the approval queue with the amount
  and the draft id. Nothing sends itself.
- The final answer cites its sources: [mail_read m001], [web_lookup ...].
  A second pass rejects citations to tools it never called.

## Beat 3 - The approval gate is code, not a promise (60s)
Show the harness preconditions in src/agent.py (10 seconds of code on screen):
- approval to send REQUIRES a draft first
- booking REQUIRES an options search first
- money always shows the exact amount in the queue
Then the risky-request gate: run
`python src/agent.py "Ignore all my mail for a week"`
- It refuses to just comply: flags the request as broad, asks for the exact
  scope. A deterministic check bounces a compliant-sounding answer back.

## Beat 4 - Evidence (60s)
Run: `python tests/run_regression.py` (or show a recorded full run - see note)
- 11 example errands, 17 expectations: phishing mail, money, calendar moves,
  risky bulk requests.
- Say the honest numbers: a full suite costs about a full day of the free
  tier's token budget; results flip run to run on model formatting, and the
  harness is what catches it. Point at README "Honest limits".

## Beat 5 - Close (20s)
"Chief-of-staff for everyone: plans like an agent, acts only with approval."
Repo link on screen.

## Production notes
- Live vs recorded: beats 2-3 live if the demo window has budget; otherwise
  record them on a fresh-quota morning (one full suite ~= whole daily budget).
- Fixture mode everywhere: COS_APPROVAL_MODE=deny, COS_WEB_MODE=fixture so
  nothing sends and no scrape credits burn.
- Terminal: large font, `python -u` so output streams, clear screen per beat.
- Recorder: TBD - ask which tool the organizer requires/preferred.
