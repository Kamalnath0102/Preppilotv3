import pytest
from fastapi.testclient import TestClient

import analytics, app as A, coach, db
from models import DayPlan, FollowScore, Question, Report, Score

M = {"latency_s": 0.1, "tokens": 10, "attempts": 1, "model": "fake"}
H = {"X-User-Id": "user-aaaa-1111"}
H2 = {"X-User-Id": "user-bbbb-2222"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "PATH", str(tmp_path / "t.db"))

    def fake(system, user, schema):
        if schema is Question:
            return Question(question="Q?", topic="t", difficulty=2, key_points=["a", "b", "c"]), M
        if schema is Score:
            return Score(correctness=5, depth=4, communication=4, feedback="Good", missed_points=[], follow_up="Why?"), M
        if schema is FollowScore:
            return FollowScore(quality=4, feedback="ok"), M
        return Report(strengths=["s"], weaknesses=["w"], study_plan=[DayPlan(day=i, focus="f", tasks=["t"]) for i in range(1, 8)],
                      encouragement="go"), M

    monkeypatch.setattr(coach, "call_json", fake)
    A._hits.clear()
    return TestClient(A.app)


def start(c, h=H, **kw):
    body = {"role": "SWE", "topic": "DSA", "n_questions": 3, **kw}
    return c.post("/api/sessions", json=body, headers=h).json()


# ---- pure logic ----
def sc(c, d, m):
    return {"correctness": c, "depth": d, "communication": m}


def test_next_difficulty():
    assert coach.next_difficulty(2, sc(5, 5, 5)) == 3
    assert coach.next_difficulty(2, sc(1, 1, 1)) == 1
    assert coach.next_difficulty(5, sc(5, 5, 5)) == 5
    assert coach.next_difficulty(3, sc(3, 3, 3)) == 3


def test_readiness_bounds_and_followup_blend():
    perfect = {"difficulty": 3, "score": sc(5, 5, 5)}
    worst = {"difficulty": 3, "score": sc(1, 1, 1)}
    assert coach.readiness([perfect]) == 100 and coach.readiness([worst]) == 0 and coach.readiness([]) == 0
    base = {"difficulty": 2, "score": sc(3, 3, 3)}
    better = {**base, "followup_score": {"quality": 5, "feedback": ""}}
    assert coach.readiness([better]) > coach.readiness([base])


def test_readiness_weights_by_difficulty():
    hard_good = {"difficulty": 5, "score": sc(5, 5, 5)}
    easy_bad = {"difficulty": 1, "score": sc(1, 1, 1)}
    assert coach.readiness([hard_good, easy_bad]) > 50


def test_integrity_flags():
    ig = A.Integrity
    assert A.integrity_flags("hi", None) == ["no_telemetry"]
    assert A.integrity_flags("short", ig(keystrokes=5, seconds=10)) == []
    assert "paste_attempt" in A.integrity_flags("x", ig(paste_attempts=1))
    assert "left_tab" in A.integrity_flags("x", ig(tab_switches=2))
    assert "typed_less_than_written" in A.integrity_flags("x" * 200, ig(keystrokes=10, seconds=100))
    assert "answered_too_fast" in A.integrity_flags("x" * 200, ig(keystrokes=200, seconds=5))


# ---- API ----
def test_full_flow_with_followups(client):
    d = start(client)
    sid = d["session_id"]
    assert "key_points" not in d["turn"] and d["total"] == 3
    for i in range(3):
        r = client.post(f"/api/sessions/{sid}/answer", json={"answer": "my answer"}, headers=H).json()
        assert r["followup"] == "Why?"
        assert client.get(f"/api/sessions/{sid}/report", headers=H).status_code == 409  # follow-up pending
        f = client.post(f"/api/sessions/{sid}/followup", json={"answer": "because"}, headers=H).json()
        assert f["followup_score"]["quality"] == 4 and f["done"] == (i == 2)
    rep = client.get(f"/api/sessions/{sid}/report", headers=H).json()
    assert 0 < rep["readiness"] <= 100 and len(rep["report"]["study_plan"]) == 7
    h = client.get("/api/history", headers=H).json()
    assert len(h) == 1 and h[0]["readiness"] == rep["readiness"]


def test_skip_followup_and_followups_off(client):
    sid = start(client)["session_id"]
    client.post(f"/api/sessions/{sid}/answer", json={"answer": "a"}, headers=H)
    r = client.post(f"/api/sessions/{sid}/followup", json={"skip": True}, headers=H).json()
    assert r["followup_score"] is None and r["next"]["idx"] == 2
    assert client.post(f"/api/sessions/{sid}/followup", json={"answer": "x"}, headers=H).status_code == 409
    sid2 = start(client, followups=False)["session_id"]
    r = client.post(f"/api/sessions/{sid2}/answer", json={"answer": "a"}, headers=H).json()
    assert "followup" not in r and r["next"]["idx"] == 2


def test_empty_followup_rejected(client):
    sid = start(client)["session_id"]
    client.post(f"/api/sessions/{sid}/answer", json={"answer": "a"}, headers=H)
    assert client.post(f"/api/sessions/{sid}/followup", json={"answer": "  "}, headers=H).status_code == 400


def test_user_isolation_and_missing_id(client):
    sid = start(client)["session_id"]
    assert client.post(f"/api/sessions/{sid}/answer", json={"answer": "a"}, headers=H2).status_code == 404
    assert client.get("/api/history", headers=H2).json() == []
    assert client.get("/api/history").status_code == 400


def test_delete_my_data(client):
    start(client)
    assert client.delete("/api/me", headers=H).json()["deleted_sessions"] == 1
    assert client.get("/api/history", headers=H).json() == []


def test_daily_cap(client, monkeypatch):
    monkeypatch.setattr(A, "DAILY_SESSIONS", 1)
    start(client)
    assert client.post("/api/sessions", json={"role": "SWE", "topic": "DSA"}, headers=H).status_code == 429


def test_feedback_and_admin(client, monkeypatch):
    sid = start(client)["session_id"]
    client.post(f"/api/sessions/{sid}/answer", json={"answer": "a", "integrity": {"paste_attempts": 1}}, headers=H)
    assert client.post(f"/api/sessions/{sid}/feedback", json={"idx": 1, "rating": 1, "comment": "fair"}, headers=H).status_code == 200
    assert client.post(f"/api/sessions/{sid}/feedback", json={"idx": 1, "rating": 5}, headers=H).status_code == 422
    assert client.post(f"/api/sessions/{sid}/feedback", json={"idx": 3, "rating": 1}, headers=H).status_code == 404
    monkeypatch.setattr(A, "ADMIN_KEY", "secret-key")
    assert client.get("/api/admin/stats").status_code == 403
    assert client.get("/api/admin/stats", headers={"X-Admin-Key": "wrong"}).status_code == 403
    st = client.get("/api/admin/stats", headers={"X-Admin-Key": "secret-key"}).json()
    assert st["sessions_started"] == 1 and st["fairness_thumbs"]["up"] == 1 and st["flag_rate"] == 1.0
    assert st["recent_comments"][0]["comment"] == "fair" and len(st["sessions_per_day"]) == 14


def test_admin_disabled_without_key(client, monkeypatch):
    monkeypatch.setattr(A, "ADMIN_KEY", None)
    assert client.get("/api/admin/stats", headers={"X-Admin-Key": ""}).status_code == 403


def test_analytics_empty():
    st = analytics.compute([], [], [])
    assert st["sessions_started"] == 0 and st["completion_rate"] is None and st["avg_readiness"] is None


# ---- progress trend ----
def test_trend_logic():
    assert coach.trend([]) == {"delta": None, "best": None, "latest": None}
    p = [{"topic": "A", "readiness": 40}, {"topic": "B", "readiness": 90}, {"topic": "A", "readiness": 55}]
    assert coach.trend(p) == {"delta": 15, "best": 90, "latest": 55}  # compares same topic only
    assert coach.trend([{"topic": "A", "readiness": 40}, {"topic": "B", "readiness": 60}])["delta"] is None


def finish(c, h=H, **kw):
    sid = start(c, h, **kw)["session_id"]
    for _ in range(3):
        c.post(f"/api/sessions/{sid}/answer", json={"answer": "a"}, headers=h)
        c.post(f"/api/sessions/{sid}/followup", json={"skip": True}, headers=h)
    return sid


def test_progress_is_per_user_and_ordered(client):
    finish(client)
    finish(client)
    g = client.get("/api/progress", headers=H).json()
    assert len(g["points"]) == 2 and g["points"][0]["id"] < g["points"][1]["id"] and g["delta"] == 0
    assert client.get("/api/progress", headers=H2).json()["points"] == []  # other users never see these sessions


# ---- shareable report card ----
def test_share_flow_and_privacy(client):
    sid = finish(client, context="")
    assert client.post(f"/api/sessions/{sid}/share", json={}, headers=H).status_code == 409  # report not built yet
    client.get(f"/api/sessions/{sid}/report", headers=H)
    assert client.post(f"/api/sessions/{sid}/share", json={}, headers=H2).status_code == 404  # not the owner
    path = client.post(f"/api/sessions/{sid}/share", json={}, headers=H).json()["share_path"]
    page = client.get(path)  # public: no user header needed
    assert page.status_code == 200 and "/100" in page.text and "Day 7" in page.text
    assert "my answer" not in page.text and "Q?" not in page.text and "user-aaaa" not in page.text  # no answers/questions/ids
    assert client.get(f"/api/sessions/{sid}/report", headers=H).json()["share_path"] == path
    client.delete(f"/api/sessions/{sid}/share", headers=H)
    assert client.get(path).status_code == 404


def test_share_page_escapes_html_and_rejects_bad_tokens(client):
    import share
    s = {"role": "<b>r</b>", "topic": "t", "report": {"encouragement": "<script>x</script>", "strengths": ["s"], "weaknesses": ["w"],
         "study_plan": [{"day": 1, "focus": "f", "tasks": ["t"]}]}}
    html = share.render(s, 50, 0)
    assert "<script>x" not in html and "&lt;script&gt;" in html and "<b>r</b>" not in html
    assert client.get("/r/short").status_code == 404 and client.get("/r/" + "x" * 12).status_code == 404


def test_delete_my_data_revokes_share(client):
    sid = finish(client)
    client.get(f"/api/sessions/{sid}/report", headers=H)
    path = client.post(f"/api/sessions/{sid}/share", json={}, headers=H).json()["share_path"]
    client.delete("/api/me", headers=H)
    assert client.get(path).status_code == 404
