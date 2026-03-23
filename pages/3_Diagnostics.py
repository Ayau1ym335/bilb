"""
pages/3_Diagnostics.py  —  AI Diagnostics
═══════════════════════════════════════════
Sections:
  A — Live prediction panel: status badge, score, confidence, model tag
  B — Probability breakdown: OK / WARNING / CRITICAL bars
  C — Rule engine vs RF comparison: agreement / override table
  D — Feature importance chart (if RF trained, else mock)
  E — Issues deep-dive: per-issue severity, score contribution, description
  F — Score history: last N predictions over time
  G — Model info panel: trained / mock, OOB score, samples, version
  H — Retrain trigger (operator/admin only)
"""

import json
import os
import sys
import time
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from frontend.auth import (
    require_auth, has_perm, render_sidebar_user,
    building_meta, render_building_form,
)

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="BILB — AI Diagnostics",
    page_icon="🤖",
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
  <div style="font-size:.6rem;letter-spacing:3px;color:#3a5060">AI DIAGNOSTICS</div>
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

    chart_limit = st.selectbox(
        "History window",
        [50, 100, 200, 500], index=1,
        format_func=lambda x: f"Last {x} readings",
    )

    show_features  = st.toggle("Feature importance",  True)
    show_history   = st.toggle("Score history chart", True)
    show_model_info= st.toggle("Model info panel",    True)

    auto_refresh = st.toggle("Auto-refresh (5s)", False)
    if auto_refresh:
        st.rerun()

    st.markdown("---")

    # ── Retrain (operator / admin only) ──────────────────────
    st.markdown("""
<div style="font-size:.65rem;letter-spacing:2px;color:#3a5060;margin-bottom:8px">
  ML MODEL
</div>""", unsafe_allow_html=True)

    if st.button("⟳ RETRAIN MODEL", use_container_width=True,
                 disabled=not has_perm("scan"),
                 help="Requires operator or admin role"):
        st.session_state["_retrain_requested"] = True

    if not has_perm("scan"):
        st.caption("Viewer role — retrain disabled")

# ── Building gate ─────────────────────────────────────────────
if not render_building_form():
    st.stop()

# ══════════════════════════════════════════════════════════════
#  Constants matching the rest of the app
# ══════════════════════════════════════════════════════════════
STATUS_COLOR = {"OK": "#00ff88", "WARNING": "#ffaa00", "CRITICAL": "#ff3355"}
PLOTLY_BASE  = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a0d12",
    font=dict(family="JetBrains Mono, monospace", color="#6a8090", size=10),
    margin=dict(l=0, r=0, t=20, b=0),
    xaxis=dict(gridcolor="#111820", showgrid=True, zeroline=False),
    yaxis=dict(gridcolor="#111820", showgrid=True, zeroline=False),
)

ISSUE_META = {
    "HIGH_HUMIDITY":            ("CRITICAL", "#ff3355", "Humidity ≥ 70% — waterproofing required"),
    "ELEVATED_HUMIDITY":        ("WARNING",  "#ffaa00", "Humidity 55–70% — monitor closely"),
    "VIBRATION_DETECTED":       ("WARNING",  "#ffaa00", "Vibration event detected"),
    "STRUCTURAL_RISK_COMBO":    ("CRITICAL", "#ff3355", "Humidity + Vibration — structural audit"),
    "HIGH_TEMPERATURE":         ("WARNING",  "#ffaa00", "Temperature ≥ 40°C — HVAC audit"),
    "ELEVATED_TEMPERATURE":     ("INFO",     "#00aaff", "Temperature 30–40°C"),
    "CRITICAL_STRUCTURAL_TILT": ("CRITICAL", "#ff3355", "Tilt ≥ 15° — geotechnical survey"),
    "TILT_DETECTED":            ("WARNING",  "#ffaa00", "Tilt 5–15° — monitoring required"),
    "POOR_DAYLIGHTING":         ("INFO",     "#00aaff", "Light < 100 lux — glazing review"),
}

SCORE_MAP = {
    "HIGH_HUMIDITY": 40, "ELEVATED_HUMIDITY": 20,
    "VIBRATION_DETECTED": 25, "STRUCTURAL_RISK_COMBO": 15,
    "HIGH_TEMPERATURE": 20, "ELEVATED_TEMPERATURE": 8,
    "CRITICAL_STRUCTURAL_TILT": 35, "TILT_DETECTED": 12,
    "POOR_DAYLIGHTING": 5,
}

FEATURE_COLS = [
    "humidity", "temperature", "light_lux", "pressure",
    "tilt_roll", "tilt_pitch", "max_tilt", "accel_z", "vibration",
    "dist_front", "dist_back", "dist_left", "dist_right",
]

FEATURE_UNITS = {
    "humidity": "%", "temperature": "°C", "light_lux": "lx",
    "pressure": "hPa", "tilt_roll": "°", "tilt_pitch": "°",
    "max_tilt": "°", "accel_z": "m/s²", "vibration": "0/1",
    "dist_front": "cm", "dist_back": "cm",
    "dist_left": "cm", "dist_right": "cm",
}


def _demo_latest():
    import math, time as t
    tau = t.time() * 0.08
    h   = 55 + 20 * math.sin(tau * .7)
    vib = h > 65
    score = min(100, (40 if h >= 70 else 20 if h >= 55 else 0) +
                     (25 if vib else 0) + (15 if vib and h >= 70 else 0))
    status = "CRITICAL" if score >= 65 else "WARNING" if score >= 30 else "OK"
    issues = (
        (["HIGH_HUMIDITY"] if h >= 70 else ["ELEVATED_HUMIDITY"] if h >= 55 else []) +
        (["VIBRATION_DETECTED"] if vib else []) +
        (["STRUCTURAL_RISK_COMBO"] if vib and h >= 70 else [])
    )
    return {
        "temperature": round(22 + 4 * math.sin(tau), 1),
        "humidity":    round(h, 1),
        "light_lux":   round(max(0, 180 + 100 * math.sin(tau * .5))),
        "pressure":    round(1013 + 3 * math.sin(tau * .3), 1),
        "tilt_roll":   round(2 * math.sin(tau * 1.2), 2),
        "tilt_pitch":  round(1 * math.cos(tau * .8), 2),
        "accel_z":     round(9.81 + 0.05 * math.sin(tau), 3),
        "vibration":   vib,
        "dist_front":  round(60 + 40 * abs(math.sin(tau)), 1),
        "dist_back":   round(120 + 50 * math.cos(tau), 1),
        "dist_left":   round(45 + 30 * abs(math.sin(tau * 1.3)), 1),
        "dist_right":  round(80 + 35 * math.cos(tau * .9), 1),
        "status":      status,
        "score":       round(score, 1),
        "issues":      json.dumps(issues),
    }


def _parse_issues(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [i for i in raw if i and i.upper() != "NONE"]
    try:
        lst = json.loads(raw)
        return [i for i in lst if i and i.upper() != "NONE"]
    except Exception:
        return [i.strip() for i in str(raw).split(",")
                if i.strip() and i.strip().upper() != "NONE"]


def _ts(r):
    try:
        return datetime.fromisoformat(r["received_at"].replace("Z", ""))
    except Exception:
        return None


def _demo_ml_result(reading: dict) -> dict:
    import random
    status = reading.get("status", "WARNING")
    score  = float(reading.get("score", 40) or 40)
    rng    = random.Random(int(score * 10))
    conf   = round(rng.uniform(0.70, 0.88), 3)
    other  = round((1 - conf) / 2, 3)
    label  = {"OK": 0, "WARNING": 1, "CRITICAL": 2}.get(status, 1)
    proba  = [other, other, other]
    proba[label] = conf
    total  = sum(proba)
    proba  = [round(p / total, 3) for p in proba]
    return {
        "status":        status,
        "label":         label,
        "score":         score,
        "confidence":    conf,
        "probabilities": {"OK": proba[0], "WARNING": proba[1], "CRITICAL": proba[2]},
        "issues":        _parse_issues(reading.get("issues", [])),
        "model":         "mock",
        "rule_status":   status,
    }


def _demo_readings(n: int) -> list:
    import math, random, time as t
    rnd, now = random.Random(99), t.time()
    rows = []
    for i in range(n):
        tau = (now - (n - i) * 10) * 0.08
        h   = max(10, min(100, 55 + 20 * math.sin(tau * .7) + rnd.gauss(0, 2)))
        vib = h > 68 and rnd.random() > 0.5
        score = min(100, (40 if h >= 70 else 20 if h >= 55 else 0) + (25 if vib else 0))
        rows.append({
            "received_at": datetime.fromtimestamp(now - (n - i) * 10).isoformat(),
            "temperature": round(22 + 4 * math.sin(tau) + rnd.gauss(0, .3), 1),
            "humidity":    round(h, 1),
            "light_lux":   round(max(0, 180 + 100 * math.sin(tau * .5))),
            "tilt_roll":   round(2 * math.sin(tau * 1.2), 2),
            "tilt_pitch":  round(1 * math.cos(tau * .8), 2),
            "accel_z":     round(9.81 + rnd.gauss(0, .03), 3),
            "vibration":   vib,
            "dist_front":  round(60 + 40 * abs(math.sin(tau)), 1),
            "dist_back":   round(120 + 50 * math.cos(tau), 1),
            "dist_left":   round(45 + 30 * abs(math.sin(tau * 1.3)), 1),
            "dist_right":  round(80 + 35 * math.cos(tau * .9), 1),
            "status":      "CRITICAL" if score >= 65 else "WARNING" if score >= 30 else "OK",
            "score":       round(score, 1),
        })
    return rows

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


@st.cache_data(ttl=30)
def _load_profile(bid):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/buildings/{bid}", timeout=2)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def _run_ml_on_reading(reading: dict) -> dict:
    """Call local ML engine directly (fast path, no HTTP hop)."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from ml import get_status
        return get_status(reading)
    except Exception:
        return _demo_ml_result(reading)


def _load_model_meta() -> dict:
    """Load RF model metadata if available."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from ml import get_classifier
        clf = get_classifier()
        return {
            "trained":   clf.is_trained(),
            "meta":      clf.meta,
            "feat_imp":  clf.feature_importance,
        }
    except Exception:
        return {"trained": False, "meta": {}, "feat_imp": {}}


def _retrain_model(bid: str) -> dict:
    """Trigger ML retraining on readings from DB."""
    try:
        import requests
        # Use the existing readings endpoint to get training data
        r = requests.get(f"{API_URL}/api/telemetry/{bid}?limit=2000", timeout=10)
        rows = r.json() if r.ok else []
        if len(rows) < 20:
            return {"ok": False, "reason": f"Only {len(rows)} readings — need ≥ 20"}

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from ml import get_classifier, reload_classifier
        clf = get_classifier()
        metrics = clf.train(rows, save=True)
        reload_classifier()
        return {"ok": True, "metrics": metrics}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ── Demo data ─────────────────────────────────────────────────
# ── Fetch data ────────────────────────────────────────────────
latest   = _load_latest(BUILDING_ID)
readings = _load_readings(BUILDING_ID, chart_limit)
profile  = _load_profile(BUILDING_ID)

# Run ML on latest reading
ml       = _run_ml_on_reading(latest)
issues   = _parse_issues(ml.get("issues") or latest.get("issues"))

status   = ml.get("status", "UNKNOWN")
score    = float(ml.get("score", 0) or 0)
conf     = float(ml.get("confidence", 0) or 0)
proba    = ml.get("probabilities", {"OK": 0.33, "WARNING": 0.34, "CRITICAL": 0.33})
model_nm = ml.get("model", "mock")
rule_st  = ml.get("rule_status", status)
sc       = STATUS_COLOR.get(status, "#6a8090")
rule_c   = STATUS_COLOR.get(rule_st, "#6a8090")

# ── Handle retrain request ────────────────────────────────────
if st.session_state.pop("_retrain_requested", False):
    with st.spinner("Retraining Random Forest on DB readings…"):
        result = _retrain_model(BUILDING_ID)
    if result.get("ok"):
        m = result.get("metrics", {})
        st.success(
            f"✓ Model retrained — Accuracy: {m.get('accuracy', 0):.1%} · "
            f"OOB: {m.get('oob_score', 0):.1%} · "
            f"Samples: {m.get('n_samples', 0):,}"
        )
        _load_readings.clear()
    else:
        st.error(f"Retrain failed: {result.get('reason', 'unknown error')}")

# ══════════════════════════════════════════════════════════════
#  SECTION A — LIVE PREDICTION PANEL
# ══════════════════════════════════════════════════════════════
st.markdown(f"""
<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
  <div>
    <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6rem;
                font-weight:800;letter-spacing:3px;color:#c8d8e8">
      AI DIAGNOSTICS
    </div>
    <div style="font-size:.7rem;color:#3a5060">
      Random Forest · Rule Engine · 13 sensor features
    </div>
  </div>
  <div style="margin-left:auto;display:flex;align-items:center;gap:8px">
    <div style="background:{'#00aaff' if model_nm == 'random_forest' else '#3a5060'}22;
                border:1px solid {'#00aaff' if model_nm == 'random_forest' else '#3a5060'};
                padding:3px 10px;font-size:.6rem;letter-spacing:2px;
                color:{'#00aaff' if model_nm == 'random_forest' else '#6a8090'}">
      {'🤖 RANDOM FOREST' if model_nm == 'random_forest' else '⚙ RULE ENGINE (MOCK)'}
    </div>
    <div style="font-size:.6rem;color:#3a5060">{time.strftime('%H:%M:%S')} UTC</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Row 1: Badge · Score gauge · Confidence · Agreement ──────
col_badge, col_gauge, col_conf, col_agree = st.columns([1.4, 1.8, 1.4, 1.4], gap="small")

with col_badge:
    st.markdown(f"""
<div style="background:{sc}11;border:2px solid {sc}44;
            padding:20px 16px;text-align:center;
            height:156px;display:flex;flex-direction:column;
            justify-content:center;border-radius:2px">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.6rem;
              font-weight:800;letter-spacing:5px;color:{sc};
              text-shadow:0 0 16px {sc}44;line-height:1">{status}</div>
  <div style="font-size:.6rem;color:#6a8090;letter-spacing:2px;margin-top:6px">
    BUILDING STATUS
  </div>
  <div style="font-size:.8rem;color:{sc};margin-top:4px;font-weight:700">
    {score:.0f} / 100
  </div>
</div>
""", unsafe_allow_html=True)

with col_gauge:
    fig_g = go.Figure(go.Indicator(
        mode   = "gauge+number",
        value  = score,
        number = {"font": {"size": 26, "color": sc,
                           "family": "JetBrains Mono, monospace"},
                  "suffix": "/100"},
        title  = {"text": "DEGRADATION SCORE",
                  "font": {"size": 9, "color": "#6a8090",
                           "family": "JetBrains Mono, monospace"}},
        gauge  = {
            "axis": {
                "range": [0, 100],
                "tickvals": [0, 30, 65, 100],
                "tickfont": {"size": 8, "color": "#6a8090"},
                "tickwidth": 0.5, "tickcolor": "#1e2d3d",
            },
            "bar":   {"color": sc, "thickness": 0.22},
            "bgcolor": "#0d1117",
            "borderwidth": 0.5, "bordercolor": "#1e2d3d",
            "steps": [
                {"range": [0,  30], "color": "rgba(0,255,136,.05)"},
                {"range": [30, 65], "color": "rgba(255,170,0,.05)"},
                {"range": [65,100], "color": "rgba(255,51,85,.07)"},
            ],
            "threshold": {"line": {"color": sc, "width": 2},
                          "thickness": 0.75, "value": score},
        },
    ))
    fig_g.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="JetBrains Mono, monospace"),
        margin=dict(l=16, r=16, t=28, b=8),
        height=156,
    )
    st.plotly_chart(fig_g, use_container_width=True)

with col_conf:
    conf_c = "#00ff88" if conf >= 0.80 else "#ffaa00" if conf >= 0.60 else "#ff3355"
    st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;
            padding:16px 12px;height:156px;display:flex;
            flex-direction:column;justify-content:center;gap:10px">
  <div>
    <div style="font-size:.6rem;letter-spacing:2px;color:#3a5060;margin-bottom:4px">
      CONFIDENCE
    </div>
    <div style="font-size:1.8rem;font-weight:700;color:{conf_c};
                font-family:'JetBrains Mono',monospace;line-height:1">
      {conf:.0%}
    </div>
    <div style="height:3px;background:#111820;border-radius:2px;margin-top:6px">
      <div style="width:{conf*100:.0f}%;height:100%;background:{conf_c};
                  border-radius:2px"></div>
    </div>
  </div>
  <div>
    <div style="font-size:.6rem;letter-spacing:2px;color:#3a5060;margin-bottom:3px">
      FEATURES USED
    </div>
    <div style="font-size:1rem;font-weight:700;color:#00aaff;
                font-family:'JetBrains Mono',monospace">
      {ml.get('features_used', 13)} / 13
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

with col_agree:
    agree    = rule_st == status
    agree_c  = "#00ff88" if agree else "#ffaa00"
    agree_lbl= "AGREE" if agree else "OVERRIDE"
    agree_ico= "✓" if agree else "△"
    st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;
            padding:16px 12px;height:156px;display:flex;
            flex-direction:column;justify-content:center;gap:8px">
  <div>
    <div style="font-size:.6rem;letter-spacing:2px;color:#3a5060;margin-bottom:3px">
      RULE ENGINE
    </div>
    <div style="font-size:1.1rem;font-weight:700;color:{rule_c};
                font-family:'JetBrains Mono',monospace">{rule_st}</div>
  </div>
  <div style="border-top:1px solid #111820;padding-top:8px">
    <div style="font-size:.6rem;letter-spacing:2px;color:#3a5060;margin-bottom:3px">
      RF vs RULES
    </div>
    <div style="display:inline-flex;align-items:center;gap:6px;
                background:{agree_c}18;border:1px solid {agree_c}55;
                padding:3px 10px;border-radius:2px">
      <span style="color:{agree_c};font-weight:700;font-size:.75rem">{agree_ico}</span>
      <span style="color:{agree_c};font-size:.65rem;letter-spacing:1px;
                   font-weight:700">{agree_lbl}</span>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION B — PROBABILITY BREAKDOWN
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  CLASS PROBABILITIES
</div>""", unsafe_allow_html=True)

p_ok   = float(proba.get("OK",       0))
p_warn = float(proba.get("WARNING",  0))
p_crit = float(proba.get("CRITICAL", 0))

# Probability bars
for lbl, pval, color in [
    ("OK",       p_ok,   "#00ff88"),
    ("WARNING",  p_warn, "#ffaa00"),
    ("CRITICAL", p_crit, "#ff3355"),
]:
    is_pred = lbl == status
    border  = f"border-left:3px solid {color}" if is_pred else "border-left:3px solid #1e2d3d"
    st.markdown(f"""
<div style="background:#0d1117;{border};padding:8px 12px;margin-bottom:5px;
            display:flex;align-items:center;gap:12px">
  <div style="font-size:.7rem;font-weight:700;letter-spacing:2px;
              color:{color if is_pred else '#3a5060'};width:80px">{lbl}</div>
  <div style="flex:1;height:8px;background:#111820;border-radius:4px;overflow:hidden">
    <div style="width:{pval*100:.1f}%;height:100%;background:{color};
                border-radius:4px;transition:width .5s"></div>
  </div>
  <div style="font-size:.85rem;font-weight:700;color:{color};
              font-family:'JetBrains Mono',monospace;width:48px;text-align:right">
    {pval:.1%}
  </div>
  {'<div style="font-size:.6rem;color:#6a8090;margin-left:4px">← predicted</div>' if is_pred else ''}
</div>""", unsafe_allow_html=True)

# Stacked probability bar
st.markdown(f"""
<div style="display:flex;height:6px;border-radius:3px;overflow:hidden;margin:6px 0 16px">
  <div style="width:{p_ok*100:.1f}%;background:#00ff88"></div>
  <div style="width:{p_warn*100:.1f}%;background:#ffaa00"></div>
  <div style="width:{p_crit*100:.1f}%;background:#ff3355"></div>
</div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION C — ISSUES DEEP-DIVE
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  DETECTED ISSUES
</div>""", unsafe_allow_html=True)

if not issues:
    st.markdown("""
<div style="background:rgba(0,255,136,.06);border:1px solid rgba(0,255,136,.3);
            padding:12px 16px;color:#00ff88;font-size:.8rem;border-radius:2px">
  ✓ No issues detected — all sensor parameters within normal thresholds
</div>""", unsafe_allow_html=True)
else:
    # Issue cards
    issue_cols = st.columns(min(len(issues), 3), gap="small")
    for idx, issue in enumerate(issues):
        sev, color, desc = ISSUE_META.get(issue, ("INFO", "#00aaff", issue))
        pts = SCORE_MAP.get(issue, 0)
        with issue_cols[idx % len(issue_cols)]:
            st.markdown(f"""
<div style="background:{color}0e;border:1px solid {color}44;
            border-left:3px solid {color};padding:12px 14px;
            margin-bottom:8px;border-radius:0 2px 2px 0">
  <div style="display:flex;justify-content:space-between;align-items:center;
              margin-bottom:4px">
    <div style="font-size:.6rem;font-weight:700;letter-spacing:1px;color:{color}">
      {sev}
    </div>
    <div style="font-size:.7rem;font-weight:700;color:{color};
                font-family:'JetBrains Mono',monospace">+{pts} pts</div>
  </div>
  <div style="font-size:.8rem;font-weight:700;color:#c8d8e8;
              font-family:'JetBrains Mono',monospace;margin-bottom:4px">{issue}</div>
  <div style="font-size:.7rem;color:#6a8090;line-height:1.4">{desc}</div>
  <div style="height:3px;background:#111820;border-radius:2px;margin-top:8px">
    <div style="width:{pts}%;height:100%;background:{color};border-radius:2px"></div>
  </div>
</div>""", unsafe_allow_html=True)

    # Score tally
    total_score = min(100, sum(SCORE_MAP.get(i, 0) for i in issues))
    st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-left:3px solid {sc};
            padding:8px 14px;display:flex;align-items:center;gap:12px;margin-top:4px">
  <div style="font-size:.65rem;letter-spacing:1px;color:#3a5060">TOTAL SCORE (capped at 100)</div>
  <div style="font-size:1rem;font-weight:700;color:{sc};
              font-family:'JetBrains Mono',monospace">{total_score:.0f} / 100</div>
  <div style="flex:1;height:5px;background:#111820;border-radius:3px;margin-left:8px">
    <div style="width:{total_score}%;height:100%;background:{sc};border-radius:3px"></div>
  </div>
</div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION D — FEATURE IMPORTANCE
# ══════════════════════════════════════════════════════════════
if show_features:
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  FEATURE IMPORTANCE
</div>""", unsafe_allow_html=True)

    model_info = _load_model_meta()
    feat_imp   = model_info.get("feat_imp", {})

    # If RF is not trained, build a mock importance from rule weights
    if not feat_imp:
        feat_imp = {
            "humidity": 0.22, "vibration": 0.18, "tilt_roll": 0.14,
            "temperature": 0.10, "tilt_pitch": 0.09, "max_tilt": 0.08,
            "accel_z": 0.06, "light_lux": 0.05, "pressure": 0.03,
            "dist_front": 0.02, "dist_back": 0.01, "dist_left": 0.01,
            "dist_right": 0.01,
        }
        _is_mock_imp = True
    else:
        _is_mock_imp = False

    # Sort descending
    sorted_imp = sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)

    fi_col1, fi_col2 = st.columns([2, 1], gap="small")

    with fi_col1:
        feat_names = [f[0] for f in sorted_imp]
        feat_vals  = [f[1] for f in sorted_imp]

        # Color: top 3 = accent, rest = muted
        bar_colors = [
            "#00ff88" if i < 3 else
            "#ffaa00" if i < 6 else
            "#378add"
            for i in range(len(feat_vals))
        ]

        fig_fi = go.Figure(go.Bar(
            x=feat_vals,
            y=[f"{n} <span style='color:#3a5060'>({FEATURE_UNITS.get(n, '')})</span>"
               for n in feat_names],
            orientation="h",
            marker=dict(color=bar_colors,
                        line=dict(color="#1e2d3d", width=0.5)),
            text=[f"{v:.3f}" for v in feat_vals],
            textposition="outside",
            textfont=dict(size=8, color="#6a8090"),
            hovertemplate="%{y}: %{x:.4f}<extra></extra>",
        ))
        fig_fi.update_layout(
            **PLOTLY_BASE,
            height=max(260, len(feat_names) * 22),
            title=dict(
                text=f"FEATURE IMPORTANCE {'(mock — train model for real values)' if _is_mock_imp else '(Random Forest)'}",
                font=dict(size=9, color="#3a5060"),
            ),
            xaxis=dict(gridcolor="#111820", zeroline=False, showgrid=True,
                       title="Importance"),
            yaxis=dict(gridcolor="#111820", zeroline=False, showgrid=False,
                       autorange="reversed"),
            showlegend=False,
        )
        st.plotly_chart(fig_fi, use_container_width=True)

    with fi_col2:
        # Current reading feature values
        st.markdown("""
<div style="font-size:.65rem;letter-spacing:2px;color:#3a5060;
            margin-bottom:8px">CURRENT VALUES</div>""", unsafe_allow_html=True)

        for feat, imp in sorted_imp[:8]:
            val = latest.get(feat)
            if val is None:
                val_str = "—"
                bar_w   = 0
                fc      = "#3a5060"
            else:
                val_str = f"{float(val):.2f}" if isinstance(val, float) else str(val)
                # Rough normalisation for bar display
                maxvals = {
                    "humidity": 100, "temperature": 50, "light_lux": 500,
                    "pressure": 1040, "tilt_roll": 20, "tilt_pitch": 20,
                    "max_tilt": 20, "accel_z": 12, "vibration": 1,
                    "dist_front": 400, "dist_back": 400,
                    "dist_left": 400, "dist_right": 400,
                }
                bar_w = min(100, abs(float(val)) / maxvals.get(feat, 100) * 100)
                fc    = "#00ff88" if imp >= 0.15 else "#ffaa00" if imp >= 0.08 else "#378add"
            st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;
            padding:5px 8px;margin-bottom:3px">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="font-size:.65rem;color:#6a8090">{feat}</div>
    <div style="font-size:.75rem;font-weight:700;color:{fc};
                font-family:'JetBrains Mono',monospace">{val_str}
      <span style="font-size:.55rem;color:#3a5060">{FEATURE_UNITS.get(feat,'')}</span>
    </div>
  </div>
  <div style="height:2px;background:#111820;margin-top:3px;border-radius:1px">
    <div style="width:{bar_w:.0f}%;height:100%;background:{fc};border-radius:1px"></div>
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION E — SCORE HISTORY + STATUS DISTRIBUTION
# ══════════════════════════════════════════════════════════════
if show_history:
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  PREDICTION HISTORY
</div>""", unsafe_allow_html=True)

    timestamps = [_ts(r) for r in readings]
    valid_idx  = [i for i, t in enumerate(timestamps) if t is not None]
    ts_valid   = [timestamps[i] for i in valid_idx]
    r_valid    = [readings[i]   for i in valid_idx]

    scores_h   = [float(r.get("score",  0) or 0) for r in r_valid]
    statuses_h = [r.get("status", "OK")           for r in r_valid]

    hist_l, hist_r = st.columns([2.5, 1], gap="small")

    with hist_l:
        fig_h = go.Figure()
        # Zone fills
        fig_h.add_hrect(y0=65, y1=105, fillcolor="rgba(255,51,85,.04)",  line_width=0, layer="below")
        fig_h.add_hrect(y0=30, y1=65,  fillcolor="rgba(255,170,0,.04)",  line_width=0, layer="below")
        fig_h.add_hrect(y0=0,  y1=30,  fillcolor="rgba(0,255,136,.03)", line_width=0, layer="below")

        # Score line
        fig_h.add_trace(go.Scatter(
            x=ts_valid, y=scores_h,
            mode="lines",
            line=dict(color="#00ff88", width=1.5),
            fill="tozeroy", fillcolor="rgba(0,255,136,.04)",
            name="Score",
            hovertemplate="%{x|%H:%M:%S}<br>Score: %{y:.1f}<extra></extra>",
        ))

        # Status change markers
        for target_st, color in [("CRITICAL", "#ff3355"), ("WARNING", "#ffaa00")]:
            xs = [ts_valid[i] for i, s in enumerate(statuses_h) if s == target_st]
            ys = [scores_h[i] for i, s in enumerate(statuses_h) if s == target_st]
            if xs:
                fig_h.add_trace(go.Scatter(
                    x=xs, y=ys, mode="markers",
                    marker=dict(size=4, color=color, opacity=0.7),
                    name=target_st, showlegend=True,
                    hovertemplate=f"{target_st}: %{{y:.1f}}<extra></extra>",
                ))

        fig_h.add_hline(y=30, line=dict(color="#ffaa00", width=0.7, dash="dot"))
        fig_h.add_hline(y=65, line=dict(color="#ff3355", width=0.7, dash="dot"))

        fig_h.update_layout(
            **PLOTLY_BASE, height=180,
            title=dict(text="DEGRADATION SCORE OVER TIME",
                       font=dict(size=9, color="#3a5060")),
            yaxis=dict(gridcolor="#111820", range=[0, 105],
                       title="score", zeroline=False),
            legend=dict(orientation="h", y=1.1,
                        font=dict(size=8, color="#6a8090"),
                        bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig_h, use_container_width=True)

    with hist_r:
        from collections import Counter
        cnt  = Counter(statuses_h)
        ok_n = cnt.get("OK", 0)
        wn_n = cnt.get("WARNING", 0)
        cr_n = cnt.get("CRITICAL", 0)
        tot  = max(ok_n + wn_n + cr_n, 1)

        fig_d = go.Figure(go.Pie(
            labels=["OK", "WARNING", "CRITICAL"],
            values=[ok_n, wn_n, cr_n],
            hole=0.58,
            marker=dict(
                colors=["#00ff88", "#ffaa00", "#ff3355"],
                line=dict(color="#080a0e", width=2),
            ),
            textfont=dict(size=8, color="#6a8090",
                          family="JetBrains Mono, monospace"),
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        ))
        fig_d.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=20, b=0),
            height=180,
            showlegend=False,
            annotations=[dict(
                text=f"{cr_n + wn_n}<br><span style='font-size:8px'>anomalies</span>",
                x=0.5, y=0.5, font_size=11, font_color=sc,
                showarrow=False,
            )],
            title=dict(text="STATUS DIST.",
                       font=dict(size=9, color="#3a5060")),
        )
        st.plotly_chart(fig_d, use_container_width=True)

    st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION F — MODEL INFO PANEL
# ══════════════════════════════════════════════════════════════
if show_model_info:
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  MODEL INFORMATION
</div>""", unsafe_allow_html=True)

    model_info = _load_model_meta()
    is_trained = model_info.get("trained", False)
    meta       = model_info.get("meta", {})

    mi1, mi2, mi3, mi4 = st.columns(4, gap="small")

    def _info_cell(col, label, value, color="#00aaff", sub=""):
        col.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-top:2px solid {color};
            padding:12px;text-align:center">
  <div style="font-size:.6rem;letter-spacing:2px;color:#3a5060;margin-bottom:4px">{label}</div>
  <div style="font-size:1rem;font-weight:700;color:{color};
              font-family:'JetBrains Mono',monospace">{value}</div>
  <div style="font-size:.6rem;color:#6a8090;margin-top:3px">{sub}</div>
</div>""", unsafe_allow_html=True)

    _info_cell(
        mi1, "MODEL TYPE",
        "RANDOM FOREST" if is_trained else "RULE ENGINE",
        "#00ff88" if is_trained else "#6a8090",
        f"v{meta.get('ml_model_version','—')}" if is_trained else "mock classifier",
    )
    _info_cell(
        mi2, "ACCURACY",
        f"{meta.get('accuracy', 0):.1%}" if is_trained else "—",
        "#00ff88" if meta.get("accuracy", 0) >= 0.85 else "#ffaa00",
        f"OOB: {meta.get('oob_score', 0):.1%}" if is_trained else "train to activate RF",
    )
    _info_cell(
        mi3, "TRAINING SET",
        f"{meta.get('n_samples', 0):,}" if is_trained else "—",
        "#00aaff",
        f"{meta.get('n_train', 0):,} train / {meta.get('n_test', 0):,} test" if is_trained else "no model saved",
    )
    _info_cell(
        mi4, "FEATURES",
        f"{meta.get('n_features', 13)}",
        "#00aaff",
        f"{meta.get('n_estimators', '—')} trees" if is_trained else "13 sensor inputs",
    )

    # Per-class metrics table if trained
    if is_trained and meta.get("per_class"):
        st.markdown("""
<div style="font-size:.65rem;letter-spacing:1px;color:#3a5060;margin:12px 0 6px">
  PER-CLASS METRICS
</div>""", unsafe_allow_html=True)

        pc = meta["per_class"]
        hc1, hc2, hc3, hc4 = st.columns([1.2, 1, 1, 1], gap="small")
        for col, lbl in zip([hc1, hc2, hc3, hc4], ["CLASS", "PRECISION", "RECALL", "F1"]):
            col.markdown(f"""
<div style="background:#111820;padding:5px 8px;font-size:.6rem;
            letter-spacing:1px;color:#6a8090;font-weight:700">{lbl}</div>""",
                         unsafe_allow_html=True)

        for cls_name, cls_c in [("OK","#00ff88"), ("WARNING","#ffaa00"), ("CRITICAL","#ff3355")]:
            m = pc.get(cls_name, {})
            r1, r2, r3, r4 = st.columns([1.2, 1, 1, 1], gap="small")
            r1.markdown(f"""
<div style="background:#0a0d12;border-bottom:1px solid #111820;
            padding:5px 8px;font-size:.75rem;font-weight:700;color:{cls_c}">{cls_name}</div>""",
                        unsafe_allow_html=True)
            for rcol, val_key in zip([r2, r3, r4], ["precision", "recall", "f1"]):
                val = m.get(val_key, 0)
                vc  = "#00ff88" if val >= 0.85 else "#ffaa00" if val >= 0.70 else "#ff3355"
                rcol.markdown(f"""
<div style="background:#0a0d12;border-bottom:1px solid #111820;
            padding:5px 8px;font-size:.78rem;font-weight:700;
            color:{vc};font-family:'JetBrains Mono',monospace">{val:.2f}</div>""",
                              unsafe_allow_html=True)

    # If not trained — call to action
    if not is_trained:
        st.markdown("""
<div style="background:#0d1117;border:1px dashed #1e2d3d;border-left:3px solid #ffaa00;
            padding:12px 16px;margin-top:10px;font-size:.78rem;color:#6a8090;
            line-height:1.7">
  <span style="color:#ffaa00;font-weight:700">△ Mock classifier active.</span>
  Using rule-based engine only. To activate Random Forest:<br>
  <span style="color:#c8d8e8">1.</span> Collect ≥ 200 readings via the bridge<br>
  <span style="color:#c8d8e8">2.</span> Click <span style="color:#00ff88">⟳ RETRAIN MODEL</span>
  in the sidebar (operator / admin)<br>
  <span style="color:#c8d8e8">3.</span> Or run:
  <span style="font-family:'JetBrains Mono',monospace;color:#00aaff">
    python -m ml.classifier --train</span>
</div>""", unsafe_allow_html=True)
