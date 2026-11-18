import json, os, sqlite3, time

PATH = os.getenv("DB_PATH", "preppilot.db")
SESSION_COLS = {"user_id": "TEXT", "n_questions": "INTEGER DEFAULT 5", "followups": "INTEGER DEFAULT 1", "context": "TEXT", "share_token": "TEXT"}
TURN_COLS = {"integrity": "TEXT", "meta": "TEXT", "followup_q": "TEXT", "followup_answer": "TEXT", "followup_score": "TEXT"}


def conn():
    c = sqlite3.connect(PATH)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, role TEXT, topic TEXT, created INTEGER, report TEXT);
    CREATE TABLE IF NOT EXISTS turns(id INTEGER PRIMARY KEY, session_id INTEGER, idx INTEGER, question TEXT,
        key_points TEXT, difficulty INTEGER, answer TEXT, score TEXT);
    CREATE TABLE IF NOT EXISTS feedback(session_id INTEGER, idx INTEGER, rating INTEGER, comment TEXT, created INTEGER,
        PRIMARY KEY(session_id, idx));""")
    for table, cols in (("sessions", SESSION_COLS), ("turns", TURN_COLS)):  # safe migrations for older databases
        have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
        for name, typ in cols.items():
            if name not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
    return c


def _j(v):
    return json.loads(v) if v else None


def _turn(r):
    d = dict(r)
    for k in ("key_points", "score", "integrity", "meta", "followup_score"):
        d[k] = _j(d.get(k))
    return d


def new_session(user_id, role, topic, n_questions=5, followups=True, context=""):
    with conn() as c:
        return c.execute("INSERT INTO sessions(role,topic,created,user_id,n_questions,followups,context) VALUES(?,?,?,?,?,?,?)",
                         (role, topic, int(time.time()), user_id, n_questions, int(followups), context)).lastrowid


def add_turn(sid, idx, q):
    with conn() as c:
        c.execute("INSERT INTO turns(session_id,idx,question,key_points,difficulty) VALUES(?,?,?,?,?)",
                  (sid, idx, q.question, json.dumps(q.key_points), q.difficulty))


def get_session(sid):
    with conn() as c:
        s = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not s:
            return None
        rows = c.execute("SELECT * FROM turns WHERE session_id=? ORDER BY idx", (sid,)).fetchall()
    return {**dict(s), "report": _j(s["report"]), "turns": [_turn(r) for r in rows]}


def save_answer(turn_id, answer, score, integrity, meta, followup_q=None):
    with conn() as c:
        c.execute("UPDATE turns SET answer=?, score=?, integrity=?, meta=?, followup_q=? WHERE id=?",
                  (answer, json.dumps(score), json.dumps(integrity), json.dumps(meta), followup_q, turn_id))


def save_followup(turn_id, answer, score, integrity):
    with conn() as c:
        c.execute("UPDATE turns SET followup_answer=?, followup_score=?, integrity=? WHERE id=?",
                  (answer, json.dumps(score) if score else None, json.dumps(integrity), turn_id))


def save_report(sid, report):
    with conn() as c:
        c.execute("UPDATE sessions SET report=? WHERE id=?", (json.dumps(report), sid))


def history(user_id):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, role, topic, created, n_questions FROM sessions WHERE user_id=? ORDER BY id DESC LIMIT 20", (user_id,))]


def set_share_token(sid, token):
    with conn() as c:
        c.execute("UPDATE sessions SET share_token=? WHERE id=?", (token, sid))


def get_by_share_token(token):
    with conn() as c:
        r = c.execute("SELECT id FROM sessions WHERE share_token=?", (token,)).fetchone()
    return get_session(r["id"]) if r else None


def count_sessions_since(user_id, ts):
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM sessions WHERE user_id=? AND created>=?", (user_id, ts)).fetchone()[0]


def save_feedback(sid, idx, rating, comment):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO feedback(session_id,idx,rating,comment,created) VALUES(?,?,?,?,?)",
                  (sid, idx, rating, comment, int(time.time())))


def delete_user(user_id):
    with conn() as c:
        ids = [r[0] for r in c.execute("SELECT id FROM sessions WHERE user_id=?", (user_id,))]
        for sid in ids:
            c.execute("DELETE FROM feedback WHERE session_id=?", (sid,))
            c.execute("DELETE FROM turns WHERE session_id=?", (sid,))
            c.execute("DELETE FROM sessions WHERE id=?", (sid,))
    return len(ids)


def raw_rows():
    """All data for analytics (no user ids or answer text leave this function's callers)."""
    with conn() as c:
        sessions = [dict(r) for r in c.execute("SELECT id, topic, created, n_questions FROM sessions WHERE user_id IS NOT NULL")]
        turns = [_turn(r) for r in c.execute(
            "SELECT t.* FROM turns t JOIN sessions s ON s.id=t.session_id WHERE s.user_id IS NOT NULL")]
        fb = [dict(r) for r in c.execute("SELECT * FROM feedback")]
    return sessions, turns, fb
