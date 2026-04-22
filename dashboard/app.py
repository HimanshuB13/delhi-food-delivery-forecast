import streamlit as st
import redis
import json
import joblib
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sys
import os
from datetime import datetime
import time

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.predictor import predict_all_zones, ZONES, r

st.set_page_config(
    page_title='Delhi Food Delivery — Live Demand Forecast',
    page_icon='🍕',
    layout='wide'
)

# ── Auto refresh every 30 seconds ──────────────────────────────────────────
st.markdown("""
<meta http-equiv="refresh" content="30">
<style>
    .metric-card { background: #1E1E2E; border-radius: 10px; padding: 15px; }
    .surge { color: #E24B4A; font-weight: bold; }
    .normal { color: #1D9E75; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ── Header ──────────────────────────────────────────────────────────────────
st.title('🍕 Delhi Food Delivery — Live Demand Forecast')
st.markdown(f"Last updated: **{datetime.now().strftime('%d %b %Y, %I:%M %p')}** | Auto-refreshes every 30 seconds")
st.divider()

# ── Live weather from Redis ─────────────────────────────────────────────────
weather = r.hgetall('current_weather')

if weather:
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("🌡️ Temperature",  f"{float(weather.get('temperature', 0)):.1f}°C")
    col2.metric("💧 Humidity",     f"{weather.get('humidity', 'N/A')}%")
    col3.metric("💨 Wind Speed",   f"{float(weather.get('wind_speed', 0)):.1f} km/h")
    col4.metric("🌦️ Condition",    weather.get('weather_desc', 'N/A').title())
    col5.metric("🌧️ Raining",      "Yes 🌧️" if weather.get('is_raining') == 'True' else "No ☀️")
else:
    st.warning("Weather data not available — make sure weather producer is running")

st.divider()

# ── Live predictions ─────────────────────────────────────────────────────────
st.subheader("📊 Live demand predictions — next 30 minutes")

predictions = predict_all_zones()

# Metric cards for each zone
cols = st.columns(3)
for i, (zone_id, pred) in enumerate(predictions.items()):
    zone_info   = ZONES[zone_id]
    base_demand = zone_info['base_demand']
    predicted   = pred['predicted']
    pct_change  = ((predicted - base_demand) / base_demand) * 100
    delta_str   = f"{pct_change:+.0f}% vs baseline"

    with cols[i % 3]:
        st.metric(
            label=pred['zone_name'],
            value=f"{predicted} orders",
            delta=delta_str
        )

st.divider()

# ── Bar chart — current predictions ─────────────────────────────────────────
st.subheader("🗺️ Demand by zone")

pred_df = pd.DataFrame([
    {
        'zone':      pred['zone_name'].split('/')[0].strip(),
        'predicted': pred['predicted'],
        'baseline':  ZONES[zone_id]['base_demand']
    }
    for zone_id, pred in predictions.items()
])

fig = go.Figure()
fig.add_trace(go.Bar(
    name='Predicted demand',
    x=pred_df['zone'],
    y=pred_df['predicted'],
    marker_color='#7F77DD',
    text=pred_df['predicted'],
    textposition='outside'
))
fig.add_trace(go.Bar(
    name='Baseline demand',
    x=pred_df['zone'],
    y=pred_df['baseline'],
    marker_color='#888888',
    opacity=0.5
))
fig.update_layout(
    barmode='group',
    title='Predicted vs baseline demand per zone',
    xaxis_title='Delhi Zone',
    yaxis_title='Orders per 30 min',
    height=400,
    legend=dict(orientation='h', y=1.1)
)
st.plotly_chart(fig, use_container_width=True, key='bar_chart')

st.divider()

# ── Order history per zone ───────────────────────────────────────────────────
st.subheader("📈 Real-time order history")

selected_zone = st.selectbox(
    'Select zone to view history',
    options=list(ZONES.keys()),
    format_func=lambda z: ZONES[z]['name']
)

history_raw = r.lrange(f'order_history:{selected_zone}', 0, 49)

if history_raw:
    history = [json.loads(h) for h in history_raw]
    hist_df = pd.DataFrame(history)
    hist_df['timestamp'] = pd.to_datetime(hist_df['timestamp'])
    hist_df = hist_df.sort_values('timestamp')

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=hist_df['timestamp'],
        y=hist_df['orders'],
        mode='lines+markers',
        name='Actual orders',
        line=dict(color='#1D9E75', width=2),
        marker=dict(size=5)
    ))
    fig2.add_trace(go.Scatter(
        x=hist_df['timestamp'],
        y=hist_df['expected'],
        mode='lines',
        name='Expected orders',
        line=dict(color='#E24B4A', width=1.5, dash='dash')
    ))
    fig2.update_layout(
        title=f'Order history — {ZONES[selected_zone]["name"]}',
        xaxis_title='Time',
        yaxis_title='Orders',
        height=350
    )
    st.plotly_chart(fig2, use_container_width=True, key='history_chart')
else:
    st.info("Collecting order history — check back in a few seconds")

st.divider()

# ── Surge alerts ─────────────────────────────────────────────────────────────
st.subheader("🚨 Surge alerts")

surge_zones = []
for zone_id, pred in predictions.items():
    base      = ZONES[zone_id]['base_demand']
    predicted = pred['predicted']
    pct       = ((predicted - base) / base) * 100

    if pct > 30:
        surge_zones.append({
            'zone':    pred['zone_name'],
            'orders':  predicted,
            'pct':     pct,
            'level':   '🔴 HIGH SURGE' if pct > 60 else '🟡 MODERATE SURGE'
        })

if surge_zones:
    for surge in surge_zones:
        st.error(f"{surge['level']} — {surge['zone']}: {surge['orders']} orders predicted ({surge['pct']:+.0f}% above baseline)")
else:
    st.success("✅ No surge alerts — all zones operating within normal range")

st.divider()

# ── Delhi map ────────────────────────────────────────────────────────────────
st.subheader("🗺️ Delhi zone map")

zone_coords = {
    'zone_1': (28.6315, 77.2167, 'Connaught Place'),
    'zone_2': (28.5494, 77.2001, 'South Delhi'),
    'zone_3': (28.7041, 77.1025, 'North Delhi'),
    'zone_4': (28.6276, 77.2772, 'East Delhi'),
    'zone_5': (28.6475, 77.1220, 'West Delhi'),
    'zone_6': (28.5355, 77.3910, 'Noida')
}

map_df = pd.DataFrame([
    {
        'lat':       coords[0],
        'lon':       coords[1],
        'zone':      coords[2],
        'predicted': predictions[zone_id]['predicted'],
        'size':      predictions[zone_id]['predicted'] / 5
    }
    for zone_id, coords in zone_coords.items()
])

fig3 = px.scatter_mapbox(
    map_df,
    lat='lat', lon='lon',
    size='size',
    color='predicted',
    hover_name='zone',
    hover_data={'predicted': True, 'lat': False, 'lon': False, 'size': False},
    color_continuous_scale='RdYlGn_r',
    zoom=10,
    height=450,
    mapbox_style='open-street-map',
    title='Live demand heatmap — Delhi zones'
)
fig3.update_layout(margin=dict(l=0, r=0, t=40, b=0))
st.plotly_chart(fig3, use_container_width=True, key='map_chart')

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Data: OpenWeatherMap API · Simulated order stream via Apache Kafka · "
    "Predictions: XGBoost model (R² 0.857, MAE ±25 orders) · "
    "Feature store: Redis · Built with Streamlit"
)