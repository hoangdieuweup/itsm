# Report Format

One entry per finding, ordered most-severe first. Group by file.

```
<relative/path/to/file.py>:<line>
  Rule: <exact or closely paraphrased rule text> — <skill-name>
  Problem: <what's actually wrong, in this code, not the rule restated>
  Fix: <concrete next step — a code change, not "consider reviewing this">
```

Example:

```
app/orders/repository.py:42
  Rule: "One table has exactly one owning module. Cross-module reads go through the facade." — fastapi-modular-scaffold
  Problem: get_order_with_user() joins orders.user_id directly against the users table instead of calling app.identity.public.get_user().
  Fix: replace the JOIN with a service-level call to identity's public facade; compose the two results in OrderService instead of in SQL.

app/orders/services/list_orders.py:18
  Rule: N+1 queries — references/backend-checks.md
  Problem: for order in orders: order.created_by.name loads the user relationship once per order.
  Fix: add .options(selectinload(Order.created_by)) to the query in repository.py.
```

End with a one-line summary: how many findings, how many files, and whether the standard tools (ruff/eslint/etc.) passed clean on top of these.

Don't report a finding twice because two different tools flagged the same line — dedupe by file+line+rule before printing.

If nothing is wrong, say so plainly — an empty findings list from a real check is a valid, useful result, not a sign the review was skipped.
