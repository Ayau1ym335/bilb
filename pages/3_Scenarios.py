"""
pages/3_Scenarios.py  —  Scenario Lab
═══════════════════════════════════════
Layout:
  · Generate button → calls LLM Strategist (Gemini + RAG)
  · Side-by-side comparison table (3 columns × all metrics)
  · Feasibility bar + type icon per scenario
  · Per-scenario accordion: description, benefits, challenges, priority works
  · Radar chart overlay: Feasibility vs ROI vs CO₂ for all 3
  · "Export to PDF" shortcut
"""

import json
import os
import sys
import time

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from frontend.auth import (
    require_auth, has_perm, render_sidebar_user,
    building_meta, render_building_form,
)

# ── Page config ───────────────────────────────────────────────
st.set_page_config(
    page_title="BILB — Scenario Lab",
    page_icon="🌿",
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
  <div style="font-size:.6rem;letter-spacing:3px;color:#3a5060">SCENARIO LAB</div>
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

    use_cache   = st.toggle("Use cached scenarios", True,
                             help="Disable to force fresh Gemini call")
    force_fb    = st.toggle("Force fallback (demo)", False,
                             help="Skip Gemini, use rule-based scenarios")
    show_radar  = st.toggle("Radar comparison chart", True)
    show_detail = st.toggle("Expanded details", False)

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
        return {}

@st.cache_data(ttl=5)
def _load_readings_agg(bid, limit=200):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/telemetry/{bid}?limit={limit}", timeout=2)
        rows = r.json() if r.ok else []
    except Exception:
        rows = []
    if not rows:
        return {}
    return {
        "avg_humidity":   sum(float(r.get("humidity",0) or 0) for r in rows) / len(rows),
        "avg_temperature":sum(float(r.get("temperature",0) or 0) for r in rows) / len(rows),
        "vibration_events":sum(1 for r in rows if r.get("vibration")),
        "max_tilt_roll":  max((abs(float(r.get("tilt_roll",0) or 0)) for r in rows), default=0),
        "max_tilt_pitch": max((abs(float(r.get("tilt_pitch",0) or 0)) for r in rows), default=0),
        "total_readings": len(rows),
    }

@st.cache_data(ttl=60)
def _call_strategist(bid, building_data_json: str, use_cache: bool, force_fb: bool):
    """Cached wrapper — key includes building_data_json so new data triggers re-call.
    NOTE: no st.* calls inside this function — @st.cache_data forbids side effects."""
    try:
        import requests
        resp = requests.post(
            f"{API_URL}/api/buildings/{bid}/scenarios"
            f"?force_fallback={'true' if force_fb else 'false'}",
            timeout=15,
        )
        if resp.ok:
            return resp.json().get("scenarios", [])
        # API unavailable — fall back to direct import
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from llm.strategist import generate_scenarios
        return generate_scenarios(
            json.loads(building_data_json),
            use_cache=use_cache,
            force_fallback=force_fb,
        )
    except ImportError:
        return _demo_scenarios()
    except Exception:
        # Error message is returned as a flag; caller shows it via st.warning
        return None

def _demo_scenarios():
    return [
        {
            "id": 1, "title": "Cultural Hub & Coworking",
            "type": "cultural",
            "tagline": "Historic character becomes the brand — rent premium guaranteed.",
            "description": ("The building's exposed brick and high ceilings create premium "
                            "coworking atmosphere. Requires waterproofing before opening, "
                            "but heritage grants offset 25–30% of costs. Target $250–400/desk/month."),
            "benefits":       ["25% rental premium vs standard office",
                               "Strong cultural heritage grant eligibility",
                               "Minimal structural reconfiguration"],
            "challenges":     ["Waterproofing and dehumidification required",
                               "Sound insulation for shared workspace"],
            "priority_works": ["Waterproofing membrane installation",
                               "Electrical system upgrade",
                               "HVAC overhaul"],
            "estimated_cost_usd_m2": 950,
            "roi_years":    6.5,
            "co2_saving_pct": 58,
            "feasibility_score": 82,
        },
        {
            "id": 2, "title": "Boutique Heritage Hotel",
            "type": "commercial",
            "tagline": "Sleep inside history — fastest-growing luxury travel segment.",
            "description": ("The 1950s Soviet modernist architecture is an increasingly "
                            "sought-after asset for experiential travelers. Full MEP "
                            "replacement required. Target $150–300/night with 65% occupancy."),
            "benefits":       ["Unique market positioning with no direct competition",
                               "ESG credentials attract institutional investors",
                               "Heritage tourism growing 12% YoY globally"],
            "challenges":     ["Highest upfront capex of all scenarios",
                               "Complex fire suppression system retrofit"],
            "priority_works": ["Structural engineering assessment",
                               "Full MEP replacement",
                               "Fire suppression system"],
            "estimated_cost_usd_m2": 1800,
            "roi_years":    9.0,
            "co2_saving_pct": 52,
            "feasibility_score": 68,
        },
        {
            "id": 3, "title": "STEAM Education Center",
            "type": "educational",
            "tagline": "Government grants cover 30% — lowest financial risk available.",
            "description": ("University partnership provides stable 10-year institutional "
                            "revenue. Government STEAM programs provide grants covering "
                            "25–35% of costs. Phased renovation plan accepted by institutional tenants."),
            "benefits":       ["Government grants reduce net investment by 25–35%",
                               "10-year institutional lease eliminates vacancy risk",
                               "STEM talent pipeline attracts tech co-location"],
            "challenges":     ["Requires ADA accessibility upgrades",
                               "Laboratory ventilation specifications"],
            "priority_works": ["Waterproofing and dehumidification",
                               "Accessibility upgrade",
                               "Lab ventilation system"],
            "estimated_cost_usd_m2": 1100,
            "roi_years":    7.0,
            "co2_saving_pct": 61,
            "feasibility_score": 76,
        },
    ]

# ──────────────────────────────────────────────────────────────
latest  = _load_latest(BUILDING_ID)
agg     = _load_readings_agg(BUILDING_ID)

# Merge all building context
building_data = {
    **b,
    "overall_status":   latest.get("status", "UNKNOWN"),
    "degradation_score":latest.get("score",  0),
    "issues":           latest.get("issues", []),
    **agg,
}

# ══════════════════════════════════════════════════════════════
#  Generate button
# ══════════════════════════════════════════════════════════════
col_title, col_btn = st.columns([3, 1], gap="small")
with col_title:
    status = latest.get("status", "UNKNOWN")
    sc     = {"OK":"#00ff88","WARNING":"#ffaa00","CRITICAL":"#ff3355"}.get(status,"#6a8090")
    st.markdown(f"""
<div style="margin-bottom:4px">
  <span style="font-family:'Barlow Condensed',sans-serif;font-size:1.6rem;
               font-weight:800;letter-spacing:3px;color:#c8d8e8">
    ADAPTATION SCENARIOS
  </span>
  <span style="font-size:.7rem;color:{sc};margin-left:12px;
               font-family:'JetBrains Mono',monospace">
    BUILDING STATUS: {status}
  </span>
</div>
<div style="font-size:.75rem;color:#3a5060">
  AI-generated via Gemini 1.5 + architectural knowledge base
</div>""", unsafe_allow_html=True)

with col_btn:
    gen_clicked = st.button(
        "⚡ GENERATE SCENARIOS",
        type="primary",
        use_container_width=True,
        disabled=not has_perm("scan"),
    )
    if not has_perm("scan"):
        st.caption("Viewer role — read only")

if gen_clicked:
    with st.spinner("Analysing building data via Gemini + RAG..."):
        _call_strategist.clear()
        bd_json = json.dumps(building_data, default=str)
        result = _call_strategist(
            BUILDING_ID, bd_json, use_cache=False, force_fb=force_fb
        )
        if result is None:
            st.warning("LLM error — using fallback scenarios.")
            result = _demo_scenarios()
        st.session_state["scenarios"] = result
    st.success("Scenarios generated.")

# Load scenarios (or generate defaults)
if "scenarios" not in st.session_state:
    bd_json = json.dumps(building_data, default=str)
    result = _call_strategist(BUILDING_ID, bd_json, use_cache, force_fb)
    st.session_state["scenarios"] = result if result is not None else _demo_scenarios()

scenarios: list[dict] = st.session_state.get("scenarios", _demo_scenarios())
if not scenarios:
    scenarios = _demo_scenarios()

# ══════════════════════════════════════════════════════════════
#  TYPE ICONS + COLORS
# ══════════════════════════════════════════════════════════════
TYPE_ICON  = {"cultural": "🎨", "commercial": "💼",
              "educational": "🎓", "residential": "🏘", "industrial": "⚙️"}
TYPE_COLOR = {"cultural": "#7f77dd", "commercial": "#378add",
              "educational": "#1d9e75", "residential": "#ef9f27", "industrial": "#888780"}
SC_ACCENT  = ["#534ab7", "#378add", "#1d9e75"]  # per-scenario accent colours

# ══════════════════════════════════════════════════════════════
#  SECTION A — COMPARISON TABLE (side-by-side)
# ══════════════════════════════════════════════════════════════
st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:12px">
  SCENARIO COMPARISON
</div>""", unsafe_allow_html=True)

# ── Header row: scenario cards ────────────────────────────────
hdr_cols = st.columns([1] + [1] * len(scenarios), gap="small")
hdr_cols[0].markdown("""
<div style="height:80px;display:flex;align-items:center">
  <span style="font-size:.65rem;letter-spacing:1px;color:#3a5060">METRIC</span>
</div>""", unsafe_allow_html=True)

for i, sc_d in enumerate(scenarios):
    t_color = TYPE_COLOR.get(sc_d.get("type",""), "#6a8090")
    t_icon  = TYPE_ICON.get(sc_d.get("type",""), "🏛")
    accent  = SC_ACCENT[i % len(SC_ACCENT)]
    hdr_cols[i + 1].markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;
            border-top:3px solid {accent};
            padding:10px 12px;height:80px;border-radius:0 0 2px 2px">
  <div style="font-size:.65rem;color:{t_color};letter-spacing:1px;margin-bottom:2px">
    {t_icon} {sc_d.get('type','').upper()}
  </div>
  <div style="font-size:.85rem;font-weight:700;color:#c8d8e8;line-height:1.2">
    {sc_d.get('title','—')}
  </div>
</div>""", unsafe_allow_html=True)

# ── Metric rows ───────────────────────────────────────────────
METRICS = [
    ("FEASIBILITY",    "feasibility_score", "{}", "%",     True,  75, 50),
    ("COST / m²",      "estimated_cost_usd_m2", "${:,.0f}", "", False, 0, 0),
    ("ROI",            "roi_years",         "{:.1f}", " yr", False, 0, 0),
    ("CO₂ SAVING",     "co2_saving_pct",    "{}", "%",      True,  60, 40),
]

for label, key, fmt, unit, higher_better, good_thr, warn_thr in METRICS:
    row_cols = st.columns([1] + [1] * len(scenarios), gap="small")

    row_cols[0].markdown(f"""
<div style="height:52px;display:flex;align-items:center;
            border-bottom:1px solid #0d1117;padding:0 4px">
  <span style="font-size:.65rem;letter-spacing:1px;color:#6a8090">{label}</span>
</div>""", unsafe_allow_html=True)

    for i, sc_d in enumerate(scenarios):
        raw = sc_d.get(key)
        if raw is None:
            display = "—"
            val_color = "#6a8090"
        else:
            try:
                display = fmt.format(float(raw)) + unit
                fval = float(raw)
                if higher_better:
                    val_color = ("#00ff88" if fval >= good_thr
                                 else "#ffaa00" if fval >= warn_thr
                                 else "#ff3355")
                else:
                    val_color = "#00aaff"
            except Exception:
                display   = str(raw) + unit
                val_color = "#6a8090"

        # Feasibility: add mini bar
        bar_html = ""
        if key == "feasibility_score" and raw is not None:
            pct   = min(100, max(0, float(raw)))
            b_col = ("#00ff88" if pct >= 75 else "#ffaa00" if pct >= 50 else "#ff3355")
            bar_html = f"""
<div style="height:3px;background:#111820;border-radius:2px;margin-top:4px">
  <div style="width:{pct}%;height:100%;background:{b_col};border-radius:2px"></div>
</div>"""

        row_cols[i + 1].markdown(f"""
<div style="background:#0a0d12;border-bottom:1px solid #111820;
            padding:8px 12px;height:52px">
  <div style="font-size:1rem;font-weight:700;color:{val_color};
              font-family:'JetBrains Mono',monospace">{display}</div>
  {bar_html}
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION B — RADAR COMPARISON CHART
# ══════════════════════════════════════════════════════════════
if show_radar:
    st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)
    st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  MULTI-CRITERIA RADAR
</div>""", unsafe_allow_html=True)

    radar_fig = go.Figure()
    radar_cats = ["Feasibility", "CO₂ Saving", "Speed<br>(inv ROI)", "Affordability<br>(inv Cost)"]

    for i, sc_d in enumerate(scenarios):
        feas      = float(sc_d.get("feasibility_score",   0) or 0)
        co2       = float(sc_d.get("co2_saving_pct",      0) or 0)
        roi       = float(sc_d.get("roi_years",           99) or 99)
        cost      = float(sc_d.get("estimated_cost_usd_m2", 3000) or 3000)

        # Invert ROI and cost so "higher = better" on radar
        speed     = max(0, 100 - (roi / 15 * 100))       # 0yr=100, 15yr=0
        afford    = max(0, 100 - (cost / 3000 * 100))    # $0=100, $3000=0

        vals = [feas, co2, speed, afford]
        vals_closed = vals + [vals[0]]
        cats_closed = radar_cats + [radar_cats[0]]

        accent = SC_ACCENT[i % len(SC_ACCENT)]
        radar_fig.add_trace(go.Scatterpolar(
            r    = vals_closed,
            theta = cats_closed,
            mode  = "lines+markers",
            name  = sc_d.get("title", f"Scenario {i+1}")[:28],
            line  = dict(color=accent, width=2),
            marker= dict(size=6, color=accent),
            fill  = "toself",
            fillcolor = f"{accent}18",
            hovertemplate = "%{theta}: %{r:.0f}<extra>"
                            + sc_d.get("title","") + "</extra>",
        ))

    radar_fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        polar=dict(
            bgcolor="#080a0e",
            radialaxis=dict(
                range=[0, 100], gridcolor="#1e2d3d",
                tickvals=[25, 50, 75, 100],
                tickfont=dict(size=8, color="#3a5060"),
                showline=False,
            ),
            angularaxis=dict(
                tickfont=dict(size=9, color="#6a8090"),
                gridcolor="#1e2d3d",
            ),
        ),
        legend=dict(
            orientation="h", y=-0.12,
            font=dict(size=9, color="#6a8090"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=40, r=40, t=20, b=60),
        height=340,
        font=dict(family="JetBrains Mono, monospace"),
    )
    st.plotly_chart(radar_fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════
#  SECTION C — SCENARIO DETAIL CARDS
# ══════════════════════════════════════════════════════════════
st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:12px">
  SCENARIO DETAILS
</div>""", unsafe_allow_html=True)

for i, sc_d in enumerate(scenarios):
    accent  = SC_ACCENT[i % len(SC_ACCENT)]
    t_color = TYPE_COLOR.get(sc_d.get("type",""), "#6a8090")
    t_icon  = TYPE_ICON.get(sc_d.get("type",""), "🏛")
    feas    = sc_d.get("feasibility_score", 0) or 0
    feas_c  = "#00ff88" if feas >= 75 else "#ffaa00" if feas >= 50 else "#ff3355"

    exp_label = f"{t_icon}  #{i+1} — {sc_d.get('title','Scenario')}    [{sc_d.get('type','').upper()}]  ·  Feasibility: {feas}%"
    with st.expander(exp_label, expanded=show_detail or i == 0):

        top_l, top_r = st.columns([3, 1], gap="small")

        with top_l:
            # Tagline
            st.markdown(f"""
<div style="font-style:italic;color:#6a8090;font-size:.8rem;
            margin-bottom:8px;border-left:3px solid {accent};padding-left:10px">
  "{sc_d.get('tagline','')}"
</div>""", unsafe_allow_html=True)
            # Description
            st.markdown(f"""
<div style="font-size:.82rem;color:#c8d8e8;line-height:1.7;margin-bottom:12px">
  {sc_d.get('description','')}
</div>""", unsafe_allow_html=True)

        with top_r:
            # Mini metrics
            for ml, mk, mf, mu in [
                ("FEASIBILITY",  "feasibility_score",     "{}", "%"),
                ("COST / m²",    "estimated_cost_usd_m2", "${:,.0f}", ""),
                ("ROI",          "roi_years",             "{:.1f}", " yr"),
                ("CO₂ SAVED",    "co2_saving_pct",        "{}", "%"),
            ]:
                raw = sc_d.get(mk)
                try:
                    disp = mf.format(float(raw)) + mu
                except Exception:
                    disp = "—"
                vc = feas_c if ml == "FEASIBILITY" else \
                     "#1d9e75" if ml == "CO₂ SAVED" else "#00aaff"
                st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-left:2px solid {vc};
            padding:5px 8px;margin-bottom:4px">
  <div style="font-size:.55rem;letter-spacing:1px;color:#3a5060">{ml}</div>
  <div style="font-size:.9rem;font-weight:700;color:{vc};
              font-family:'JetBrains Mono',monospace">{disp}</div>
</div>""", unsafe_allow_html=True)

        # Benefits / Challenges / Priority works — 3 columns
        bc1, bc2, bc3 = st.columns(3, gap="small")

        benefits   = sc_d.get("benefits",       [])
        challenges = sc_d.get("challenges",     [])
        pw_list    = sc_d.get("priority_works", [])

        with bc1:
            st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;
            border-top:2px solid #1d9e75;padding:12px;height:100%">
  <div style="font-size:.65rem;letter-spacing:2px;color:#1d9e75;margin-bottom:8px">
    ✓ BENEFITS
  </div>""" + "".join(f"""
  <div style="font-size:.78rem;color:#c8d8e8;padding:3px 0;
              border-bottom:1px solid #111820;line-height:1.4">
    <span style="color:#1d9e75">▸</span> {b}
  </div>""" for b in benefits) + "</div>", unsafe_allow_html=True)

        with bc2:
            st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;
            border-top:2px solid #ffaa00;padding:12px;height:100%">
  <div style="font-size:.65rem;letter-spacing:2px;color:#ffaa00;margin-bottom:8px">
    △ CHALLENGES
  </div>""" + "".join(f"""
  <div style="font-size:.78rem;color:#c8d8e8;padding:3px 0;
              border-bottom:1px solid #111820;line-height:1.4">
    <span style="color:#ffaa00">▸</span> {c}
  </div>""" for c in challenges) + "</div>", unsafe_allow_html=True)

        with bc3:
            st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;
            border-top:2px solid {accent};padding:12px;height:100%">
  <div style="font-size:.65rem;letter-spacing:2px;color:{accent};margin-bottom:8px">
    ▶ PRIORITY WORKS
  </div>""" + "".join(f"""
  <div style="font-size:.78rem;color:#c8d8e8;padding:3px 0;
              border-bottom:1px solid #111820;line-height:1.4">
    <span style="color:{accent}">{j+1}.</span> {pw}
  </div>""" for j, pw in enumerate(pw_list)) + "</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION D — EXPORT SHORTCUT
# ══════════════════════════════════════════════════════════════
st.markdown("<hr style='border-color:#1e2d3d;margin:16px 0'>", unsafe_allow_html=True)

exp_col, note_col = st.columns([1, 3], gap="small")
with exp_col:
    if st.button("📄 OPEN REPORT PAGE →", use_container_width=True, type="primary"):
        st.switch_page("pages/5_Report.py")
with note_col:
    st.markdown("""
<div style="font-size:.75rem;color:#3a5060;padding-top:6px;line-height:1.6">
  Scenarios are included in the PDF report.<br>
  Navigate to <b style="color:#6a8090">Report</b> to download the full assessment document.
</div>""", unsafe_allow_html=True)
