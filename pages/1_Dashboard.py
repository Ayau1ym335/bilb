"""
pages/1_Dashboard.py  —  Live Mission Control
═══════════════════════════════════════════════
Layout (3 panels):
  LEFT   — Telemetry panel: live sensor values, bar indicators, alerts
  CENTER — Grid map 20×20: robot position, trail, heatmap overlay, waypoints
  RIGHT  — Proximity radar (polar HC-SR04) + WebSocket D-pad controls

WebSocket: connects to ESP32 at ws://192.168.4.1:81
           receives {"type":"telem", ...} every 200ms
           sends   {"cmd":"FORWARD"} etc.

All JS runs in an iframe via st.components.v1.html().
Python side polls the FastAPI bridge for DB readings.
"""

import json
import math
import os
import time

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components


# ─── Helper (must be defined before any f-string that calls it) ───────────────
def _hdg_name(deg: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]
    return dirs[round(deg / 45) % 8]


# ── Auth guard ────────────────────────────────────────────────
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from frontend.auth import require_auth, render_sidebar_user, building_meta, render_building_form

st.set_page_config(
    page_title="BILB — Mission Control",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)
require_auth("view")

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<div style="padding:12px 0 8px;text-align:center">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:2rem;
              font-weight:800;letter-spacing:8px;color:#00ff88;
              text-shadow:0 0 20px rgba(0,255,136,.2)">BILB</div>
  <div style="font-size:.6rem;letter-spacing:3px;color:#3a5060">MISSION CONTROL</div>
</div>
""", unsafe_allow_html=True)
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

    ws_url = st.text_input("ESP32 WebSocket", value="ws://192.168.4.1:81",
                            help="Connect to robot's AP: BILB_Robot / bilb2026")
    auto_refresh = st.toggle("Auto-refresh DB (3s)", False)
    show_heatmap = st.toggle("Heatmap overlay", True)
    show_trail   = st.toggle("Robot trail", True)

    if auto_refresh:
        # @st.cache_data(ttl=3) on the loaders already throttles to 3s.
        # time.sleep() here would block the entire Streamlit server thread.
        st.rerun()

# ── Building registration gate ────────────────────────────────
if not render_building_form():
    st.stop()

# ── Load latest telemetry from FastAPI/DB ────────────────────
API_URL = os.getenv("API_URL", "http://localhost:8000")
BUILDING_ID = b.get("building_id", "BILB_001")

@st.cache_data(ttl=3)
def load_latest(bid: str):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/telemetry/{bid}/latest", timeout=2)
        return r.json() if r.ok else {}
    except Exception:
        return _demo_reading()

@st.cache_data(ttl=3)
def load_readings(bid: str, limit: int = 200):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/telemetry/{bid}?limit={limit}", timeout=2)
        return r.json() if r.ok else [_demo_reading() for _ in range(60)]
    except Exception:
        return [_demo_reading() for _ in range(60)]

@st.cache_data(ttl=10)
def load_heatmap(bid: str):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/heatmap/{bid}?cell_size=1.0", timeout=2)
        return r.json().get("cells", {}) if r.ok else {}
    except Exception:
        return {}

def _demo_reading():
    import math, random, time as t
    tau = t.time() * 0.1
    return {
        "temperature": round(22 + 4 * math.sin(tau), 1),
        "humidity":    round(55 + 20 * math.sin(tau * .7), 1),
        "pressure":    round(1013 + 5 * math.sin(tau * .3), 1),
        "light_lux":   round(max(0, 200 + 150 * math.sin(tau * .5))),
        "tilt_roll":   round(2 * math.sin(tau * 1.2), 2),
        "tilt_pitch":  round(1 * math.cos(tau * .8), 2),
        "vibration":   random.random() > 0.92,
        "status":      "WARNING",
        "score":       round(30 + 20 * abs(math.sin(tau * .4)), 1),
        "dist_front":  round(50 + 80 * abs(math.sin(tau)), 1),
        "dist_back":   round(120 + 60 * math.cos(tau), 1),
        "dist_left":   round(40 + 50 * abs(math.sin(tau * 1.3)), 1),
        "dist_right":  round(80 + 40 * math.cos(tau * .8), 1),
        "pos_x":       round(8 + 3 * math.sin(tau * .3), 2),
        "pos_y":       round(8 + 3 * math.cos(tau * .3), 2),
        "pos_heading": int(tau * 30 % 360),
    }

latest   = load_latest(BUILDING_ID)
readings = load_readings(BUILDING_ID)
heatmap  = load_heatmap(BUILDING_ID) if show_heatmap else {}

# ── Status header ─────────────────────────────────────────────
status = latest.get("status", "UNKNOWN")
score  = latest.get("score", 0) or 0
sc = {"OK": "#00ff88", "WARNING": "#ffaa00", "CRITICAL": "#ff3355"}.get(status, "#6a8090")

st.markdown(f"""
<div style="background:{sc}11;border:1px solid {sc}44;
            padding:10px 20px;margin-bottom:16px;
            display:flex;align-items:center;gap:16px;border-radius:2px">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.8rem;
              font-weight:800;letter-spacing:4px;color:{sc}">{status}</div>
  <div style="color:#6a8090;font-size:.7rem;letter-spacing:2px">
    SCORE: {score:.0f}/100 · {b['name']} · {b['city']}
  </div>
  <div style="margin-left:auto;font-size:.65rem;color:#3a5060">
    {time.strftime('%H:%M:%S')} UTC
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
#  MAIN 3-PANEL LAYOUT
# ═══════════════════════════════════════════════════════════════
col_left, col_center, col_right = st.columns([1, 2.2, 1], gap="small")

# ────────────────────────────────────────────────────────────
#  LEFT: Telemetry panel
# ────────────────────────────────────────────────────────────
with col_left:
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.7rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:8px">TELEMETRY</div>
""", unsafe_allow_html=True)

    def _telem_row(label: str, val, unit: str,
                   val_float: float, lo: float, hi: float,
                   warn: float = None, crit: float = None):
        pct  = min(100, max(0, (val_float - lo) / max(hi - lo, 1) * 100))
        color = "#00ff88"
        if crit and val_float >= crit:
            color = "#ff3355"
        elif warn and val_float >= warn:
            color = "#ffaa00"

        st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-left:3px solid {color};
            padding:8px 10px;margin-bottom:6px;position:relative;overflow:hidden">
  <div style="display:flex;align-items:center;justify-content:space-between">
    <div style="font-size:.65rem;letter-spacing:1px;color:#6a8090">{label}</div>
    <div style="font-size:.95rem;font-weight:700;color:{color};
                font-family:'JetBrains Mono',monospace">{val}<span style="font-size:.65rem;color:#3a5060;margin-left:3px">{unit}</span></div>
  </div>
  <div style="position:absolute;bottom:0;left:0;right:0;height:2px;background:#111820">
    <div style="width:{pct}%;height:100%;background:{color};transition:width .5s"></div>
  </div>
</div>
""", unsafe_allow_html=True)

    _telem_row("TEMP",     f"{latest.get('temperature', 0):.1f}", "°C",
               float(latest.get("temperature", 0)), 0, 50, warn=30, crit=40)
    _telem_row("HUMIDITY", f"{latest.get('humidity', 0):.1f}", "%",
               float(latest.get("humidity", 0)), 0, 100, warn=55, crit=70)
    _telem_row("LIGHT",    f"{latest.get('light_lux', 0):.0f}", "lx",
               float(latest.get("light_lux", 0)), 0, 1000)
    _telem_row("PRESSURE", f"{latest.get('pressure', 1013):.0f}", "hPa",
               float(latest.get("pressure", 1013)), 980, 1040)

    roll  = abs(float(latest.get("tilt_roll",  0) or 0))
    pitch = abs(float(latest.get("tilt_pitch", 0) or 0))
    _telem_row("TILT ROLL",  f"{latest.get('tilt_roll', 0):.2f}", "°",
               roll, 0, 20, warn=5, crit=15)
    _telem_row("TILT PITCH", f"{latest.get('tilt_pitch', 0):.2f}", "°",
               pitch, 0, 20, warn=5, crit=15)
    _telem_row("DEG SCORE",  f"{score:.1f}", "/100",
               score, 0, 100, warn=30, crit=65)

    # Vibration alert
    vib = latest.get("vibration", False)
    if vib:
        st.markdown("""
<div style="background:rgba(255,51,85,.1);border:1px solid #ff3355;
            padding:8px 12px;color:#ff3355;font-size:.75rem;
            letter-spacing:1px;text-align:center;margin-bottom:6px;
            animation:blink 1s step-end infinite">
  ⚠ VIBRATION DETECTED
</div>
<style>@keyframes blink{50%{opacity:0}}</style>
""", unsafe_allow_html=True)
    else:
        st.markdown("""
<div style="background:#080a0e;border:1px solid #1e2d3d;
            padding:8px 12px;color:#3a5060;font-size:.75rem;
            letter-spacing:1px;text-align:center;margin-bottom:6px">
  VIBRATION: NONE
</div>""", unsafe_allow_html=True)

    # Position info
    px = latest.get("pos_x", 0) or 0
    py = latest.get("pos_y", 0) or 0
    ph = latest.get("pos_heading", 0) or 0
    st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;padding:8px 10px;
            font-size:.75rem;color:#6a8090;letter-spacing:1px">
  <div>POS  X:{px:.1f}  Y:{py:.1f}</div>
  <div>HDG  {ph}°  ({_hdg_name(ph)})</div>
</div>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────
#  CENTER: Grid map + heatmap overlay
# ────────────────────────────────────────────────────────────
with col_center:
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.7rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:8px">FLOOR PLAN / ROUTE MAP</div>
""", unsafe_allow_html=True)

    GRID = 20

    # Build heatmap traces
    hm_x, hm_y, hm_z, hm_txt = [], [], [], []
    if heatmap:
        for cell in heatmap.values():
            hm_x.append(float(cell.get("x", 0)))
            hm_y.append(float(cell.get("y", 0)))
            sc_val = float(cell.get("avg_score", 0))
            hm_z.append(sc_val)
            hm_txt.append(
                f"x={cell['x']:.1f} y={cell['y']:.1f}<br>"
                f"score={sc_val:.1f} n={cell.get('count', 0)}<br>"
                f"status={cell.get('max_status', '?')}"
            )

    # Build trail from recent readings
    trail_x, trail_y = [], []
    if show_trail and readings:
        for r in reversed(readings[-80:]):
            if r.get("pos_x") is not None and r.get("pos_y") is not None:
                trail_x.append(float(r["pos_x"]))
                trail_y.append(float(r["pos_y"]))

    fig = go.Figure()

    # Grid lines (subtle)
    for i in range(GRID + 1):
        fig.add_shape(type="line", x0=0, x1=GRID, y0=i, y1=i,
                      line=dict(color="#111820", width=0.5))
        fig.add_shape(type="line", x0=i, x1=i, y0=0, y1=GRID,
                      line=dict(color="#111820", width=0.5))
    # Major grid every 5
    for i in range(0, GRID + 1, 5):
        fig.add_shape(type="line", x0=0, x1=GRID, y0=i, y1=i,
                      line=dict(color="#1e2d3d", width=1))
        fig.add_shape(type="line", x0=i, x1=i, y0=0, y1=GRID,
                      line=dict(color="#1e2d3d", width=1))

    # Heatmap overlay
    if hm_x:
        fig.add_trace(go.Scatter(
            x=hm_x, y=hm_y, mode="markers",
            marker=dict(
                size=22,
                color=hm_z,
                colorscale=[[0, "rgba(0,255,136,.15)"],
                             [0.3, "rgba(255,170,0,.25)"],
                             [1, "rgba(255,51,85,.45)"]],
                cmin=0, cmax=100,
                showscale=True,
                colorbar=dict(
                    title="Score", thickness=10, len=0.5,
                    tickfont=dict(color="#6a8090", size=9),
                    titlefont=dict(color="#6a8090", size=9),
                    bgcolor="rgba(0,0,0,0)", outlinewidth=0,
                ),
                symbol="square",
            ),
            text=hm_txt, hoverinfo="text", name="Heatmap", showlegend=False,
        ))

    # Robot trail
    if trail_x:
        fig.add_trace(go.Scatter(
            x=trail_x, y=trail_y, mode="lines",
            line=dict(color="rgba(0,255,136,.4)", width=2, dash="dot"),
            name="Trail", hoverinfo="skip", showlegend=False,
        ))

    # Robot marker + heading arrow
    rx, ry, rh = float(px), float(py), float(ph)
    import math
    rad = math.radians(rh - 90)
    arrow_dx = math.cos(rad) * 1.2
    arrow_dy = -math.sin(rad) * 1.2

    # Robot circle
    fig.add_trace(go.Scatter(
        x=[rx], y=[ry],
        mode="markers+text",
        marker=dict(size=18, color="#00ff88", symbol="circle",
                    line=dict(color="#00ff88", width=2),
                    opacity=0.9),
        text=["BILB"], textposition="top center",
        textfont=dict(color="#00ff88", size=9),
        name="Robot", hoverinfo="skip", showlegend=False,
    ))
    # Heading arrow
    fig.add_annotation(
        x=rx + arrow_dx, y=ry + arrow_dy,
        ax=rx, ay=ry,
        xref="x", yref="y", axref="x", ayref="y",
        arrowhead=2, arrowsize=1.2, arrowwidth=2,
        arrowcolor="#00ff88", showarrow=True,
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#080a0e",
        xaxis=dict(range=[-0.5, GRID + 0.5], showgrid=False, zeroline=False,
                   tickvals=list(range(0, GRID + 1, 5)),
                   tickfont=dict(color="#3a5060", size=9), title=""),
        yaxis=dict(range=[-0.5, GRID + 0.5], showgrid=False, zeroline=False,
                   tickvals=list(range(0, GRID + 1, 5)),
                   tickfont=dict(color="#3a5060", size=9), title="",
                   scaleanchor="x", scaleratio=1),
        margin=dict(l=30, r=10, t=10, b=30),
        height=450,
        font=dict(family="JetBrains Mono, monospace", color="#6a8090", size=10),
        dragmode="pan",
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})

    # Waypoint manager
    with st.expander("▸ WAYPOINT QUEUE", expanded=False):
        c1, c2, c3 = st.columns([2, 2, 1])
        wp_x = c1.number_input("X (grid)", 0.0, 19.9, float(px), 0.1, key="wp_x")
        wp_y = c2.number_input("Y (grid)", 0.0, 19.9, float(py), 0.1, key="wp_y")
        if c3.button("+ ADD", use_container_width=True):
            if "waypoints" not in st.session_state:
                st.session_state["waypoints"] = []
            st.session_state["waypoints"].append({"x": wp_x, "y": wp_y})
            st.rerun()

        wps = st.session_state.get("waypoints", [])
        if wps:
            for i, wp in enumerate(wps):
                cc1, cc2 = st.columns([4, 1])
                cc1.markdown(
                    f"<span style='font-size:.75rem;color:#00aaff'>"
                    f"#{i+1}  X{wp['x']:.1f}  Y{wp['y']:.1f}</span>",
                    unsafe_allow_html=True
                )
                if cc2.button("✕", key=f"del_wp_{i}"):
                    st.session_state["waypoints"].pop(i)
                    st.rerun()
            cc1, cc2 = st.columns(2)
            if cc1.button("▶ RUN MISSION", type="primary", use_container_width=True):
                st.success(f"Mission queued: {len(wps)} waypoints")
            if cc2.button("✕ CLEAR ALL", use_container_width=True):
                st.session_state["waypoints"] = []
                st.rerun()

# ────────────────────────────────────────────────────────────
#  RIGHT: Proximity radar + controls
# ────────────────────────────────────────────────────────────
with col_right:
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.7rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:8px">PROXIMITY RADAR</div>
""", unsafe_allow_html=True)

    df = float(min(latest.get("dist_front", 400) or 400, 400))
    db = float(min(latest.get("dist_back",  400) or 400, 400))
    dl = float(min(latest.get("dist_left",  400) or 400, 400))
    dr = float(min(latest.get("dist_right", 400) or 400, 400))

    radar = go.Figure(go.Scatterpolar(
        r=[df, dr, db, dl, df],
        theta=[0, 90, 180, 270, 360],
        mode="lines+markers",
        fill="toself",
        fillcolor="rgba(0,255,136,.06)",
        line=dict(color="#00ff88", width=1.5),
        marker=dict(
            size=8,
            color=[
                "#ff3355" if d < 25 else "#ffaa00" if d < 50 else "#00ff88"
                for d in [df, dr, db, dl, df]
            ],
        ),
        hovertemplate="%{theta}: %{r:.0f} cm<extra></extra>",
    ))
    radar.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="#080a0e",
            radialaxis=dict(
                range=[0, 420], gridcolor="#1e2d3d",
                tickvals=[50, 100, 200, 400],
                tickfont=dict(size=8, color="#3a5060"),
                showline=False,
            ),
            angularaxis=dict(
                tickvals=[0, 90, 180, 270],
                ticktext=["F", "R", "B", "L"],
                tickfont=dict(size=11, color="#6a8090"),
                direction="clockwise", rotation=90,
            ),
        ),
        margin=dict(l=10, r=10, t=10, b=10),
        height=240,
        showlegend=False,
        font=dict(family="JetBrains Mono, monospace"),
    )
    st.plotly_chart(radar, use_container_width=True)

    # Distance grid
    def _dist_cell(label: str, val: float):
        c = "#ff3355" if val < 25 else "#ffaa00" if val < 50 else "#00ff88"
        v = "∞" if val >= 400 else f"{val:.0f}"
        return (f"<div style='text-align:center;background:#0d1117;"
                f"border:1px solid #1e2d3d;padding:6px 4px'>"
                f"<div style='font-size:.6rem;color:#3a5060;letter-spacing:1px'>{label}</div>"
                f"<div style='font-size:1.1rem;font-weight:700;color:{c}"
                f";font-family:JetBrains Mono,monospace'>{v}</div>"
                f"<div style='font-size:.6rem;color:#3a5060'>cm</div></div>")

    st.markdown(f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:8px">
  {_dist_cell('FRONT', df)}{_dist_cell('BACK', db)}
  {_dist_cell('LEFT', dl)}{_dist_cell('RIGHT', dr)}
</div>""", unsafe_allow_html=True)

    # ── WebSocket D-pad control panel ─────────────────────────
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.7rem;
            letter-spacing:3px;color:#3a5060;margin:12px 0 8px">ROBOT CONTROL</div>
""", unsafe_allow_html=True)

    # Embed the interactive WebSocket controller as HTML component
    WS_CONTROL_HTML = f"""
<!DOCTYPE html><html>
<head>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:transparent;font-family:'JetBrains Mono',monospace}}
:root{{--acc:#00ff88;--crit:#ff3355;--warn:#ffaa00;
       --bg:#080a0e;--bg2:#0d1117;--border:#1e2d3d}}

.ws-bar{{display:flex;align-items:center;gap:8px;margin-bottom:8px;
          font-size:10px;color:#6a8090}}
.ws-dot{{width:8px;height:8px;border-radius:50%;background:var(--crit);flex-shrink:0}}
.ws-dot.conn{{background:var(--acc)}}
.ws-url{{flex:1;background:var(--bg2);border:1px solid var(--border);
          color:#c8d8e8;font-family:inherit;font-size:10px;padding:4px 8px}}
.ws-btn{{background:var(--acc);border:none;color:#080a0e;font-family:inherit;
          font-size:10px;font-weight:700;padding:4px 10px;cursor:pointer}}
.ws-btn.disc{{background:transparent;border:1px solid var(--crit);color:var(--crit)}}

.mode-row{{display:flex;gap:4px;margin-bottom:8px}}
.mbtn{{flex:1;background:transparent;border:1px solid var(--border);
        color:#6a8090;font-family:inherit;font-size:9px;letter-spacing:1px;
        padding:4px 2px;cursor:pointer}}
.mbtn:hover{{border-color:var(--acc);color:var(--acc)}}
.mbtn.active{{background:var(--acc);border-color:var(--acc);color:#080a0e;font-weight:700}}
.mbtn.stop{{border-color:var(--crit);color:var(--crit)}}
.mbtn.stop.active,.mbtn.stop:hover{{background:var(--crit);color:#fff}}

.dpad{{display:grid;grid-template-columns:repeat(3,44px);
        grid-template-rows:repeat(3,44px);gap:3px;margin:0 auto;width:138px}}
.dkey{{background:var(--bg2);border:1px solid var(--border);color:#6a8090;
        font-size:18px;cursor:pointer;display:flex;align-items:center;
        justify-content:center;border-radius:2px;user-select:none}}
.dkey:active,.dkey.press{{background:var(--acc);color:#080a0e;
                           border-color:var(--acc);transform:scale(.95)}}
.dkey.cstop{{font-size:9px;letter-spacing:1px;font-weight:700;
              background:rgba(255,51,85,.1);border-color:var(--crit);color:var(--crit)}}
.dkey.cstop:active{{background:var(--crit);color:#fff}}

.hint{{font-size:8px;color:#3a5060;text-align:center;margin-top:6px;line-height:1.7}}
</style>
</head>
<body>

<div class="ws-bar">
  <div class="ws-dot" id="dot"></div>
  <input class="ws-url" id="url" value="{ws_url}">
  <button class="ws-btn" id="connbtn" onclick="toggle()">CONNECT</button>
</div>

<div class="mode-row">
  <button class="mbtn active" id="bm" onclick="setMode('MANUAL')">MAN</button>
  <button class="mbtn"        id="ba" onclick="setMode('AUTO')">AUTO</button>
  <button class="mbtn"        id="bs" onclick="setMode('SCAN')">SCAN</button>
  <button class="mbtn stop"   onclick="sendCmd('STOP')">■ STOP</button>
</div>

<div class="dpad">
  <div></div>
  <div class="dkey" id="kfwd"
       onmousedown="hold('FORWARD')" onmouseup="rel()"
       ontouchstart="hold('FORWARD')" ontouchend="rel()">▲</div>
  <div></div>
  <div class="dkey" id="klft"
       onmousedown="hold('LEFT')"    onmouseup="rel()"
       ontouchstart="hold('LEFT')"   ontouchend="rel()">◄</div>
  <div class="dkey cstop"  onmousedown="sendCmd('STOP')">STOP</div>
  <div class="dkey" id="krgt"
       onmousedown="hold('RIGHT')"   onmouseup="rel()"
       ontouchstart="hold('RIGHT')"  ontouchend="rel()">►</div>
  <div></div>
  <div class="dkey" id="kbwd"
       onmousedown="hold('BACKWARD')" onmouseup="rel()"
       ontouchstart="hold('BACKWARD')" ontouchend="rel()">▼</div>
  <div></div>
</div>

<div class="hint">W/↑ FWD · S/↓ BWD · A/← LEFT · D/→ RIGHT · SPACE=STOP</div>

<script>
let ws=null, mode='MANUAL', timer=null;

function toggle(){{
  ws&&ws.readyState<2 ? disconnect() : connect();
}}
function connect(){{
  const url=document.getElementById('url').value;
  ws=new WebSocket(url);
  setDot('connecting');
  ws.onopen=()=>{{setDot('conn');document.getElementById('connbtn').textContent='DISCONNECT';
                   document.getElementById('connbtn').classList.add('disc')}};
  ws.onclose=()=>{{setDot('');document.getElementById('connbtn').textContent='CONNECT';
                   document.getElementById('connbtn').classList.remove('disc')}};
  ws.onerror=()=>setDot('');
}}
function disconnect(){{if(ws)ws.close()}}
function setDot(s){{const d=document.getElementById('dot');
  d.className='ws-dot'+(s?' '+s:'')}}
function sendCmd(cmd){{
  if(ws&&ws.readyState===1)ws.send(JSON.stringify({{cmd}}));
}}
function hold(cmd){{
  sendCmd(cmd);
  timer=setInterval(()=>sendCmd(cmd),100);
  document.getElementById('k'+{{FORWARD:'fwd',BACKWARD:'bwd',LEFT:'lft',RIGHT:'rgt'}}[cmd])?.classList.add('press');
}}
function rel(){{
  clearInterval(timer);timer=null;
  sendCmd('STOP');
  document.querySelectorAll('.dkey').forEach(d=>d.classList.remove('press'));
}}
function setMode(m){{
  mode=m;
  ['bm','ba','bs'].forEach(id=>document.getElementById(id)?.classList.remove('active'));
  document.getElementById({{MANUAL:'bm',AUTO:'ba',SCAN:'bs'}}[m])?.classList.add('active');
  sendCmd(m==='MANUAL'?'STOP':m);
}}

// Keyboard
const km={{ArrowUp:'FORWARD',w:'FORWARD',W:'FORWARD',
           ArrowDown:'BACKWARD',s:'BACKWARD',S:'BACKWARD',
           ArrowLeft:'LEFT',a:'LEFT',A:'LEFT',
           ArrowRight:'RIGHT',d:'RIGHT',D:'RIGHT'}};
const kd=new Set();
document.addEventListener('keydown',e=>{{
  if(e.target.tagName==='INPUT')return;
  if(e.code==='Space'){{e.preventDefault();sendCmd('STOP');return}}
  if(e.key==='1')setMode('MANUAL');
  if(e.key==='2')setMode('AUTO');
  if(e.key==='3')setMode('SCAN');
  const c=km[e.key];
  if(c&&!kd.has(e.key)){{kd.add(e.key);sendCmd(c)}}
}});
document.addEventListener('keyup',e=>{{
  if(km[e.key]){{kd.delete(e.key);if(!kd.size)sendCmd('STOP')}}
}});
</script>
</body></html>
"""
    components.html(WS_CONTROL_HTML, height=340, scrolling=False)


