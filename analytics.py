"""Product analytics for the /admin dashboard. Pure function so it is easy to test."""
import time
from collections import Counter, defaultdict
import coach


def _mean(xs, nd=2):
    return round(sum(xs) / len(xs), nd) if xs else None


def pending_followup(t):
    return bool(t.get("followup_q")) and t.get("followup_answer") is None


def compute(sessions, turns, feedback, now=None):
    now = now or time.time()
    by_s = defaultdict(list)
    for t in turns:
        by_s[t["session_id"]].append(t)
    completed, readiness, by_topic = 0, [], defaultdict(list)
    for s in sessions:
        done = [t for t in by_s[s["id"]] if t["score"] and not pending_followup(t)]
        if done and len(done) >= (s["n_questions"] or 5):
            completed += 1
            r = coach.readiness(done)
            readiness.append(r)
            by_topic[s["topic"]].append(r)
    answered = [t for t in turns if t["score"]]
    flagged = [t for t in answered if t["integrity"] and any(f != "no_telemetry" for f in t["integrity"]["flags"])]
    reached, ans_by_idx = Counter(t["idx"] for t in turns), Counter(t["idx"] for t in answered)
    offered = [t for t in turns if t.get("followup_q")]
    fu_done = [t for t in offered if t.get("followup_answer")]
    metas = [t["meta"] for t in answered if t.get("meta")]
    days = Counter(time.strftime("%Y-%m-%d", time.gmtime(s["created"])) for s in sessions)
    last14 = [time.strftime("%Y-%m-%d", time.gmtime(now - 86400 * i)) for i in range(13, -1, -1)]
    up = sum(1 for f in feedback if f["rating"] == 1)
    down = sum(1 for f in feedback if f["rating"] == -1)
    return {
        "sessions_started": len(sessions),
        "sessions_completed": completed,
        "completion_rate": round(completed / len(sessions), 2) if sessions else None,
        "avg_readiness": _mean(readiness, 1),
        "readiness_by_topic": {k: {"avg": _mean(v, 1), "n": len(v)} for k, v in by_topic.items()},
        "dropoff": [{"question": i, "reached": reached[i], "answered": ans_by_idx[i]} for i in sorted(reached)],
        "avg_scoring_latency_s": _mean([m["latency_s"] for m in metas]),
        "avg_scoring_tokens": _mean([m["tokens"] for m in metas], 0),
        "total_scoring_tokens": sum(m["tokens"] for m in metas),
        "flag_rate": round(len(flagged) / len(answered), 2) if answered else None,
        "followup_answer_rate": round(len(fu_done) / len(offered), 2) if offered else None,
        "avg_followup_quality": _mean([t["followup_score"]["quality"] for t in fu_done if t.get("followup_score")]),
        "fairness_thumbs": {"up": up, "down": down, "up_rate": round(up / (up + down), 2) if up + down else None},
        "recent_comments": [{"rating": f["rating"], "comment": f["comment"]}
                            for f in sorted(feedback, key=lambda f: -f["created"]) if f["comment"]][:10],
        "sessions_per_day": [{"date": d, "sessions": days[d]} for d in last14],
    }
