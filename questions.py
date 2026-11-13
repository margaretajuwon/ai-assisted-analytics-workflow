"""Ten business questions. For each: a reference (golden) SQL written and reviewed by hand, and the FIRST-DRAFT SQL an AI assistant
(Claude) produced from the question text and schema alone. `revised` holds the fix after the harness flagged a failure (or None).
Definitions are stated in each question so correctness is checkable. Completed orders only unless stated."""
Q = [
 dict(id="Q1", q="Monthly net revenue = completed order amount minus refunds on those orders, by the month of the ORDER.",
  golden="""with rev as (select date_trunc('month', order_ts)::date m, sum(amount) gross from orders where status='completed' group by 1),
ref as (select date_trunc('month', o.order_ts)::date m, sum(r.amount) refunded from refunds r join orders o using(order_id) where o.status='completed' group by 1)
select rev.m as month, round(gross - coalesce(refunded,0),2) as net_revenue from rev left join ref using(m) order by 1""",
  draft="""select date_trunc('month', o.order_ts)::date as month, round(sum(o.amount - coalesce(r.amount,0)),2) as net_revenue
from orders o left join refunds r on r.order_id = o.order_id where o.status='completed' group by 1 order by 1""",
  revised="""with ref as (select order_id, sum(amount) refunded from refunds group by 1)
select date_trunc('month', o.order_ts)::date as month, round(sum(o.amount - coalesce(ref.refunded,0)),2) as net_revenue
from orders o left join ref using(order_id) where o.status='completed' group by 1 order by 1"""),
 dict(id="Q2", q="How many customers have at least 2 completed orders? (Orders with no customer are guest checkouts and are not customers.)",
  golden="""select count(*) as customers from (select customer_id from orders where status='completed' and customer_id is not null group by 1 having count(*)>=2)""",
  draft="""select count(*) as customers from (select customer_id from orders where status='completed' group by customer_id having count(*) >= 2)""",
  revised="""select count(*) as customers from (select customer_id from orders where status='completed' and customer_id is not null group by customer_id having count(*) >= 2)"""),
 dict(id="Q3", q="Average completed-order value by customer country (exclude guest orders).",
  golden="""select c.country, round(avg(o.amount),2) as aov from orders o join customers c using(customer_id) where o.status='completed' group by 1 order by 1""",
  draft="""select c.country, round(avg(o.amount),2) as aov from orders o join customers c on c.customer_id=o.customer_id where o.status='completed' group by c.country order by c.country""",
  revised=None),
 dict(id="Q4", q="Top 5 products by revenue (qty x price) on completed orders.",
  golden="""select i.product_id, round(sum(i.qty*i.price),2) as revenue from order_items i join orders o using(order_id) where o.status='completed' group by 1 order by 2 desc, 1 limit 5""",
  draft="""select product_id, round(sum(qty*price),2) as revenue from order_items group by 1 order by 2 desc, 1 limit 5""",
  revised="""select i.product_id, round(sum(i.qty*i.price),2) as revenue from order_items i join orders o on o.order_id=i.order_id where o.status='completed' group by 1 order by 2 desc, 1 limit 5"""),
 dict(id="Q5", q="Monthly refund rate = refunded amount / completed order amount, by month of the order.",
  golden="""with rev as (select date_trunc('month', order_ts)::date m, sum(amount) gross from orders where status='completed' group by 1),
ref as (select date_trunc('month', o.order_ts)::date m, sum(r.amount) refunded from refunds r join orders o using(order_id) where o.status='completed' group by 1)
select rev.m as month, round(coalesce(refunded,0)/gross,4) as refund_rate from rev left join ref using(m) order by 1""",
  draft="""select date_trunc('month', o.order_ts)::date as month, round(sum(coalesce(r.amount,0))/sum(o.amount),4) as refund_rate
from orders o left join refunds r on r.order_id=o.order_id where o.status='completed' group by 1 order by 1""",
  revised="""with ref as (select order_id, sum(amount) refunded from refunds group by 1)
select date_trunc('month', o.order_ts)::date as month, round(sum(coalesce(ref.refunded,0))/sum(o.amount),4) as refund_rate
from orders o left join ref using(order_id) where o.status='completed' group by 1 order by 1"""),
 dict(id="Q6", q="By signup month: share of customers with a completed order who placed at least 2 completed orders (repeat rate).",
  golden="""with n as (select customer_id, count(*) k from orders where status='completed' and customer_id is not null group by 1)
select date_trunc('month', c.signup_date)::date as signup_month, round(avg(case when n.k>=2 then 1.0 else 0 end),4) as repeat_rate
from n join customers c using(customer_id) group by 1 order by 1""",
  draft="""select date_trunc('month', c.signup_date)::date as signup_month,
 round(count(distinct case when t.k>=2 then c.customer_id end)*1.0/count(distinct c.customer_id),4) as repeat_rate
from customers c left join (select customer_id, count(*) k from orders where status='completed' group by 1) t using(customer_id)
group by 1 order by 1""",
  revised="""with n as (select customer_id, count(*) k from orders where status='completed' and customer_id is not null group by 1)
select date_trunc('month', c.signup_date)::date as signup_month, round(avg(case when n.k>=2 then 1.0 else 0 end),4) as repeat_rate
from n join customers c using(customer_id) group by 1 order by 1"""),
 dict(id="Q7", q="Median days between a customer's first and second completed order (customers with at least 2).",
  golden="""with o as (select customer_id, order_ts, row_number() over (partition by customer_id order by order_ts) rn from orders where status='completed' and customer_id is not null)
select round(median(date_diff('second', a.order_ts, b.order_ts)/86400.0),2) as median_days from o a join o b on a.customer_id=b.customer_id and a.rn=1 and b.rn=2""",
  draft="""with o as (select customer_id, order_ts, lead(order_ts) over (partition by customer_id order by order_ts) nxt, row_number() over (partition by customer_id order by order_ts) rn
 from orders where status='completed' and customer_id is not null)
select round(median(date_diff('second', order_ts, nxt)/86400.0),2) as median_days from o where rn=1 and nxt is not null""",
  revised=None),
 dict(id="Q8", q="Completed orders and revenue by customer plan (exclude guest orders).",
  golden="""select c.plan, count(*) as orders, round(sum(o.amount),2) as revenue from orders o join customers c using(customer_id) where o.status='completed' group by 1 order by 1""",
  draft="""select c.plan, count(o.order_id) as orders, round(sum(o.amount),2) as revenue from customers c join orders o on o.customer_id=c.customer_id where o.status='completed' group by c.plan order by c.plan""",
  revised=None),
 dict(id="Q9", q="Of customers whose FIRST completed order had a discount (>0), how many placed a second completed order?",
  golden="""with o as (select customer_id, discount, row_number() over (partition by customer_id order by order_ts) rn, count(*) over (partition by customer_id) k
 from orders where status='completed' and customer_id is not null)
select count(*) as customers from o where rn=1 and discount>0 and k>=2""",
  draft="""select count(distinct o1.customer_id) as customers from orders o1 join orders o2 on o1.customer_id=o2.customer_id and o2.order_ts>o1.order_ts and o2.status='completed'
where o1.status='completed' and o1.discount>0""",
  revised="""with o as (select customer_id, discount, row_number() over (partition by customer_id order by order_ts) rn, count(*) over (partition by customer_id) k
 from orders where status='completed' and customer_id is not null)
select count(*) as customers from o where rn=1 and discount>0 and k>=2"""),
 dict(id="Q10", q="Share of customers (with at least 1 completed order) whose second completed order came within 30 days of the first.",
  golden="""with o as (select customer_id, order_ts, row_number() over (partition by customer_id order by order_ts) rn from orders where status='completed' and customer_id is not null),
f as (select customer_id, max(case when rn=1 then order_ts end) t1, max(case when rn=2 then order_ts end) t2 from o group by 1)
select round(avg(case when t2 is not null and date_diff('second', t1, t2) <= 30*86400 then 1.0 else 0 end),4) as share_30d from f""",
  draft="""with o as (select customer_id, order_ts, row_number() over (partition by customer_id order by order_ts) rn from orders where status='completed' and customer_id is not null)
select round(count(distinct case when b.order_ts <= a.order_ts + interval 30 day then a.customer_id end)*1.0/(select count(distinct customer_id) from o),4) as share_30d
from o a join o b on a.customer_id=b.customer_id and a.rn=1 and b.rn=2""",
  revised=None),
]
