"""Run: python -m evals.run_evals
Calibration eval for the answer scorer. For labelled answers (strong, weak, don't-know, off-topic, prompt-injection,
and a non-native-English fairness case) it checks:
  1. expected score ranges   2. strong ranked above weak   3. run-to-run consistency (each answer scored twice).
Writes evals/RESULTS.md and evals/RESULTS_<model>.md so you can compare models side by side."""
import json, re, time
from pathlib import Path

import llm
from coach import score_answer

HERE = Path(__file__).parent


def scored(q, text):
    time.sleep(1.2)  # stay under free-tier rate limits
    s, _ = score_answer(q["question"], q["key_points"], q["difficulty"], text)
    return s.correctness


def main():
    data = json.loads((HERE / "calibration.json").read_text())
    rows, passed, total, diffs, order_ok, order_total, errors = [], 0, 0, [], 0, 0, 0
    for q in data:
        by_label = {}
        for a in q["answers"]:
            try:
                c1, c2 = scored(q, a["text"]), scored(q, a["text"])
            except Exception as e:
                errors += 1
                rows.append((q["question"][:38] + "…", a["label"], f"ERROR {type(e).__name__}", "-", "ERROR"))
                continue
            diffs.append(abs(c1 - c2))
            by_label[a["label"]] = (c1 + c2) / 2
            e = a["expect"]
            ok = ("correctness_min" not in e or min(c1, c2) >= e["correctness_min"]) and \
                 ("correctness_max" not in e or max(c1, c2) <= e["correctness_max"])
            passed += ok
            total += 1
            rows.append((q["question"][:38] + "…", a["label"], f"{c1}/{c2}", json.dumps(e), "pass" if ok else "FAIL"))
        if "strong" in by_label and "weak" in by_label:
            order_total += 1
            order_ok += by_label["strong"] > by_label["weak"]
    md = [f"# Scorer calibration results ({llm.MODEL})", "",
          f"- Expectation pass rate: {passed}/{total}" + (f" ({errors} errors)" if errors else ""),
          f"- Strong ranked above weak: {order_ok}/{order_total}",
          f"- Mean run-to-run correctness difference: {sum(diffs) / len(diffs):.2f} (lower is more consistent)" if diffs else "- No consistency data",
          "", "| question | answer type | correctness (run1/run2) | expected | result |", "|---|---|---|---|---|"]
    md += ["| " + " | ".join(r) + " |" for r in rows]
    text = "\n".join(md) + "\n"
    (HERE / "RESULTS.md").write_text(text)
    (HERE / f"RESULTS_{re.sub(r'[^A-Za-z0-9]+', '_', llm.MODEL)}.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
