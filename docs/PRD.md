# PrepPilot: Product Requirements (v1)

## 1. Problem
Learners preparing for engineering roles get little realistic interview practice. Human mock interviews are scarce and expensive, and self-study gives no objective read on gaps.
> Hypothesis to validate: students would practice more and improve faster with on-demand mock interviews that give honest, specific feedback. _(Replace with evidence from `USER_RESEARCH.md`.)_

## 2. Target user
Final-year students and early-career engineers preparing for fresher or junior roles. Secondary: career switchers.
**Job to be done:** "Tell me honestly how ready I am and what to do this week to improve."

## 3. Goals and non-goals
| Goals (v1) | Non-goals (v1) |
|---|---|
| Realistic 3/5/10-question text interviews with follow-ups | Voice or video interviews |
| Trustworthy, explainable scoring | Live coding with test execution |
| Visible progress over time | Human mentor marketplace |
| Low friction: no signup | Full accounts, payments |

## 4. Success metrics
| Type | Metric | Target (hypothesis) |
|---|---|---|
| North star | Users completing 3+ sessions in 14 days with a rising readiness score | 15% of first-session completers |
| Activation | Visitors who complete a first session | 40% |
| Quality | "Was this score fair?" thumbs-up rate | 80%+ |
| Quality | Eval pass rate and run-to-run variance | 90%+ pass, variance under 0.5 |
| Engagement | Follow-up answered rate | 70%+ |
| Guardrails | Integrity flag rate, p95 latency, tokens per session | under 15%, under 8s, tracked |

## 5. Scope and prioritization (impact vs effort)
| Item | Impact | Effort | Decision |
|---|---|---|---|
| Rubric-based scoring with hidden key points | High | Low | Built |
| Follow-up questions | High | Medium | Built |
| Fairness thumbs and admin analytics | High | Medium | Built (needed to learn) |
| Per-browser history and delete-my-data | Medium | Low | Built |
| Paste/copy friction plus integrity flags | Medium | Low | Built (flag, don't block) |
| Resume-aware questions | Medium | Low | Built as an optional pasted background field (no file upload) |
| Progress trend per user | Medium | Low | Built (same-topic delta and chart) |
| Shareable report card / PDF | Medium | Low | Built (opt-in public link; also a growth loop) |
| Full login | Medium | High | Deferred: friction hurts activation |
| Voice answers | High | High | Roadmap after text MVP is validated |
| Coding questions with test runner | High | Very high | Roadmap: sandbox design in `ARCHITECTURE.md` |
| Postgres, payments | Low now | Medium | Deferred until traction |

## 6. Risks and mitigations
- **Scores feel wrong or unfair:** hidden rubric, calibration evals, fairness thumbs, "judge ideas not English" rule and a dedicated eval case.
- **Cheating or gaming:** friction plus server-side flags, flagged sessions marked in the report.
- **Prompt injection:** answers are treated as untrusted and tested in evals.
- **Privacy:** minimal data, no raw answers in analytics, self-serve deletion.
- **Cost:** token tracking, daily session cap, rate limiting, free-tier model.

## 7. Launch plan (first 2 weeks)
1. Week 1: 5 user interviews, 10 to 15 friends and classmates test it; fix the top 3 issues from the admin dashboard.
2. Week 2: share in 3 college or community groups; track activation and fairness rate.
3. Decision rule: if completion is under 30%, fix the first-question experience before adding features.

## 8. Pricing hypothesis (to test, not built)
Free: 3 sessions per day. Paid (about INR 199 per month, hypothesis): unlimited sessions, company-style tracks, saved history across devices, mentor review credits. Test with a "join the waitlist for Pro" button and measure click-through before building anything.

## 9. Open questions
- Do users trust AI scores more with the rubric shown after each answer?
- Is text enough, or is voice the key missing piece?
- What readiness score would make someone feel ready to apply?
