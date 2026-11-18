"""PrepPilot API. Users are anonymous: the browser keeps a random id (X-User-Id header) so each person sees only their own sessions."""
import hmac, os, re, secrets, time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import Literal

import analytics, coach, db, share

app = FastAPI(title="PrepPilot")
HERE = Path(__file__).parent
ADMIN_KEY = os.getenv("ADMIN_KEY")
DAILY_SESSIONS = int(os.getenv("DAILY_SESSIONS", "10"))
DEBUG = bool(os.getenv("DEBUG"))
UID_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
_hits = defaultdict(deque)


def limit(request: Request, n=40, window=60):
    ip = request.client.host if request.client else "x"
    q, now = _hits[ip], time.time()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, "Slow down a little and try again in a minute.")
    q.append(now)


def uid(request: Request) -> str:
    u = request.headers.get("x-user-id", "")
    if not UID_RE.match(u):
        raise HTTPException(400, "Missing or invalid user id")
    return u


def load(sid: int, user: str):
    s = db.get_session(sid)
    if not s or s["user_id"] != user:  # same answer for "missing" and "someone else's": no information leak
        raise HTTPException(404, "Session not found")
    return s


class Integrity(BaseModel):
    """Client-reported telemetry. Spoofable, so it only raises flags; it never blocks or changes scores."""
    paste_attempts: int = Field(0, ge=0, le=1000)
    tab_switches: int = Field(0, ge=0, le=1000)
    keystrokes: int = Field(0, ge=0, le=100000)
    seconds: float = Field(0, ge=0, le=86400)


class Start(BaseModel):
    role: str = Field(min_length=2, max_length=80)
    topic: str = Field(min_length=2, max_length=80)
    n_questions: int = Field(5, ge=3, le=10)
    start_difficulty: int = Field(2, ge=1, le=5)
    followups: bool = True
    context: str = Field("", max_length=1500)


class Answer(BaseModel):
    answer: str = Field(min_length=1, max_length=4000)
    integrity: Integrity | None = None


class FollowUp(BaseModel):
    answer: str = Field("", max_length=3000)
    skip: bool = False
    integrity: Integrity | None = None


class Feedback(BaseModel):
    idx: int = Field(ge=1, le=10)
    rating: Literal[1, -1]
    comment: str = Field("", max_length=500)


def integrity_flags(answer: str, ig: Integrity | None) -> list[str]:
    if ig is None:
        return ["no_telemetry"]
    n, flags = len(answer), []
    if ig.paste_attempts:
        flags.append("paste_attempt")
    if ig.tab_switches >= 2:
        flags.append("left_tab")
    if n >= 80 and ig.keystrokes < n * 0.5:
        flags.append("typed_less_than_written")
    if n >= 80 and ig.seconds > 0 and n / ig.seconds > 12:
        flags.append("answered_too_fast")
    return flags


def public_turn(t):  # never leak the hidden rubric before the answer is scored
    return {"idx": t["idx"], "question": t["question"], "difficulty": t["difficulty"]}


def llm_call(fn, *a):
    try:
        return fn(*a)
    except ValueError as e:
        raise HTTPException(502, "The AI returned an unusable response. Please try again.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"AI error: {type(e).__name__}: {str(e)[:200]}" if DEBUG else "The AI service failed. Please try again.")


def advance(s, cur, score):
    """Create the next question (or finish). Difficulty adapts deterministically from the last score."""
    if cur["idx"] >= s["n_questions"]:
        return {"done": True}
    nd = coach.next_difficulty(cur["difficulty"], score)
    q, _ = llm_call(coach.generate_question, s["role"], s["topic"], nd, [t["question"] for t in s["turns"]], s.get("context") or "")
    db.add_turn(s["id"], cur["idx"] + 1, q)
    return {"done": False, "next": {"idx": cur["idx"] + 1, "question": q.question, "difficulty": nd}}


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/admin")
def admin_page():
    return FileResponse(HERE / "admin.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/sessions")
def start(body: Start, request: Request):
    limit(request)
    user = uid(request)
    if db.count_sessions_since(user, int(time.time()) - 86400) >= DAILY_SESSIONS:
        raise HTTPException(429, "Daily practice limit reached. Come back tomorrow!")
    q, _ = llm_call(coach.generate_question, body.role, body.topic, body.start_difficulty, [], body.context)
    sid = db.new_session(user, body.role, body.topic, body.n_questions, body.followups, body.context)
    db.add_turn(sid, 1, q)
    return {"session_id": sid, "total": body.n_questions, "turn": public_turn(db.get_session(sid)["turns"][0])}


@app.post("/api/sessions/{sid}/answer")
def answer(sid: int, body: Answer, request: Request):
    limit(request)
    s = load(sid, uid(request))
    cur = s["turns"][-1]
    if cur["score"]:
        raise HTTPException(409, "Current question already answered")
    sc, meta = llm_call(coach.score_answer, cur["question"], cur["key_points"], cur["difficulty"], body.answer)
    score = sc.model_dump()
    flags = integrity_flags(body.answer, body.integrity)
    fu = score.get("follow_up", "").strip() if s["followups"] else ""
    db.save_answer(cur["id"], body.answer, score, {"flags": flags, "raw": body.integrity.model_dump() if body.integrity else None},
                   meta, fu or None)
    out = {"score": score, "turn_score": round(coach.turn_score(score), 1), "meta": meta, "integrity_flags": flags,
           "idx": cur["idx"], "total": s["n_questions"]}
    if fu:
        return {**out, "followup": fu, "done": False}
    return {**out, **advance(s, cur, score)}


@app.post("/api/sessions/{sid}/followup")
def followup(sid: int, body: FollowUp, request: Request):
    limit(request)
    s = load(sid, uid(request))
    cur = s["turns"][-1]
    if not cur["score"] or not cur["followup_q"] or cur["followup_answer"] is not None:
        raise HTTPException(409, "No follow-up is waiting")
    if not body.skip and not body.answer.strip():
        raise HTTPException(400, "Write an answer or skip the follow-up")
    prev = (cur["integrity"] or {}).get("flags", [])
    fscore, flags = None, prev
    if not body.skip:
        fs, _ = llm_call(coach.score_followup, cur["question"], cur["answer"], cur["followup_q"], body.answer)
        fscore = fs.model_dump()
        flags = prev + integrity_flags(body.answer, body.integrity)
    flags = list(dict.fromkeys(f for f in flags if f != "no_telemetry"))
    db.save_followup(cur["id"], "" if body.skip else body.answer.strip(), fscore,
                     {"flags": flags, "raw": (cur["integrity"] or {}).get("raw")})
    return {"followup_score": fscore, "integrity_flags": flags, **advance(s, cur, cur["score"])}


@app.post("/api/sessions/{sid}/feedback")
def feedback(sid: int, body: Feedback, request: Request):
    limit(request)
    s = load(sid, uid(request))
    if not any(t["idx"] == body.idx and t["score"] for t in s["turns"]):
        raise HTTPException(404, "Question not found")
    db.save_feedback(sid, body.idx, body.rating, body.comment.strip())
    return {"ok": True}


@app.get("/api/sessions/{sid}/report")
def report(sid: int, request: Request):
    limit(request)
    s = load(sid, uid(request))
    turns = [t for t in s["turns"] if t["score"] and not analytics.pending_followup(t)]
    if len(turns) < s["n_questions"]:
        raise HTTPException(409, "Finish all questions first")
    if not s["report"]:
        r, _ = llm_call(coach.build_report, s["role"], s["topic"], turns)
        db.save_report(sid, r.model_dump())
        s = db.get_session(sid)
    flagged = sum(1 for t in turns if t["integrity"] and t["integrity"]["flags"])
    return {"readiness": coach.readiness(turns), "report": s["report"], "flagged_answers": flagged,
            "share_path": f"/r/{s['share_token']}" if s.get("share_token") else None,
            "turns": [{"question": t["question"], "difficulty": t["difficulty"], "score": t["score"],
                       "followup_score": t["followup_score"]} for t in turns]}


@app.get("/api/history")
def history(request: Request):
    user = uid(request)
    out = []
    for h in db.history(user):
        turns = [t for t in db.get_session(h["id"])["turns"] if t["score"] and not analytics.pending_followup(t)]
        done = len(turns) >= (h["n_questions"] or 5)
        out.append({**h, "answered": len(turns), "readiness": coach.readiness(turns) if done else None})
    return out


@app.get("/api/progress")
def progress(request: Request):
    """Completed sessions of THIS user, oldest first, plus the same-topic change since last time."""
    pts = [{"id": h["id"], "topic": h["topic"], "created": h["created"], "readiness": h["readiness"]}
           for h in reversed(history(request)) if h["readiness"] is not None]
    return {"points": pts, **coach.trend(pts)}


def _done_turns(s):
    return [t for t in s["turns"] if t["score"] and not analytics.pending_followup(t)]


@app.post("/api/sessions/{sid}/share")
def share_on(sid: int, request: Request):
    """Opt-in public link to a read-only report card (scores and plan only)."""
    limit(request)
    s = load(sid, uid(request))
    if not s["report"] or len(_done_turns(s)) < s["n_questions"]:
        raise HTTPException(409, "Finish the interview and open your report first")
    token = s.get("share_token") or secrets.token_urlsafe(12)
    db.set_share_token(sid, token)
    return {"share_path": f"/r/{token}"}


@app.delete("/api/sessions/{sid}/share")
def share_off(sid: int, request: Request):
    limit(request)
    load(sid, uid(request))
    db.set_share_token(sid, None)
    return {"ok": True}


@app.get("/r/{token}")
def public_report(token: str, request: Request):
    limit(request)
    s = db.get_by_share_token(token) if TOKEN_RE.match(token) else None
    if not s or not s["report"]:
        raise HTTPException(404, "This report link is not available")
    turns = _done_turns(s)
    flagged = sum(1 for t in turns if t["integrity"] and any(f != "no_telemetry" for f in t["integrity"]["flags"]))
    return HTMLResponse(share.render(s, coach.readiness(turns), flagged), headers={"Referrer-Policy": "no-referrer"})


@app.delete("/api/me")
def delete_me(request: Request):
    return {"deleted_sessions": db.delete_user(uid(request))}


@app.get("/api/admin/stats")
def admin_stats(request: Request):
    key = request.headers.get("x-admin-key", "")
    if not ADMIN_KEY or not hmac.compare_digest(key.encode(), ADMIN_KEY.encode()):
        raise HTTPException(403, "Forbidden")
    return analytics.compute(*db.raw_rows())
