# Demo script (v2) - Homingo Hack Days submission video

Official requirement (organizer mail, 2 Nov): "Record the one path that
matters, from the user's first action to the finished result. A plain screen
recording is fine." No camera, voice or presenter requirement; the video is
submitted as a link with sharing on.

THE ONE PATH: the refund chase, first action to finished result. Target
2-3 minutes. One continuous terminal recording, large font, `python -u`.

## Visible fixture labeling (required)
The whole demo runs on synthetic fixtures. Wherever the distinction affects
interpretation, the screen must say so:
- A banner line at recording start:
  "DEMO DATA: simulated mailbox, calendar, restaurants and web. No real
  accounts, no real email is sent. Approved actions print what would happen."
- Fixture mode is on: COS_APPROVAL_MODE=deny COS_WEB_MODE=fixture.
- When the approval queue denies, say on screen (typed comment): approvals are
  auto-denied in the demo so nothing ever acts.

## Beats
1. (10s) Terminal shows the banner, then the inbox/calendar fixtures: an
   undelivered ShopKart order, a dentist appointment.
2. (60-90s) First action: `python src/agent.py "My ShopKart order never
   arrived. Get my money back"`
   Narrate via typed echo lines between runs, not audio:
   - it searches mail and reads the order BEFORE drafting
   - it looks up the vendor refund policy - the harness blocks a claim draft
     that skips this (show the precondition error if it fires)
   - it drafts the exact email, then stops: approval queue shows the amount
     and the draft id. Nothing sends itself.
   - the final answer cites its sources, e.g. [mail_read m001]; a second pass
     rejects citations to tools never called
3. (30s) The risky request: `python src/agent.py "Ignore all my mail for a
   week"` - it flags the request as broad and asks for exact scope instead of
   complying. A deterministic gate bounces compliant-sounding answers.
4. (20s) Evidence: show the last green suite summary line (17/17, revision
   hash, date) from the regression log file, and README "Honest limits":
   results vary run to run; the harness catches it.
5. (5s) Repo URL on screen.

## Production
- Record: terminal session capture in the sandbox (asciinema if present,
  else `script` + render), stitched/titled with ffmpeg. No audio track needed;
  typed echo lines carry the narration. No AI voice needed.
- Budget: beats 2-3 cost one errand run each (~small); record on a
  fresh-quota morning and do NOT run a full suite the same day.
- Hosting: TBD (options tracked with main) - the link must open in a private
  window with sharing on.
- Before submission: open the video link in a private browser window to
  confirm sharing, exactly as the organizer instructs.
