import functions_framework
import json
import os
import random
import uuid
from datetime import datetime, timezone

import pg8000.native


PRODUCTS = ["SKU-1001-HEADPHONES", "SKU-2042-LAPTOP", "SKU-3017-KEYBOARD", "SKU-4088-MONITOR"]
USERS = ["user-alice", "user-bob", "user-carol", "user-dave", "user-eve"]


def _log(severity, message, **fields):
    """Print a structured JSON log entry. Cloud Logging parses stdout JSON automatically."""
    entry = {"severity": severity, "message": message, **fields}
    print(json.dumps(entry))
    return entry


def get_db_connection():
    """Connect to Cloud SQL PostgreSQL via the Unix socket mounted by Cloud Run."""
    connection_name = os.environ["CLOUD_SQL_CONNECTION_NAME"]
    return pg8000.native.Connection(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASS"],
        database=os.environ["DB_NAME"],
        unix_sock=f"/cloudsql/{connection_name}/.s.PGSQL.5432",
    )


def ensure_table(conn):
    conn.run("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          SERIAL PRIMARY KEY,
            session_id  TEXT        NOT NULL,
            user_id     TEXT        NOT NULL,
            event       TEXT        NOT NULL,
            product_id  TEXT,
            amount      NUMERIC(10,2),
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def insert_events(conn, session_id, user, events):
    """Bulk-insert session events into the database."""
    for e in events:
        conn.run(
            "INSERT INTO sessions (session_id, user_id, event, product_id, amount) "
            "VALUES (:sid, :uid, :evt, :pid, :amt)",
            sid=session_id,
            uid=user,
            evt=e["message"],
            pid=e.get("product_id"),
            amt=e.get("cart_total") or e.get("order_total"),
        )


def recent_sessions(conn, limit=5):
    """Return the most recent session rows for display."""
    rows = conn.run(
        "SELECT session_id, user_id, event, product_id, amount, created_at "
        "FROM sessions ORDER BY created_at DESC LIMIT :lim",
        lim=limit,
    )
    cols = ["session_id", "user_id", "event", "product_id", "amount", "created_at"]
    return [dict(zip(cols, row)) for row in rows]


def session_count(conn):
    return conn.run("SELECT COUNT(*) FROM sessions")[0][0]


@functions_framework.http
def log_generator(request):
    session_id = str(uuid.uuid4())[:8]
    user = random.choice(USERS)
    product = random.choice(PRODUCTS)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Generate structured log events ──────────────────────────────────────
    logged = []

    logged.append(_log(
        "INFO", "User session started",
        session_id=session_id, user_id=user,
        source="log-generator-function", timestamp=ts,
    ))
    logged.append(_log(
        "INFO", "Product page viewed",
        session_id=session_id, user_id=user,
        product_id=product, page=f"/products/{product}",
        response_time_ms=random.randint(40, 180),
    ))
    logged.append(_log(
        "INFO", "Item added to cart",
        session_id=session_id, user_id=user,
        product_id=product, quantity=random.randint(1, 3),
        cart_total=round(random.uniform(49.99, 299.99), 2),
    ))
    if random.random() < 0.4:
        logged.append(_log(
            "WARNING", "Low stock alert triggered",
            session_id=session_id, product_id=product,
            stock_remaining=random.randint(1, 4),
        ))
    if random.random() < 0.25:
        logged.append(_log(
            "ERROR", "Payment gateway timeout",
            session_id=session_id, user_id=user,
            gateway="stripe", timeout_ms=5000, will_retry=True,
        ))
    else:
        logged.append(_log(
            "INFO", "Checkout completed",
            session_id=session_id, user_id=user, product_id=product,
            order_total=round(random.uniform(49.99, 299.99), 2),
            payment_method="card",
        ))

    # ── Database operations ──────────────────────────────────────────────────
    db_error = None
    recent = []
    total_sessions = 0

    try:
        conn = get_db_connection()
        ensure_table(conn)
        insert_events(conn, session_id, user, logged)
        recent = recent_sessions(conn)
        total_sessions = session_count(conn)
        conn.close()

        _log("INFO", "Database write complete",
             session_id=session_id, rows_inserted=len(logged),
             total_sessions=total_sessions, source="log-generator-function")

    except Exception as exc:
        db_error = str(exc)
        _log("ERROR", "Database operation failed",
             session_id=session_id, error=db_error,
             source="log-generator-function")

    # ── Build HTML response ──────────────────────────────────────────────────
    log_rows = []
    for e in logged:
        severity = e["severity"]
        colour = {"INFO": "#2563eb", "WARNING": "#d97706", "ERROR": "#dc2626"}.get(severity, "#6b7280")
        badge = f'<span style="background:{colour};color:#fff;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600">{severity}</span>'
        fields = {k: v for k, v in e.items() if k not in ("severity", "message")}
        fields_str = " &nbsp;·&nbsp; ".join(f'<code>{k}={json.dumps(v)}</code>' for k, v in fields.items())
        log_rows.append(f"<tr><td style='padding:10px 12px'>{badge}</td><td style='padding:10px 12px'><strong>{e['message']}</strong><br><small style='color:#6b7280'>{fields_str}</small></td></tr>")

    db_rows_html = ""
    if recent:
        db_table_rows = "".join(
            f"<tr><td>{r['session_id']}</td><td>{r['user_id']}</td><td>{r['event']}</td>"
            f"<td>{r['product_id'] or '—'}</td><td>{r['amount'] or '—'}</td>"
            f"<td>{str(r['created_at'])[:19]}</td></tr>"
            for r in recent
        )
        db_rows_html = f"""
        <h2 style="margin-top:40px;font-size:18px">🗄️ Recent database rows <small style="color:#6b7280;font-size:14px;font-weight:400">(last 5 of {total_sessions} total)</small></h2>
        <table style="width:100%;border-collapse:collapse;background:#f9fafb;border-radius:8px;overflow:hidden;font-size:13px">
          <thead><tr style="background:#f3f4f6">
            <th style="padding:8px 12px;text-align:left;color:#6b7280">session_id</th>
            <th style="padding:8px 12px;text-align:left;color:#6b7280">user_id</th>
            <th style="padding:8px 12px;text-align:left;color:#6b7280">event</th>
            <th style="padding:8px 12px;text-align:left;color:#6b7280">product_id</th>
            <th style="padding:8px 12px;text-align:left;color:#6b7280">amount</th>
            <th style="padding:8px 12px;text-align:left;color:#6b7280">created_at</th>
          </tr></thead>
          <tbody style="font-family:monospace">{db_table_rows}</tbody>
        </table>"""
    elif db_error:
        db_rows_html = f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin-top:24px;color:#991b1b"><strong>Database error:</strong> {db_error}</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Log Generator — GCP → Elasticsearch Demo</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 900px; margin: 48px auto; padding: 0 24px; color: #1f2937; }}
    h1 {{ font-size: 24px; margin-bottom: 4px; }}
    .subtitle {{ color: #6b7280; margin-bottom: 32px; }}
    .badge {{ background: #d1fae5; color: #065f46; padding: 4px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; }}
    table {{ width: 100%; border-collapse: collapse; background: #f9fafb; border-radius: 8px; overflow: hidden; margin: 24px 0; }}
    th {{ background: #f3f4f6; padding: 10px 12px; text-align: left; font-size: 13px; color: #6b7280; font-weight: 600; }}
    tr:not(:last-child) {{ border-bottom: 1px solid #e5e7eb; }}
    td {{ padding: 8px 12px; }}
    code {{ font-size: 12px; background: #e5e7eb; padding: 1px 4px; border-radius: 3px; }}
    .info {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px 20px; margin: 24px 0; font-size: 14px; }}
    .pipeline {{ display: flex; align-items: center; gap: 8px; font-size: 13px; color: #6b7280; margin: 16px 0; flex-wrap: wrap; }}
    .step {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 12px; color: #1f2937; font-weight: 500; }}
    .arrow {{ color: #9ca3af; }}
  </style>
</head>
<body>
  <h1>🪵 Log Generator</h1>
  <p class="subtitle">GCP Cloud Function + Cloud SQL → Cloud Logging → Pub/Sub → Dataflow → Elasticsearch</p>

  <span class="badge">✓ {len(logged)} log events emitted</span>
  &nbsp; Session: <code>{session_id}</code>
  &nbsp; User: <code>{user}</code>

  <div class="pipeline">
    <span class="step">Cloud Function</span><span class="arrow">→</span>
    <span class="step">Cloud SQL (PostgreSQL)</span><span class="arrow">→</span>
    <span class="step">Cloud Logging</span><span class="arrow">→</span>
    <span class="step">Pub/Sub</span><span class="arrow">→</span>
    <span class="step">Dataflow</span><span class="arrow">→</span>
    <span class="step">Elasticsearch <code>logs.ecs</code></span>
  </div>

  <h2 style="font-size:18px;margin-top:32px">📋 Log events emitted this request</h2>
  <table>
    <thead><tr><th>Severity</th><th>Event</th></tr></thead>
    <tbody>{"".join(log_rows)}</tbody>
  </table>

  {db_rows_html}

  <div class="info">
    ⏱ Logs typically arrive in Elasticsearch within <strong>60–90 seconds</strong> via the Dataflow pipeline.<br><br>
    Two types of logs flow through for each request:<br>
    • <strong>Cloud Function stdout</strong> — the structured events above, tagged with <code>session_id={session_id}</code><br>
    • <strong>Cloud SQL postgres.log</strong> — the actual SQL statements executed against the database<br><br>
    Reload this page to generate a new batch of events.
  </div>
</body>
</html>"""

    return (html, 200, {"Content-Type": "text/html; charset=utf-8"})
