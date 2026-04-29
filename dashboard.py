import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import os

st.set_page_config(
    page_title="OpenRouter Spend Dashboard",
    page_icon="💸",
    layout="wide"
)

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"

def get_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

def fetch_key_info(api_key):
    r = requests.get(f"{BASE_URL}/auth/key", headers=get_headers(api_key), timeout=10)
    if r.status_code == 200:
        return r.json().get("data", {})
    return {}

def fetch_generations(api_key, offset=0, limit=100):
    r = requests.get(
        f"{BASE_URL}/generations",
        headers=get_headers(api_key),
        params={"offset": offset, "limit": limit},
        timeout=10
    )
    if r.status_code == 200:
        return r.json().get("data", [])
    return []

def load_all_generations(api_key, max_records=1000):
    all_records = []
    offset = 0
    batch = 100
    while offset < max_records:
        records = fetch_generations(api_key, offset=offset, limit=batch)
        if not records:
            break
        all_records.extend(records)
        offset += batch
    return all_records

def build_dataframe(records):
    if not records:
        return pd.DataFrame()
    rows = []
    for r in records:
        rows.append({
            "id": r.get("id", ""),
            "model": r.get("model", "Unknown"),
            "timestamp": r.get("created_at", ""),
            "cost": (r.get("usage", {}) or {}).get("cost", 0) or 0,
            "prompt_tokens": (r.get("usage", {}) or {}).get("prompt_tokens", 0) or 0,
            "completion_tokens": (r.get("usage", {}) or {}).get("completion_tokens", 0) or 0,
            "total_tokens": (r.get("usage", {}) or {}).get("total_tokens", 0) or 0,
            "app": r.get("app_id") or r.get("origin") or "Unknown",
        })
    df = pd.DataFrame(rows)
    if not df.empty and "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df["date"] = df["timestamp"].dt.date
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.day_name()
    return df

# ── Sidebar ────────────────────────────────────────────────
st.sidebar.title("⚙️ Settings")
api_key = st.sidebar.text_input(
    "OpenRouter API Key",
    value=OPENROUTER_API_KEY,
    type="password",
    help="Your OpenRouter API key"
)
st.sidebar.divider()
date_range = st.sidebar.date_input(
    "Date Range",
    value=(datetime.now().date() - timedelta(days=30), datetime.now().date()),
)
if st.sidebar.button("🔄 Refresh"):
    st.cache_data.clear()
    st.rerun()

# ── Main ───────────────────────────────────────────────────
st.title("💸 OpenRouter Spend Dashboard")

if not api_key:
    st.warning("Enter your OpenRouter API key in the sidebar to get started.")
    st.stop()

# Key summary metrics (always available)
with st.spinner("Loading account info..."):
    key_info = fetch_key_info(api_key)

if not key_info:
    st.error("Could not fetch account data — check your API key.")
    st.stop()

# ── Top metrics from key info ──────────────────────────────
st.subheader("📊 Account Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Spend (All Time)", f"${key_info.get('usage_monthly', 0):.4f}")
c2.metric("This Week", f"${key_info.get('usage_weekly', 0):.4f}")
c3.metric("Today", f"${key_info.get('usage_daily', 0):.4f}")
daily_limit = key_info.get("limit", None)
c4.metric("Daily Limit", f"${daily_limit:.2f}" if daily_limit else "None")

st.divider()

# ── Generation history ─────────────────────────────────────
with st.spinner("Loading generation history..."):
    records = load_all_generations(api_key, max_records=1000)

df = build_dataframe(records)

if df.empty:
    st.info("No generation history found yet.")
    st.stop()

# Filter by date range
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start, end = date_range
    df = df[(df["date"] >= start) & (df["date"] <= end)]

if df.empty:
    st.warning("No data in selected date range.")
    st.stop()

# ── Spend by Model ─────────────────────────────────────────
st.subheader("🤖 Spend by Model")
model_df = (
    df.groupby("model")
    .agg(total_cost=("cost", "sum"), requests=("id", "count"), tokens=("total_tokens", "sum"))
    .sort_values("total_cost", ascending=False)
    .reset_index()
)
model_df["total_cost"] = model_df["total_cost"].apply(lambda x: round(x, 6))

col_a, col_b = st.columns([1, 1])
with col_a:
    st.dataframe(model_df, use_container_width=True, hide_index=True)
with col_b:
    fig = px.pie(model_df, values="total_cost", names="model",
                 title="Cost Share by Model", hole=0.4)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Spend by App/Origin (project proxy) ────────────────────
st.subheader("📁 Spend by App / Project")
app_df = (
    df.groupby("app")
    .agg(total_cost=("cost", "sum"), requests=("id", "count"))
    .sort_values("total_cost", ascending=False)
    .reset_index()
)
app_df["total_cost"] = app_df["total_cost"].apply(lambda x: round(x, 6))

col_c, col_d = st.columns([1, 1])
with col_c:
    st.dataframe(app_df, use_container_width=True, hide_index=True)
with col_d:
    fig2 = px.bar(app_df, x="app", y="total_cost",
                  title="Cost by App/Project", labels={"total_cost": "Cost ($)", "app": "App"})
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Daily Trend ────────────────────────────────────────────
st.subheader("📈 Daily Spend Trend")
daily_df = df.groupby("date")["cost"].sum().reset_index()
fig3 = px.line(daily_df, x="date", y="cost",
               title="Daily Spend", labels={"cost": "Cost ($)", "date": "Date"},
               markers=True)
st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ── Raw log ────────────────────────────────────────────────
with st.expander("🔍 Raw Generation Log"):
    st.dataframe(
        df[["timestamp", "model", "app", "cost", "prompt_tokens", "completion_tokens", "total_tokens"]]
        .sort_values("timestamp", ascending=False),
        use_container_width=True,
        hide_index=True
    )
