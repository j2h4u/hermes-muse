"""Review every unjudged private turn of the last 72h, oldest first, in any language.

The model judges agent_gap / latent_need / friction / fine. Tool failures are evidence,
never an admission gate. Each turn is recorded once.
"""
import re

from .common import D, clip, one

PAGE = 2000  # host rows per read; the window is read page by page
WINDOW = 3 * D
VERDICTS = ("agent_gap", "latent_need", "friction", "fine")
FAILED = re.compile(r'"(?:success|ok)"\s*:\s*false|"error"\s*:\s*"[^"]|"status"\s*:\s*"(?:error|failed)"'
                    r'|^\s*(?:error|failed|traceback)\b', re.I | re.M)


def turns(rows):
    """Group time-ordered user/assistant/tool rows into turns per session."""
    out, current = [], {}
    for row in rows:
        sid = row["session_id"]
        if row["role"] == "user":
            previous = current.get(sid)
            turn = {"ref": row["ref"], "at": row["at"], "user": row["text"], "replies": [], "tools": [],
                    "previous": previous["user"] if previous else None,
                    "previous_reply": "\n\n".join(previous["replies"]) if previous else None}
            current[sid] = turn
            out.append(turn)
        elif sid in current:
            if row["role"] == "assistant":
                current[sid]["replies"].append(row["text"])
            else:
                current[sid]["tools"].append((row.get("tool_name") or "", not FAILED.search(row["text"][:2000])))
    return out


def rules(turn):
    found, tools = [], turn["tools"]
    if any(not ok and not any(ok2 and name2 == name for name2, ok2 in tools[i + 1:]) for i, (name, ok) in enumerate(tools)):
        found.append("tool_failure_unretried")
    return found


def window(k, since):
    """Every user/assistant/tool row after `since`; a page restarts at its last timestamp, refs dedupe the overlap."""
    rows, refs = [], set()
    while True:
        page = [r for r in k.adapter.sessions.user_turns(since, roles=("user", "assistant", "tool"), limit=PAGE)
                if r["ref"] not in refs]
        if not page:
            return rows
        rows += page
        refs.update(r["ref"] for r in page)
        since = page[-1]["at"] - 1e-6


def candidates(k, now, skip=()):
    """Every private turn, oldest first; judged or already offered turns are left out."""
    rows = window(k, now - WINDOW)
    picked = []
    for turn in turns(rows):
        ref = "review:" + turn["ref"]
        if ref in skip or one(k.store, "finding", ref) or one(k.store, "idea", ref):
            continue
        found = rules(turn)
        picked.append({"kind": "review", "ref": ref, "at": turn["at"], "rules": found, "user": clip(turn["user"], 1500),
                       "reply": clip("\n\n".join(turn["replies"]), 1500),
                       **({"previous_user": clip(turn["previous"], 800)} if turn["previous"] else {}),
                       **({"previous_reply": clip(turn["previous_reply"], 800)} if turn["previous_reply"] else {}),
                       "tools": [{"name": n, "ok": ok} for n, ok in turn["tools"][:10]], "pointer": turn["ref"]})
    return picked


def unreported(k, now):
    """Bounded actionable results from earlier batches, including a completed queue awaiting synthesis."""
    cursor = tuple(k.store.meta("review_reported_until", [0, ""]))
    rows = [e for kind, state in (("finding", "open"), ("idea", "active"))
            for e in k.store.query(kind, state=state, since=now - WINDOW)
            if e["payload"].get("verdict") in VERDICTS and (e["state_since"], e["id"]) > cursor]
    return [{"ref": e["id"], "at": e["state_since"], "turn": e["payload"]["turn"],
             "verdict": e["payload"]["verdict"], "reason": e["payload"]["reason"]}
            for e in sorted(rows, key=lambda e: (e["state_since"], e["id"]))[:20]]


def reported(k, results):
    """A successful final nightly batch included these results in its synthesis."""
    if results:
        k.store.set_meta("review_reported_until", max([r["at"], r["ref"]] for r in results))


def record(k, ref, verdict, reason, now, rules=()):
    """agent_gap -> open Finding (14 days); friction (the user corrected or redid something a skill or rule could have
    settled) -> open Finding tagged friction, a suggestion only; latent_need -> Idea candidate; fine -> dismissed Finding.
    `evidence` is the reviewed turn (a pointer for read) plus the pick rules that matched it."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
    reason = str(reason or "").strip()[:500]
    if not reason:
        raise ValueError("reason is required")
    turn = ref.removeprefix("review:")
    payload = {"reason": reason, "verdict": verdict, "turn": turn, "evidence": [turn, *(f"rule:{r}" for r in rules)]}
    with k.store.atomic():
        found = one(k.store, "finding", ref) or one(k.store, "idea", ref)
        if found:
            return {"result": "existing", "entity": found["id"]}
        if verdict == "latent_need":
            e = k.store.create("idea", ref, {"title": reason[:200], "origin": "review", **payload}, now=now)
        else:
            tag = {"tag": "friction"} if verdict == "friction" else {}
            e = k.store.create("finding", ref, {**payload, **tag}, state="dismissed" if verdict == "fine" else "open", now=now)
    return {"result": "recorded", "entity": e["id"], "state": e["state"]}
