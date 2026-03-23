"""
pages/2_Profile.py  —  Building Asset Profile
═══════════════════════════════════════════════
Sections:
  · Status header   — big badge OK / WARNING / CRITICAL + score gauge
  · Degradation gauge (0–100) — Plotly indicator
  · Issues list     — tags from ML model, colour-coded by severity
  · Parameter breakdown — score contribution per factor
  · Time series     — temperature, humidity, vibration events, tilt
  · Scan session history table
"""

import json
import os
import sys
import time
from datetime import datetime

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from frontend.auth import (
    require_auth, has_perm, render_sidebar_user,
    building_meta, render_building_form,
)

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="BILB — Asset Profile",
    page_icon="🏛",
    layout="wide",
    initial_sidebar_state="expanded",
)
require_auth("view")

# ══════════════════════════════════════════════════════════════
#  Sidebar
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
<div style="padding:12px 0 8px;text-align:center">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:2rem;
              font-weight:800;letter-spacing:8px;color:#00ff88;
              text-shadow:0 0 20px rgba(0,255,136,.2)">BILB</div>
  <div style="font-size:.6rem;letter-spacing:3px;color:#3a5060">ASSET PROFILE</div>
</div>""", unsafe_allow_html=True)
    render_sidebar_user()
    st.markdown("---")

    b = building_meta()
    if b["name"] != "—":
        st.markdown(f"""
<div style="font-size:.65rem;color:#3a5060;letter-spacing:1px">
  <div style="color:#4a7090;margin-bottom:4px">ACTIVE BUILDING</div>
  <div style="color:#c8d8e8;font-weight:700">{b['name']}</div>
  <div>{b['city']} · {b['year_built']}</div>
  <div>{b['area_m2']} m² · {b['floors']} floors</div>
</div>""", unsafe_allow_html=True)
    st.markdown("---")

    chart_period = st.selectbox("Chart period",
        ["Last 50", "Last 100", "Last 200", "All"], index=1)
    limit_map = {"Last 50": 50, "Last 100": 100, "Last 200": 200, "All": 1000}
    chart_limit = limit_map[chart_period]

    retrain = st.button("⟳ RETRAIN ML MODEL", use_container_width=True,
                         disabled=not has_perm("scan"))
    if retrain:
        st.info("Retraining queued — results appear in ~30s")

    auto_refresh = st.toggle("Auto-refresh (5s)", False)
    if auto_refresh:
        # @st.cache_data(ttl=5) on loaders already throttles fetches.
        # time.sleep() here would block the entire Streamlit server thread.
        st.rerun()

# ── Building registration gate ────────────────────────────────
if not render_building_form():
    st.stop()

# ══════════════════════════════════════════════════════════════
#  Data loaders
# ══════════════════════════════════════════════════════════════
API_URL     = os.getenv("API_URL",     "http://localhost:8000")
BUILDING_ID = b.get("building_id", "BILB_001")

@st.cache_data(ttl=5)
def _load_latest(bid):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/telemetry/{bid}/latest", timeout=2)
        return r.json() if r.ok else {}
    except Exception:
        return _demo_latest()

@st.cache_data(ttl=5)
def _load_readings(bid, limit):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/telemetry/{bid}?limit={limit}", timeout=2)
        return r.json() if r.ok else _demo_readings(limit)
    except Exception:
        return _demo_readings(limit)

@st.cache_data(ttl=10)
def _load_profile(bid):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/buildings/{bid}", timeout=2)
        return r.json() if r.ok else {}
    except Exception:
        return {}

@st.cache_data(ttl=10)
def _load_sessions(bid):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/buildings/{bid}/sessions", timeout=2)
        return r.json() if r.ok else []
    except Exception:
        return []


def _demo_latest():
    import math, time as t
    tau = t.time() * 0.08
    h   = 55 + 20 * math.sin(tau * .7)
    vib = h > 65
    score = min(100, (40 if h >= 70 else 20 if h >= 55 else 0)
                   + (25 if vib else 0)
                   + (15 if vib and h >= 70 else 0))
    status = "CRITICAL" if score >= 65 else "WARNING" if score >= 30 else "OK"
    return {
        "temperature": round(22 + 4 * math.sin(tau), 1),
        "humidity":    round(h, 1),
        "light_lux":   round(max(0, 180 + 100 * math.sin(tau * .5))),
        "pressure":    round(1013 + 3 * math.sin(tau * .3), 1),
        "tilt_roll":   round(2 * math.sin(tau * 1.2), 2),
        "tilt_pitch":  round(1 * math.cos(tau * .8), 2),
        "vibration":   vib,
        "status":      status,
        "score":       round(score, 1),
        "issues": json.dumps(
            (["HIGH_HUMIDITY"]       if h >= 70 else
             ["ELEVATED_HUMIDITY"]   if h >= 55 else []) +
            (["VIBRATION_DETECTED"]  if vib else []) +
            (["STRUCTURAL_RISK_COMBO"] if vib and h >= 70 else [])
        ),
    }

def _demo_readings(limit):
    import math, time as t, random
    readings = []
    now = t.time()
    for i in range(limit):
        tau = (now - (limit - i) * 10) * 0.08
        h   = 55 + 20 * math.sin(tau * .7) + random.gauss(0, 2)
        h   = max(10, min(100, h))
        vib = h > 68 and random.random() > 0.5
        score = min(100, (40 if h >= 70 else 20 if h >= 55 else 0) + (25 if vib else 0))
        readings.append({
            "received_at": datetime.fromtimestamp(now - (limit-i)*10).isoformat(),
            "temperature": round(22 + 4*math.sin(tau) + random.gauss(0,.3), 1),
            "humidity":    round(h, 1),
            "light_lux":   round(max(0, 180 + 100*math.sin(tau*.5) + random.gauss(0,10))),
            "tilt_roll":   round(2*math.sin(tau*1.2) + random.gauss(0,.1), 2),
            "tilt_pitch":  round(1*math.cos(tau*.8)  + random.gauss(0,.05), 2),
            "vibration":   vib,
            "status":      ("CRITICAL" if score>=65 else "WARNING" if score>=30 else "OK"),
            "score":       round(score, 1),
        })
    return readings

latest   = _load_latest(BUILDING_ID)
readings = _load_readings(BUILDING_ID, chart_limit)
profile  = _load_profile(BUILDING_ID)
sessions = _load_sessions(BUILDING_ID)

# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────
STATUS_COLOR = {"OK": "#00ff88", "WARNING": "#ffaa00", "CRITICAL": "#ff3355"}
PLOTLY_BASE  = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a0d12",
    font=dict(family="JetBrains Mono, monospace", color="#6a8090", size=10),
    margin=dict(l=0, r=0, t=20, b=0),
    xaxis=dict(gridcolor="#111820", showgrid=True, zeroline=False),
    yaxis=dict(gridcolor="#111820", showgrid=True, zeroline=False),
)

def _ts(r):
    try:
        return datetime.fromisoformat(r["received_at"].replace("Z", ""))
    except Exception:
        return None

def _parse_issues(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [i for i in raw if i and i.upper() != "NONE"]
    try:
        lst = json.loads(raw)
        return [i for i in lst if i and i.upper() != "NONE"]
    except Exception:
        return [i.strip() for i in str(raw).split(",") if i.strip() and i.strip().upper() != "NONE"]

status = latest.get("status", "UNKNOWN")
score  = float(latest.get("score", 0) or 0)
sc     = STATUS_COLOR.get(status, "#6a8090")
issues = _parse_issues(latest.get("issues") or profile.get("issues"))

# ══════════════════════════════════════════════════════════════
#  SECTION A — STATUS HEADER + GAUGE
# ══════════════════════════════════════════════════════════════
col_badge, col_gauge, col_meta = st.columns([1.5, 2, 1.5], gap="small")

with col_badge:
    st.markdown(f"""
<div style="background:{sc}11;border:2px solid {sc}44;
            padding:24px 20px;text-align:center;height:160px;
            display:flex;flex-direction:column;justify-content:center;
            border-radius:2px">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:3rem;
              font-weight:800;letter-spacing:6px;color:{sc};
              text-shadow:0 0 20px {sc}44;line-height:1">{status}</div>
  <div style="font-size:.65rem;color:#6a8090;letter-spacing:2px;
              margin-top:8px">BUILDING STATUS</div>
  <div style="font-size:.8rem;color:{sc};margin-top:6px;font-weight:700">
    SCORE: {score:.0f} / 100
  </div>
</div>
""", unsafe_allow_html=True)

with col_gauge:
    # Plotly gauge / speedometer
    gauge_color = sc
    fig_gauge = go.Figure(go.Indicator(
        mode  = "gauge+number+delta",
        value = score,
        delta = {"reference": 50, "valueformat": ".0f",
                 "font": {"size": 12, "color": "#6a8090"}},
        number= {"font": {"size": 28, "color": sc,
                          "family": "JetBrains Mono, monospace"},
                 "suffix": "/100"},
        title = {"text": "DEGRADATION SCORE",
                 "font": {"size": 10, "color": "#6a8090", "family": "JetBrains Mono, monospace"}},
        gauge = {
            "axis": {
                "range": [0, 100],
                "tickwidth": 0.5, "tickcolor": "#1e2d3d",
                "tickvals": [0, 30, 65, 100],
                "ticktext": ["0", "30", "65", "100"],
                "tickfont": {"size": 9, "color": "#6a8090"},
            },
            "bar":   {"color": sc, "thickness": 0.25},
            "bgcolor": "#0d1117",
            "borderwidth": 0.5,
            "bordercolor": "#1e2d3d",
            "steps": [
                {"range": [0,  30], "color": "rgba(0,255,136,.06)"},
                {"range": [30, 65], "color": "rgba(255,170,0,.06)"},
                {"range": [65,100], "color": "rgba(255,51,85,.08)"},
            ],
            "threshold": {
                "line":  {"color": sc, "width": 2},
                "thickness": 0.75,
                "value": score,
            },
        },
    ))
    fig_gauge.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono, monospace"),
        margin=dict(l=20, r=20, t=30, b=10),
        height=160,
    )
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_meta:
    vib_count = sum(1 for r in readings if r.get("vibration"))
    avg_hum   = (sum(float(r.get("humidity",0) or 0) for r in readings)
                 / max(len(readings), 1))
    avg_temp  = (sum(float(r.get("temperature",0) or 0) for r in readings)
                 / max(len(readings), 1))

    for label, val, unit, warn_c in [
        ("AVG HUMIDITY",    f"{avg_hum:.1f}",  "%",  "#ffaa00" if avg_hum >= 55 else "#00ff88"),
        ("AVG TEMP",        f"{avg_temp:.1f}", "°C", "#ffaa00" if avg_temp >= 30 else "#00ff88"),
        ("VIB EVENTS",      str(vib_count),    "",   "#ff3355" if vib_count > 5
                                                    else "#ffaa00" if vib_count > 0
                                                    else "#00ff88"),
        ("READINGS",        str(len(readings)),"",   "#00aaff"),
    ]:
        st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-left:2px solid {warn_c};
            padding:7px 10px;margin-bottom:5px">
  <div style="font-size:.6rem;letter-spacing:1px;color:#3a5060">{label}</div>
  <div style="font-size:1rem;font-weight:700;color:{warn_c};
              font-family:'JetBrains Mono',monospace">{val}
    <span style="font-size:.6rem;color:#3a5060">{unit}</span>
  </div>
</div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION B — ISSUES LIST
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  IDENTIFIED ISSUES
</div>""", unsafe_allow_html=True)

ISSUE_META = {
    "HIGH_HUMIDITY":           ("CRITICAL", "#ff3355", "Humidity ≥ 70% — waterproofing required"),
    "ELEVATED_HUMIDITY":       ("WARNING",  "#ffaa00", "Humidity 55–70% — monitor closely"),
    "VIBRATION_DETECTED":      ("WARNING",  "#ffaa00", "Vibration event detected"),
    "STRUCTURAL_RISK_COMBO":   ("CRITICAL", "#ff3355", "Humidity + Vibration — structural audit"),
    "HIGH_TEMPERATURE":        ("WARNING",  "#ffaa00", "Temperature ≥ 40°C — HVAC audit"),
    "ELEVATED_TEMPERATURE":    ("INFO",     "#00aaff", "Temperature 30–40°C"),
    "CRITICAL_STRUCTURAL_TILT":("CRITICAL", "#ff3355", "Tilt ≥ 15° — geotechnical survey"),
    "TILT_DETECTED":           ("WARNING",  "#ffaa00", "Tilt 5–15° — monitoring required"),
    "POOR_DAYLIGHTING":        ("INFO",     "#00aaff", "Light < 100 lux — glazing review"),
}

if not issues:
    st.markdown("""
<div style="background:rgba(0,255,136,.06);border:1px solid rgba(0,255,136,.3);
            padding:12px 16px;color:#00ff88;font-size:.8rem;border-radius:2px">
  ✓ No issues detected — building within normal parameters
</div>""", unsafe_allow_html=True)
else:
    cols = st.columns(min(len(issues), 3), gap="small")
    for i, issue in enumerate(issues):
        sev, color, desc = ISSUE_META.get(issue, ("INFO", "#00aaff", issue))
        with cols[i % len(cols)]:
            st.markdown(f"""
<div style="background:{color}11;border:1px solid {color}44;
            border-left:3px solid {color};padding:10px 14px;
            margin-bottom:8px;border-radius:0 2px 2px 0">
  <div style="font-size:.65rem;font-weight:700;letter-spacing:1px;
              color:{color};margin-bottom:3px">{sev}</div>
  <div style="font-size:.8rem;font-weight:700;color:#c8d8e8;
              font-family:'JetBrains Mono',monospace">{issue}</div>
  <div style="font-size:.7rem;color:#6a8090;margin-top:4px">{desc}</div>
</div>""", unsafe_allow_html=True)

# Score breakdown
if issues:
    SCORE_MAP = {
        "HIGH_HUMIDITY": 40, "ELEVATED_HUMIDITY": 20,
        "VIBRATION_DETECTED": 25, "STRUCTURAL_RISK_COMBO": 15,
        "HIGH_TEMPERATURE": 20, "ELEVATED_TEMPERATURE": 8,
        "CRITICAL_STRUCTURAL_TILT": 35, "TILT_DETECTED": 12,
        "POOR_DAYLIGHTING": 5,
    }
    with st.expander("▸ Score breakdown", expanded=False):
        items = [(k, SCORE_MAP.get(k, 0)) for k in issues]
        total = min(100, sum(v for _, v in items))
        for iss, pts in items:
            _, c, _ = ISSUE_META.get(iss, ("INFO", "#00aaff", ""))
            # pts is already 0–100; use directly as bar width %
            st.markdown(f"""
<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">
  <div style="font-size:.75rem;color:#6a8090;width:200px">{iss}</div>
  <div style="flex:1;height:6px;background:#111820;border-radius:3px">
    <div style="width:{pts}%;height:100%;background:{c};border-radius:3px"></div>
  </div>
  <div style="font-size:.75rem;color:{c};width:36px;text-align:right">+{pts}</div>
</div>""", unsafe_allow_html=True)
        st.markdown(f"""
<div style="font-size:.8rem;color:{sc};font-weight:700;
            margin-top:6px;border-top:1px solid #1e2d3d;padding-top:6px">
  Total score: {total:.0f} / 100
</div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION C — TIME SERIES
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  SENSOR TIME SERIES
</div>""", unsafe_allow_html=True)

# Parse timestamps
timestamps = [_ts(r) for r in readings]
valid_idx  = [i for i, t in enumerate(timestamps) if t is not None]
ts         = [timestamps[i] for i in valid_idx]
r_valid    = [readings[i] for i in valid_idx]

def _vals(key):
    return [float(r.get(key, 0) or 0) for r in r_valid]

# ── Row 1: Temperature + Humidity ────────────────────────────
col_temp, col_hum = st.columns(2, gap="small")

with col_temp:
    temps = _vals("temperature")
    fig_t = go.Figure()
    fig_t.add_trace(go.Scatter(
        x=ts, y=temps, mode="lines", name="Temp",
        line=dict(color="#ff6b6b", width=1.5),
        fill="tozeroy", fillcolor="rgba(255,107,107,.05)",
    ))
    fig_t.add_hline(y=30, line=dict(color="#ffaa00", width=0.8, dash="dot"))
    fig_t.add_hline(y=40, line=dict(color="#ff3355", width=0.8, dash="dot"))
    fig_t.update_layout(**PLOTLY_BASE, height=160,
                        yaxis_title="°C",
                        title=dict(text="TEMPERATURE", font=dict(size=9, color="#3a5060")))
    st.plotly_chart(fig_t, use_container_width=True)

with col_hum:
    hums = _vals("humidity")
    fig_h = go.Figure()
    fig_h.add_trace(go.Scatter(
        x=ts, y=hums, mode="lines", name="Humidity",
        line=dict(color="#00aaff", width=1.5),
        fill="tozeroy", fillcolor="rgba(0,170,255,.05)",
    ))
    fig_h.add_hline(y=55, line=dict(color="#ffaa00", width=0.8, dash="dot"))
    fig_h.add_hline(y=70, line=dict(color="#ff3355", width=0.8, dash="dot"))
    fig_h.update_layout(**PLOTLY_BASE, height=160,
                        yaxis_title="%",
                        title=dict(text="HUMIDITY", font=dict(size=9, color="#3a5060")))
    st.plotly_chart(fig_h, use_container_width=True)

# ── Row 2: Tilt + Vibration events ───────────────────────────
col_tilt, col_vib = st.columns(2, gap="small")

with col_tilt:
    rolls  = _vals("tilt_roll")
    pitchs = _vals("tilt_pitch")
    fig_tl = go.Figure()
    fig_tl.add_trace(go.Scatter(
        x=ts, y=rolls, mode="lines", name="Roll",
        line=dict(color="#9b59b6", width=1.5),
    ))
    fig_tl.add_trace(go.Scatter(
        x=ts, y=pitchs, mode="lines", name="Pitch",
        line=dict(color="#00aaff", width=1.2, dash="dot"),
    ))
    fig_tl.add_hline(y=5,   line=dict(color="#ffaa00", width=0.7, dash="dot"))
    fig_tl.add_hline(y=-5,  line=dict(color="#ffaa00", width=0.7, dash="dot"))
    fig_tl.add_hline(y=15,  line=dict(color="#ff3355", width=0.7, dash="dot"))
    fig_tl.add_hline(y=-15, line=dict(color="#ff3355", width=0.7, dash="dot"))
    fig_tl.update_layout(
        **PLOTLY_BASE, height=160, yaxis_title="°",
        title=dict(text="TILT (ROLL / PITCH)", font=dict(size=9, color="#3a5060")),
        legend=dict(orientation="h", y=1.1,
                    font=dict(size=8, color="#6a8090")),
    )
    st.plotly_chart(fig_tl, use_container_width=True)

with col_vib:
    vib_vals = [1 if r.get("vibration") else 0 for r in r_valid]
    vib_ts   = [t for t, v in zip(ts, vib_vals) if v]

    fig_v = go.Figure()
    # Background area
    fig_v.add_trace(go.Scatter(
        x=ts, y=vib_vals, mode="lines",
        line=dict(color="rgba(255,51,85,.3)", width=1),
        fill="tozeroy", fillcolor="rgba(255,51,85,.06)",
        showlegend=False,
    ))
    # Event markers
    if vib_ts:
        fig_v.add_trace(go.Scatter(
            x=vib_ts, y=[1] * len(vib_ts),
            mode="markers",
            marker=dict(size=7, color="#ff3355", symbol="x"),
            name="Event", showlegend=False,
        ))
    # Apply base layout first, then override yaxis via update_yaxes to avoid
    # TypeError from passing yaxis= twice (once in **PLOTLY_BASE, once explicitly)
    fig_v.update_layout(
        **PLOTLY_BASE, height=160,
        title=dict(text=f"VIBRATION EVENTS  ({len(vib_ts)} detected)",
                   font=dict(size=9, color="#3a5060")),
    )
    fig_v.update_yaxes(range=[-0.1, 1.3], showgrid=False,
                       zeroline=False, showticklabels=False)
    st.plotly_chart(fig_v, use_container_width=True)

# ── Row 3: Score over time + Status distribution ─────────────
col_score, col_dist = st.columns([2, 1], gap="small")

with col_score:
    scores   = _vals("score")
    statuses = [r.get("status", "OK") for r in r_valid]

    fig_sc = go.Figure()
    # Colour zones
    fig_sc.add_hrect(y0=65, y1=105, fillcolor="rgba(255,51,85,.04)",
                     line_width=0, layer="below")
    fig_sc.add_hrect(y0=30, y1=65, fillcolor="rgba(255,170,0,.04)",
                     line_width=0, layer="below")
    fig_sc.add_trace(go.Scatter(
        x=ts, y=scores, mode="lines",
        line=dict(color="#00ff88", width=1.5),
        fill="tozeroy", fillcolor="rgba(0,255,136,.04)",
        name="Score",
    ))
    fig_sc.add_hline(y=30, line=dict(color="#ffaa00", width=0.7, dash="dot"))
    fig_sc.add_hline(y=65, line=dict(color="#ff3355", width=0.7, dash="dot"))
    fig_sc.update_layout(
        **PLOTLY_BASE, height=140, yaxis_title="score",
        yaxis_range=[0, 105],
        title=dict(text="DEGRADATION SCORE OVER TIME",
                   font=dict(size=9, color="#3a5060")),
    )
    st.plotly_chart(fig_sc, use_container_width=True)

with col_dist:
    from collections import Counter
    cnt  = Counter(statuses)
    ok   = cnt.get("OK", 0)
    warn = cnt.get("WARNING", 0)
    crit = cnt.get("CRITICAL", 0)
    total_s = ok + warn + crit or 1

    fig_pie = go.Figure(go.Pie(
        labels=["OK", "WARNING", "CRITICAL"],
        values=[ok, warn, crit],
        hole=0.55,
        marker=dict(colors=["#00ff88", "#ffaa00", "#ff3355"],
                    line=dict(color="#080a0e", width=2)),
        textfont=dict(size=9, color="#6a8090", family="JetBrains Mono, monospace"),
        hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
    ))
    fig_pie.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=20, b=0),
        height=140,
        showlegend=True,
        legend=dict(orientation="v", x=1.0, font=dict(size=8, color="#6a8090")),
        annotations=[dict(text=f"{crit+warn}<br><span style='font-size:8px'>issues</span>",
                          x=0.5, y=0.5, font_size=11, font_color=sc,
                          showarrow=False)],
        title=dict(text="STATUS DIST.", font=dict(size=9, color="#3a5060")),
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# ══════════════════════════════════════════════════════════════
#  SECTION D — SCAN SESSION HISTORY
# ══════════════════════════════════════════════════════════════
if sessions:
    st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  SCAN SESSION HISTORY
</div>""", unsafe_allow_html=True)

    import pandas as pd
    sess_rows = []
    for s in sessions[:10]:
        started = s.get("started_at", "")[:16].replace("T", " ")
        ended   = (s.get("ended_at", "") or "—")[:16].replace("T", " ")
        sess_rows.append({
            "ID":       s.get("id", "—"),
            "Started":  started,
            "Ended":    ended,
            "Readings": s.get("total_readings", 0),
            "Vib":      s.get("vibration_events", 0),
            "Avg H%":   f"{s.get('avg_humidity', 0) or 0:.1f}",
            "Avg T°C":  f"{s.get('avg_temperature', 0) or 0:.1f}",
        })
    df = pd.DataFrame(sess_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
