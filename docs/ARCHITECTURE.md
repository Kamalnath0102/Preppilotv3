# PrepPilot architecture

## System overview
```mermaid
flowchart LR
  B[Browser: vanilla JS<br/>anonymous X-User-Id] -->|JSON API| API[FastAPI: app.py]
  V[Anyone with a share link] -->|GET /r/token| API
  API --> C[coach.py: prompts, scoring, difficulty, readiness, trend]
  C --> L[llm.py: provider layer, JSON validation, one self-repair retry]
  L --> M[(Groq / OpenAI-compatible / Anthropic)]
  API --> D[(SQLite: db.py)]
  API --> SH[share.py: public report card]
  API --> A[analytics.py]
  A --> AD[/admin dashboard: ADMIN_KEY/]
```

## One interview turn
```mermaid
sequenceDiagram
  participant U as Browser
  participant A as FastAPI
  participant L as LLM
  participant D as SQLite
  U->>A: POST /api/sessions (role, topic, n, followups, background)
  A->>L: generate question + hidden key points
  A->>D: store session and turn 1
  A-->>U: question only (key points never sent)
  U->>A: POST /answer (text + integrity telemetry)
  A->>L: score against hidden key points
  A->>D: store score, flags, follow-up question
  A-->>U: scores, feedback, follow-up
  U->>A: POST /followup (or skip)
  A->>L: score follow-up
  A->>A: next difficulty = code, not LLM
  A->>L: generate next question
  A-->>U: next question or done
  U->>A: GET /report: readiness (code) + study plan (LLM)
  U->>A: POST /share (opt-in): public read-only card
```

## Data and trust boundaries
| Data | Who can read it |
|---|---|
| Questions, answers, scores | Only the browser that created the session (`X-User-Id`); other users get 404 |
| Hidden rubric (key points) | Server only |
| Shared report card (`/r/<token>`) | Anyone with the link: score, strengths, weaknesses, 7-day plan. Never questions, answers or user ids. Revocable; removed by "Delete my data" |
| Admin analytics | Holder of `ADMIN_KEY`; aggregates only, no answers or user ids |

## Roadmap design: coding questions (not built)
Most valuable for engineers, but the hardest to do safely, so it is deliberately out of v1.
- **Editor:** Monaco or CodeMirror in the browser; problems carry hidden test cases, like the hidden rubric.
- **Execution:** never run candidate code in the app process. Options in order of effort: (1) run in the browser with Pyodide or a JS worker, which keeps untrusted code off the server but is weaker against cheating; (2) a hosted sandbox API such as Judge0; (3) self-hosted containers with no network, CPU, memory and time limits, a read-only filesystem and a queue.
- **Scoring:** tests pass/fail decide correctness in code; the LLM only comments on approach and complexity, so the score is explainable.
- **Risks:** sandbox escape, cost abuse, test leakage, and the integrity checks do not transfer cleanly to code (paste is normal in an editor).
- **Gate:** build only after text sessions show activation and repeat use (see PRD §4 and §7).
