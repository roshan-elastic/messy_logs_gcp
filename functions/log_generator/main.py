import functions_framework
import json
import uuid
import random
from datetime import datetime, timezone


PRODUCTS = ["SKU-1001-HEADPHONES", "SKU-2042-LAPTOP", "SKU-3017-KEYBOARD", "SKU-4088-MONITOR"]
USERS = ["user-alice", "user-bob", "user-carol", "user-dave", "user-eve"]
PAGES = ["/", "/products", "/cart", "/checkout", "/account"]


def _log(severity, message, **fields):
    """Print a structured JSON log entry. Cloud Logging parses stdout JSON automatically."""
    entry = {"severity": severity, "message": message, **fields}
    print(json.dumps(entry))
    return entry


@functions_framework.http
def log_generator(request):
    session_id = str(uuid.uuid4())[:8]
    user = random.choice(USERS)
    product = random.choice(PRODUCTS)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    logged = []

    logged.append(_log(
        "INFO", "User session started",
        session_id=session_id,
        user_id=user,
        source="log-generator-function",
        timestamp=ts,
    ))

    logged.append(_log(
        "INFO", "Product page viewed",
        session_id=session_id,
        user_id=user,
        product_id=product,
        page="/products/" + product,
        response_time_ms=random.randint(40, 180),
    ))

    logged.append(_log(
        "INFO", "Item added to cart",
        session_id=session_id,
        user_id=user,
        product_id=product,
        quantity=random.randint(1, 3),
        cart_total=round(random.uniform(49.99, 299.99), 2),
    ))

    if random.random() < 0.4:
        logged.append(_log(
            "WARNING", "Low stock alert triggered",
            session_id=session_id,
            product_id=product,
            stock_remaining=random.randint(1, 4),
        ))

    if random.random() < 0.25:
        logged.append(_log(
            "ERROR", "Payment gateway timeout",
            session_id=session_id,
            user_id=user,
            gateway="stripe",
            timeout_ms=5000,
            will_retry=True,
        ))
    else:
        logged.append(_log(
            "INFO", "Checkout completed",
            session_id=session_id,
            user_id=user,
            product_id=product,
            order_total=round(random.uniform(49.99, 299.99), 2),
            payment_method="card",
        ))

    rows = []
    for e in logged:
        severity = e["severity"]
        colour = {"INFO": "#2563eb", "WARNING": "#d97706", "ERROR": "#dc2626"}.get(severity, "#6b7280")
        badge = f'<span style="background:{colour};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600">{severity}</span>'
        msg = e["message"]
        fields = {k: v for k, v in e.items() if k not in ("severity", "message")}
        fields_str = " &nbsp;·&nbsp; ".join(f'<code>{k}={json.dumps(v)}</code>' for k, v in fields.items())
        rows.append(f"<tr><td style='padding:10px 12px'>{badge}</td><td style='padding:10px 12px'><strong>{msg}</strong><br><small style='color:#6b7280'>{fields_str}</small></td></tr>")

    table_rows = "\n".join(rows)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Log Generator — GCP → Elasticsearch Demo</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 48px auto; padding: 0 24px; color: #1f2937; }}
    h1 {{ font-size: 24px; margin-bottom: 4px; }}
    .subtitle {{ color: #6b7280; margin-bottom: 32px; }}
    .badge {{ background: #d1fae5; color: #065f46; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; background: #f9fafb; border-radius: 8px; overflow: hidden; margin: 24px 0; }}
    th {{ background: #f3f4f6; padding: 10px 12px; text-align: left; font-size: 13px; color: #6b7280; font-weight: 600; }}
    tr:not(:last-child) {{ border-bottom: 1px solid #e5e7eb; }}
    code {{ font-size: 12px; background: #e5e7eb; padding: 1px 4px; border-radius: 3px; }}
    .info {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px 20px; margin: 24px 0; font-size: 14px; }}
    .pipeline {{ display: flex; align-items: center; gap: 8px; font-size: 13px; color: #6b7280; margin: 16px 0; flex-wrap: wrap; }}
    .step {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 12px; color: #1f2937; font-weight: 500; }}
    .arrow {{ color: #9ca3af; }}
    a {{ color: #2563eb; }}
  </style>
</head>
<body>
  <h1>🪵 Log Generator</h1>
  <p class="subtitle">GCP Cloud Function → Cloud Logging → Pub/Sub → Dataflow → Elasticsearch</p>

  <span class="badge">✓ {len(logged)} log events emitted</span> &nbsp; Session: <code>{session_id}</code> &nbsp; User: <code>{user}</code>

  <div class="pipeline">
    <span class="step">Cloud Function (this page)</span><span class="arrow">→</span>
    <span class="step">Cloud Logging</span><span class="arrow">→</span>
    <span class="step">Log Router → Pub/Sub</span><span class="arrow">→</span>
    <span class="step">Dataflow</span><span class="arrow">→</span>
    <span class="step">Elasticsearch <code>logs.ecs</code></span>
  </div>

  <table>
    <thead><tr><th>Severity</th><th>Event</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>

  <div class="info">
    ⏱ Logs typically arrive in Elasticsearch within <strong>60–90 seconds</strong> via the Dataflow pipeline.<br><br>
    To find them, query <code>logs.ecs</code> for the last 5 minutes. All events above share
    <code>session_id={session_id}</code> — look for that in <code>jsonPayload.session_id</code>.<br><br>
    Reload this page to generate a new batch of events.
  </div>
</body>
</html>"""

    return (html, 200, {"Content-Type": "text/html; charset=utf-8"})
