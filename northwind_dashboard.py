"""
Northwind Sales Executive Dashboard
=====================================
FastAPI app serving a live sales dashboard from the Northwind PostgreSQL database.

Run:  uvicorn northwind_dashboard:app --reload
Then open http://127.0.0.1:8000
"""

import asyncio
import psycopg2
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

DB_URL = (
    "postgresql://northwind_reader:northwind_read_only"
    "@ep-patient-field-aqean10y.c-8.us-east-1.pg.koyeb.app:5432/koyebdb"
)

REFRESH_SECONDS = 300  # refresh cache every 5 minutes

app = FastAPI(title="Northwind Dashboard")

# In-memory cache populated at startup and refreshed on schedule
_cache: dict = {}


def fetch_all_data() -> dict:
    """Query the database and return all dashboard data."""
    conn = psycopg2.connect(DB_URL)
    with conn.cursor() as cur:

        cur.execute("""
            SELECT SUM(od."UnitPrice" * od."Quantity"),
                   COUNT(DISTINCT o."OrderID"),
                   COUNT(DISTINCT o."CustomerID")
            FROM order_details od
            JOIN orders o ON od."OrderID" = o."OrderID"
        """)
        total_rev, total_orders, customers = cur.fetchone()

        cur.execute("""
            SELECT TO_CHAR(DATE_TRUNC('month', o."OrderDate"::date), 'YYYY-MM'),
                   SUM(od."UnitPrice" * od."Quantity")
            FROM order_details od
            JOIN orders o ON od."OrderID" = o."OrderID"
            GROUP BY 1 ORDER BY 1
        """)
        monthly = [{"month": r[0], "revenue": round(r[1], 2)} for r in cur.fetchall()]

        cur.execute("""
            SELECT c."CategoryName", SUM(od."UnitPrice" * od."Quantity")
            FROM order_details od
            JOIN orders o ON od."OrderID" = o."OrderID"
            JOIN products p ON od."ProductID" = p."ProductID"
            JOIN categories c ON p."CategoryID" = c."CategoryID"
            GROUP BY 1 ORDER BY 2 DESC
        """)
        categories = [{"category": r[0], "revenue": round(r[1], 2)} for r in cur.fetchall()]

        cur.execute("""
            SELECT cu."CompanyName", cu."Country",
                   SUM(od."UnitPrice" * od."Quantity"),
                   COUNT(DISTINCT o."OrderID")
            FROM order_details od
            JOIN orders o ON od."OrderID" = o."OrderID"
            JOIN customers cu ON o."CustomerID" = cu."CustomerID"
            GROUP BY cu."CustomerID", cu."CompanyName", cu."Country"
            ORDER BY 3 DESC LIMIT 10
        """)
        top_customers = [
            {"rank": i + 1, "company": r[0], "country": r[1],
             "revenue": round(r[2], 2), "orders": r[3]}
            for i, r in enumerate(cur.fetchall())
        ]

    conn.close()
    return {
        "kpis": {
            "total_revenue":    round(total_rev, 2),
            "total_orders":     total_orders,
            "avg_order_value":  round(total_rev / total_orders, 2),
            "active_customers": customers,
        },
        "monthly":       monthly,
        "categories":    categories,
        "top_customers": top_customers,
    }


async def refresh_loop():
    while True:
        _cache.update(fetch_all_data())
        await asyncio.sleep(REFRESH_SECONDS)


@app.on_event("startup")
async def startup():
    _cache.update(fetch_all_data())
    asyncio.create_task(refresh_loop())


# ---------------------------------------------------------------------------
# API endpoints — serve from cache
# ---------------------------------------------------------------------------

@app.get("/api/kpis")
def kpis():
    return _cache.get("kpis", {})


@app.get("/api/revenue_by_month")
def revenue_by_month():
    return _cache.get("monthly", [])


@app.get("/api/revenue_by_category")
def revenue_by_category():
    return _cache.get("categories", [])


@app.get("/api/top_customers")
def top_customers():
    return _cache.get("top_customers", [])


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Northwind Sales Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  :root {
    --bg:       #0f1117;
    --surface:  #1c1f2e;
    --surface2: #252840;
    --border:   #363a55;
    --text:     #e2e8f0;
    --text-dim: #8892b0;
    --blue:     #7aa2f7;
    --purple:   #bb9af7;
    --green:    #9ece6a;
    --amber:    #e0af68;
    --red:      #f7768e;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 1.5rem 2rem 2rem;
  }

  /* Header */
  .header {
    display: flex;
    align-items: baseline;
    gap: 1rem;
    margin-bottom: 1.5rem;
  }
  h1 { font-size: 1.5rem; font-weight: 700; color: var(--blue); }
  .subtitle { font-size: 0.9rem; color: var(--text-dim); }

  /* KPI cards */
  .kpi-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.2rem;
  }
  .kpi-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
  }
  .kpi-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    margin-bottom: 0.4rem;
  }
  .kpi-value {
    font-size: 1.9rem;
    font-weight: 700;
    letter-spacing: -0.02em;
  }
  .kpi-card:nth-child(1) .kpi-value { color: var(--green); }
  .kpi-card:nth-child(2) .kpi-value { color: var(--blue); }
  .kpi-card:nth-child(3) .kpi-value { color: var(--amber); }
  .kpi-card:nth-child(4) .kpi-value { color: var(--purple); }

  /* Charts row */
  .charts-row {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 1rem;
    margin-bottom: 1.2rem;
  }
  .panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.4rem 0.5rem;
  }
  .panel-title {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    margin-bottom: 0.6rem;
    font-weight: 600;
  }

  /* Top customers table */
  .table-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1.2rem 1.4rem;
  }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  thead th {
    color: var(--blue);
    text-align: left;
    padding: 0.4rem 0.7rem;
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-bottom: 1px solid var(--border);
  }
  tbody td {
    padding: 0.5rem 0.7rem;
    border-bottom: 1px solid rgba(54,58,85,0.5);
    color: var(--text);
  }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr:hover { background: rgba(122,162,247,0.05); }
  .rank { color: var(--text-dim); font-variant-numeric: tabular-nums; }
  .revenue-cell { color: var(--green); font-weight: 600; font-variant-numeric: tabular-nums; }
  .orders-cell  { color: var(--blue);  font-variant-numeric: tabular-nums; }
</style>
</head>
<body>

<div class="header">
  <h1>Northwind Sales Dashboard</h1>
  <span class="subtitle">Historical performance across all markets</span>
</div>

<!-- KPIs -->
<div class="kpi-row">
  <div class="kpi-card"><div class="kpi-label">Total Revenue</div><div class="kpi-value" id="kpi-revenue">—</div></div>
  <div class="kpi-card"><div class="kpi-label">Total Orders</div><div class="kpi-value" id="kpi-orders">—</div></div>
  <div class="kpi-card"><div class="kpi-label">Avg Order Value</div><div class="kpi-value" id="kpi-avg">—</div></div>
  <div class="kpi-card"><div class="kpi-label">Active Customers</div><div class="kpi-value" id="kpi-customers">—</div></div>
</div>

<!-- Charts -->
<div class="charts-row">
  <div class="panel">
    <div class="panel-title">Revenue by Month</div>
    <div id="chart-time"></div>
  </div>
  <div class="panel">
    <div class="panel-title">Revenue by Category</div>
    <div id="chart-category"></div>
  </div>
</div>

<!-- Top customers -->
<div class="table-panel">
  <div class="panel-title">Top 10 Customers by Revenue</div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Company</th><th>Country</th>
        <th style="text-align:right">Revenue</th>
        <th style="text-align:right">Orders</th>
      </tr>
    </thead>
    <tbody id="customers-body"></tbody>
  </table>
</div>

<script>
const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };
const DARK = {
  paper_bgcolor: '#1c1f2e',
  plot_bgcolor:  '#1c1f2e',
  font:          { color: '#e2e8f0', family: 'Segoe UI, system-ui, sans-serif', size: 12 },
  margin:        { t: 10, b: 40, l: 60, r: 10 },
};

function fmt(n)  { return '$' + n.toLocaleString('en-US', {maximumFractionDigits: 0}); }
function fmtK(n) {
  if (n >= 1e6) return '$' + (n/1e6).toFixed(2) + 'M';
  if (n >= 1e3) return '$' + (n/1e3).toFixed(1) + 'K';
  return '$' + n.toFixed(0);
}

async function load() {
  const [kpis, monthly, cats, customers] = await Promise.all([
    fetch('api/kpis').then(r => r.json()),
    fetch('api/revenue_by_month').then(r => r.json()),
    fetch('api/revenue_by_category').then(r => r.json()),
    fetch('api/top_customers').then(r => r.json()),
  ]);

  // KPIs
  document.getElementById('kpi-revenue').textContent   = fmtK(kpis.total_revenue);
  document.getElementById('kpi-orders').textContent    = kpis.total_orders.toLocaleString();
  document.getElementById('kpi-avg').textContent       = fmtK(kpis.avg_order_value);
  document.getElementById('kpi-customers').textContent = kpis.active_customers.toLocaleString();

  // Revenue by month (line chart)
  Plotly.newPlot('chart-time', [{
    x: monthly.map(d => d.month),
    y: monthly.map(d => d.revenue),
    type: 'scatter', mode: 'lines+markers',
    line:    { color: '#7aa2f7', width: 2.5, shape: 'spline' },
    marker:  { color: '#7aa2f7', size: 5 },
    fill:    'tozeroy',
    fillcolor: 'rgba(122,162,247,0.08)',
    hovertemplate: '%{x}<br>%{y:$,.0f}<extra></extra>',
  }], {
    ...DARK,
    xaxis: { gridcolor: '#363a55', tickfont: { size: 11 } },
    yaxis: { gridcolor: '#363a55', tickformat: '$,.0f', tickfont: { size: 11 } },
    height: 260,
  }, PLOTLY_CONFIG);

  // Revenue by category (horizontal bar)
  const catColors = ['#7aa2f7','#bb9af7','#9ece6a','#e0af68','#f7768e','#2ac3de','#ff9e64','#73daca'];
  Plotly.newPlot('chart-category', [{
    x:           cats.map(d => d.revenue),
    y:           cats.map(d => d.category),
    type:        'bar',
    orientation: 'h',
    marker:      { color: catColors.slice(0, cats.length) },
    hovertemplate: '%{y}<br>%{x:$,.0f}<extra></extra>',
  }], {
    ...DARK,
    margin: { t: 10, b: 40, l: 120, r: 20 },
    xaxis:  { gridcolor: '#363a55', tickformat: '$,.0f', tickfont: { size: 10 } },
    yaxis:  { gridcolor: 'transparent', tickfont: { size: 11 }, autorange: 'reversed' },
    height: 260,
  }, PLOTLY_CONFIG);

  // Top customers table
  const tbody = document.getElementById('customers-body');
  tbody.innerHTML = customers.map(c => `
    <tr>
      <td class="rank">${c.rank}</td>
      <td>${c.company}</td>
      <td style="color:var(--text-dim)">${c.country}</td>
      <td class="revenue-cell" style="text-align:right">${fmt(c.revenue)}</td>
      <td class="orders-cell"  style="text-align:right">${c.orders}</td>
    </tr>`).join('');
}

load();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8003)
