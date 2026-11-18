"""Public, read-only report card. Contains only scores and the study plan: never questions, answers or user ids."""
from html import escape as e


def render(s: dict, readiness: int, flagged: int) -> str:
    r = s["report"]
    ul = lambda xs: "<ul>" + "".join(f"<li>{e(x)}</li>" for x in xs) + "</ul>"
    plan = "".join(f"<h3>Day {p['day']}: {e(p['focus'])}</h3>{ul(p['tasks'])}" for p in r["study_plan"])
    note = f'<p class="mut">{flagged} answer(s) in this session were flagged by integrity checks.</p>' if flagged else ""
    title = f"Interview readiness {readiness}/100: {e(s['topic'])}"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | PrepPilot</title><meta name="robots" content="noindex">
<meta property="og:title" content="{title}"><meta property="og:description" content="Practised with PrepPilot, an AI mock interview coach.">
<style>:root{{--bg:#f7f6f2;--card:#fff;--tx:#1f2328;--mut:#6b7280;--ac:#4f46e5;--bd:#e4e2da}}
@media (prefers-color-scheme:dark){{:root{{--bg:#15161a;--card:#1e2026;--tx:#e8e8ea;--mut:#9ca3af;--ac:#818cf8;--bd:#2d3038}}}}
body{{margin:0;background:var(--bg);color:var(--tx);font:16px/1.5 system-ui,sans-serif}}main{{max-width:720px;margin:0 auto;padding:24px 16px 48px}}
.card{{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:16px;margin:14px 0}}.big{{font-size:3.5rem;font-weight:700;margin:0;color:var(--ac)}}
.mut{{color:var(--mut);font-size:.9rem}}a.btn,button{{font:inherit;display:inline-block;padding:10px 18px;border-radius:10px;border:1px solid var(--ac);background:var(--ac);color:#fff;font-weight:600;text-decoration:none;cursor:pointer;margin-right:8px}}
button.s{{background:var(--card);color:var(--tx);border-color:var(--bd);font-weight:400}}@media print{{.noprint{{display:none}}}}</style></head><body><main>
<p class="mut">PrepPilot report card</p><h1>{e(s['role'])}: {e(s['topic'])}</h1>
<div class="card"><span class="mut">Interview readiness</span><p class="big">{readiness}/100</p><p>{e(r['encouragement'])}</p>{note}</div>
<div class="card"><b>Strengths</b>{ul(r['strengths'])}<b>Work on</b>{ul(r['weaknesses'])}</div>
<div class="card"><h2>7-day plan</h2>{plan}</div>
<p class="noprint"><button class="s" onclick="window.print()">Save as PDF</button><a class="btn" href="/">Practise your own interview</a></p>
<p class="mut">Scores come from an AI coach and are a practice signal, not a hiring verdict.</p></main></body></html>"""
