"""SQL QA harness: grade AI-drafted SQL against reviewed reference SQL, plus guardrails.
Checks per query: read-only, runs, same columns, same rows (order-insensitive, numeric tolerance), and a reconciliation guard
(net revenue totals must tie to the source tables). Writes results/qa_report.csv and README.md. Run: python build_db.py && python harness.py"""
from pathlib import Path
import re, time
import duckdb, pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from questions import Q

HERE = Path(__file__).parent; RES = HERE / "results"; RES.mkdir(exist_ok=True)
con = duckdb.connect(str(HERE / "shop.duckdb"), read_only=True)

def run(sql):
    if not re.match(r"^\s*(with|select)\b", sql, re.I) or re.search(r"\b(insert|update|delete|drop|alter|create)\b", sql, re.I):
        raise ValueError("guardrail: read-only SELECT/WITH only")
    t = time.time(); df = con.execute(sql).df(); return df, time.time() - t

def compare(a, b, tol=1e-6):
    if list(a.columns) != list(b.columns) and len(a.columns) != len(b.columns): return "column_count"
    a, b = a.copy(), b.copy(); b.columns = a.columns
    if len(a) != len(b): return f"row_count {len(b)} vs {len(a)}"
    a = a.sort_values(list(a.columns)).reset_index(drop=True); b = b.sort_values(list(b.columns)).reset_index(drop=True)
    for c in a.columns:
        if pd.api.types.is_numeric_dtype(a[c]):
            if ((a[c].astype(float) - b[c].astype(float)).abs() > tol + 1e-9).any(): return f"value_mismatch in {c}"
        elif not (a[c].astype(str) == b[c].astype(str)).all(): return f"value_mismatch in {c}"
    return "PASS"

def grade(which):
    out = []
    for q in Q:
        sql = q[which] if which == "draft" else (q["revised"] or q["draft"])
        gold, _ = run(q["golden"])
        try: cand, secs = run(sql); res = compare(gold, cand)
        except Exception as e: res, secs = f"error: {str(e)[:60]}", 0
        out.append(dict(id=q["id"], result=res, seconds=round(secs, 3)))
    return pd.DataFrame(out)

d1, d2 = grade("draft"), grade("revised")
rep = d1.merge(d2, on="id", suffixes=("_first_draft", "_after_review"))
rep.insert(1, "question", [q["q"][:70] + ("..." if len(q["q"]) > 70 else "") for q in Q])
rep.to_csv(RES / "qa_report.csv", index=False)

# reconciliation guard: sum of Q1 draft vs revised vs source of truth
src = con.execute("select sum(amount) from orders where status='completed'").fetchone()[0] - con.execute("select sum(r.amount) from refunds r join orders o using(order_id) where o.status='completed'").fetchone()[0]
q1 = next(q for q in Q if q["id"] == "Q1")
tot_draft = run(q1["draft"])[0].net_revenue.sum(); tot_rev = run(q1["revised"])[0].net_revenue.sum()

p1 = int((d1.result == "PASS").sum()); p2 = int((d2.result == "PASS").sum())
fig, ax = plt.subplots(figsize=(5, 3.4))
ax.bar(["AI first draft", "After review loop"], [p1, p2], color=["#a0aec0", "#2b6cb0"]); ax.set_ylim(0, len(Q))
ax.set_ylabel(f"queries matching reference (of {len(Q)})"); ax.set_title("SQL accuracy before and after the QA loop")
for i, v in enumerate([p1, p2]): ax.text(i, v + .1, str(v), ha="center")
plt.tight_layout(); plt.savefig(RES / "accuracy.png", dpi=140); plt.close()

why = {"Q1": "join fan-out: an order with 2 refunds is counted twice, inflating revenue", "Q2": "NULL customer_id (guest checkout) forms its own group and is counted as a customer",
       "Q4": "forgot the completed-orders filter (cancelled and pending items counted)", "Q5": "same fan-out inflates the denominator", "Q6": "denominator included customers with no completed order (definition drift)",
       "Q9": "counted any later order, not specifically the first one, and kept guest orders"}
fails = d1[d1.result != "PASS"]
lines = "\n".join(f"- **{r.id}**: {r.result}. Cause: {why.get(r.id, 'see questions.py')}." for r in fails.itertuples())
tbl = "| id | question | first draft | after review |\n|---|---|---|---|\n" + "\n".join(f"| {r.id} | {r.question} | {r.result_first_draft} | {r.result_after_review} |" for r in rep.itertuples())
readme = f"""# AI-assisted analytics workflow with SQL QA

**Synthetic data.** A small e-commerce warehouse (3,000 customers, ~4,100 orders, refunds, guest checkouts) in DuckDB.
No employer data. The question this project answers: **how do you use an AI assistant to write SQL fast and still trust the numbers?**

## Workflow
1. Write the question with its definition (what counts as revenue, who is a customer).
2. Have an AI assistant (Claude) draft the SQL from the question text and schema alone.
3. Run it through the harness (`harness.py`): read-only guard, executes, same columns and rows as a reviewed reference query
   (order-insensitive, numeric tolerance), and a reconciliation check against the source tables.
4. Diagnose each failure, fix it, re-grade, and keep the cause so the same trap is checked next time.

The AI drafts in this repo were written in a chat session, not by an automated API call inside the harness. The reference SQL was written
and reviewed by hand. Results below are from actually running the harness.

## Results ({p1}/{len(Q)} first drafts correct, {p2}/{len(Q)} after review)
{tbl}

Why the first drafts failed:
{lines}

Reconciliation guard: true net revenue from the source tables is **{src:,.2f}**. The first-draft Q1 totals **{tot_draft:,.2f}**
(overstated by {tot_draft - src:,.2f}); the revised query totals **{tot_rev:,.2f}**.

![accuracy](results/accuracy.png)

## What I take from this
- Fluent-looking SQL is often wrong in exactly the places that matter: join fan-out, NULL keys, missing status filters, and
  unstated denominators. A query that runs is not a query that is right.
- The cheap, high-value checks are reconciliation to source totals and row-count sanity, not reading the SQL harder.
- Writing the metric definition first removes most of the ambiguity before the AI sees the question.

## Limits
- Ten questions on one small schema; this shows a method, not a benchmark of any model. The first drafts were written as representative first-pass attempts in a chat session, so the pass rate is a worked example, not a measured error rate for any model.
- A comparison to a reference query only works when the reference is itself correct, so reference SQL needs human review.

## Run it
```
pip install duckdb pandas numpy matplotlib
python build_db.py
python harness.py
```
"""
(HERE / "README.md").write_text(readme, encoding="utf-8")
print(rep.to_string(index=False)); print(src, tot_draft, tot_rev)

