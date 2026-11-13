"""Build a SYNTHETIC e-commerce warehouse in DuckDB for the SQL-QA harness. Fixed seed, no employer data."""
from pathlib import Path
import duckdb, numpy as np, pandas as pd
rng = np.random.default_rng(5)
N = 3000
cust = pd.DataFrame({"customer_id": np.arange(1, N + 1),
    "signup_date": pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 540, N), unit="D"),
    "country": rng.choice(["US", "CA", "GB", "DE", "AU"], N, p=[.5, .1, .2, .12, .08]),
    "plan": rng.choice(["free", "plus", "pro"], N, p=[.6, .3, .1])})
orders, items, refunds = [], [], []
oid = iid = rid = 0
prices = rng.choice([9, 15, 25, 40, 60, 120], 40)
for c in cust.itertuples():
    k = rng.poisson(2.2 if c.plan != "free" else 1.2)
    t = c.signup_date + pd.Timedelta(days=int(rng.integers(0, 20)))
    for _ in range(k):
        t = t + pd.Timedelta(days=int(rng.integers(3, 70)), hours=int(rng.integers(0, 24)))
        if t > pd.Timestamp("2025-06-30"): break
        oid += 1
        n_items = int(rng.integers(1, 5)); amt = 0.0
        for _ in range(n_items):
            iid += 1; pr = float(rng.choice(prices)); q = int(rng.integers(1, 3)); amt += pr * q
            items.append((iid, oid, int(rng.integers(1, 41)), q, pr))
        disc = round(amt * float(rng.choice([0, 0, 0, .1, .2])), 2)
        status = rng.choice(["completed", "completed", "completed", "completed", "cancelled", "pending"], p=[.8, 0, 0, 0, .12, .08][:1] + [0, 0, 0, .12, .08]) if False else rng.choice(["completed", "cancelled", "pending"], p=[.82, .11, .07])
        orders.append((oid, c.customer_id, t, status, round(amt - disc, 2), disc))
        if status == "completed" and rng.random() < .12:
            for _ in range(int(rng.integers(1, 3))):          # multiple partial refunds per order
                rid += 1; refunds.append((rid, oid, round((amt - disc) * float(rng.uniform(.1, .5)), 2), t + pd.Timedelta(days=int(rng.integers(1, 20)))))
# a few orders with no customer (guest checkout) to create null-handling traps
orders = [(o[0], (None if rng.random() < .02 else o[1]), *o[2:]) for o in orders]
db = Path(__file__).parent / "shop.duckdb"
con = duckdb.connect(str(db))
for name, df in [("customers", cust),
    ("orders", pd.DataFrame(orders, columns=["order_id", "customer_id", "order_ts", "status", "amount", "discount"])),
    ("order_items", pd.DataFrame(items, columns=["item_id", "order_id", "product_id", "qty", "price"])),
    ("refunds", pd.DataFrame(refunds, columns=["refund_id", "order_id", "amount", "refund_ts"]))]:
    con.execute(f"create or replace table {name} as select * from df")
print({t: con.execute(f"select count(*) from {t}").fetchone()[0] for t in ["customers", "orders", "order_items", "refunds"]})
