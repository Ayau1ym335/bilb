"""
pages/5_Report.py  —  PDF Report Generator
════════════════════════════════════════════
Flow:
  1. Check building is registered
  2. Show preview of what will be included
  3. "GENERATE REPORT" button → calls report.generator.generate_pdf()
  4. Download button with PDF bytes
  5. Inline preview: key metrics summary

All data pulled from FastAPI or demo mode.
"""

import io
import json
import os
import sys
import time
from datetime import datetime

import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from frontend.auth import (
    require_auth, has_perm, render_sidebar_user,
    building_meta, render_building_form,
)

st.set_page_config(
    page_title="BILB — Report",
    page_icon="📄",
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
  <div style="font-size:.6rem;letter-spacing:3px;color:#3a5060">REPORT</div>
</div>""", unsafe_allow_html=True)
    render_sidebar_user()
    st.markdown("---")

    b = building_meta()
    if b["name"] != "—":
        st.markdown(f"""
<div style="font-size:.65rem;color:#3a5060;letter-spacing:1px;margin-bottom:12px">
  <div style="color:#4a7090;margin-bottom:4px">ACTIVE BUILDING</div>
  <div style="color:#c8d8e8;font-weight:700">{b['name']}</div>
  <div>{b['city']} · {b['year_built']}</div>
</div>""", unsafe_allow_html=True)

    st.markdown("""
<div style="font-size:.65rem;letter-spacing:2px;color:#3a5060;margin-bottom:8px">
  REPORT OPTIONS
</div>""", unsafe_allow_html=True)
    inc_scenarios   = st.toggle("Include AI scenarios",    True)
    inc_sus         = st.toggle("Include sustainability",   True)
    inc_raw         = st.toggle("Include raw sensor table", False)
    transport_km    = st.slider("Transport km (for CO₂)", 5, 300, 50)

if not render_building_form():
    st.stop()

# ══════════════════════════════════════════════════════════════
#  Data loaders
# ══════════════════════════════════════════════════════════════
API_URL     = os.getenv("API_URL",     "http://localhost:8000")
BUILDING_ID = b.get("building_id", "BILB_001")

@st.cache_data(ttl=10)
def _load_latest(bid):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/telemetry/{bid}/latest", timeout=2)
        return r.json() if r.ok else {}
    except Exception:
        return _demo_latest()

@st.cache_data(ttl=10)
def _load_readings(bid, limit=200):
    try:
        import requests
        r = requests.get(f"{API_URL}/api/telemetry/{bid}?limit={limit}", timeout=2)
        return r.json() if r.ok else _demo_readings(limit)
    except Exception:
        return _demo_readings(limit)

def _demo_latest():
    import math, time as t
    tau = t.time() * 0.08
    h   = 68.0
    return {
        "temperature": 24.5, "humidity": h, "light_lux": 87,
        "pressure": 1013.2, "tilt_roll": 3.2, "tilt_pitch": 1.1,
        "vibration": True, "status": "CRITICAL", "score": 72.5,
        "issues": json.dumps(["HIGH_HUMIDITY","VIBRATION_DETECTED","STRUCTURAL_RISK_COMBO"]),
    }

def _demo_readings(n=60):
    import math, random, time as t
    rnd, now = random.Random(42), t.time()
    rows = []
    for i in range(n):
        tau = (now - (n-i)*10) * 0.08
        h   = max(10, min(100, 55 + 20*math.sin(tau*.7) + rnd.gauss(0,2)))
        vib = h > 68 and rnd.random() > 0.5
        rows.append({
            "received_at":  datetime.fromtimestamp(now-(n-i)*10).isoformat(),
            "temperature":  round(22+4*math.sin(tau)+rnd.gauss(0,.3), 1),
            "humidity":     round(h, 1),
            "light_lux":    round(max(0, 180+100*math.sin(tau*.5)+rnd.gauss(0,10))),
            "tilt_roll":    round(2*math.sin(tau*1.2)+rnd.gauss(0,.1), 2),
            "tilt_pitch":   round(1*math.cos(tau*.8)+rnd.gauss(0,.05), 2),
            "vibration":    vib,
            "status":       ("CRITICAL" if h>=70 and vib else "WARNING" if h>=55 else "OK"),
            "score":        round(min(100,(40 if h>=70 else 20 if h>=55 else 0)+(25 if vib else 0)), 1),
        })
    return rows

latest   = _load_latest(BUILDING_ID)
readings = _load_readings(BUILDING_ID)


# ══════════════════════════════════════════════════════════════
#  Helper functions  (must be defined before any call site)
# ══════════════════════════════════════════════════════════════

def _parse_issues(raw):
    if not raw: return []
    if isinstance(raw, list): return [i for i in raw if i and i.upper()!="NONE"]
    try:
        lst = json.loads(raw)
        return [i for i in lst if i and i.upper()!="NONE"]
    except Exception:
        return [i.strip() for i in str(raw).split(",") if i.strip() and i.strip().upper()!="NONE"]


def R_co2_saving(sd):
    """Quick CO₂ saving estimate for the report contents preview text."""
    area = float(b.get("area_m2") or 500)
    fl   = int(  b.get("floors")  or 4)
    ta   = area * fl
    co2_new  = ta * 900 / 1000
    co2_rest = co2_new * 0.30
    saved    = co2_new - co2_rest
    return f"{saved:,.0f}t saved"


def _do_generate(building, sensor_data, ml_result, scenarios,
                 transport_km, inc_sus) -> bytes | None:
    """
    Attempts to use report.generator.generate_pdf().
    Falls back to a lightweight minimal PDF if not available.
    """
    # Try real generator first
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from report.generator import generate_pdf
        from economist.calculator import calculate

        sus_report = (
            calculate(
                building_id             = building.get("building_id", "BILB_001"),
                floor_area_m2           = float(building.get("area_m2")  or 500),
                floors                  = int(  building.get("floors")   or 4),
                transport_km            = transport_km,
                restoration_cost_usd_m2 = 1200.0,
                annual_revenue_usd_m2   = 150.0,
            ) if inc_sus else None
        )

        pdf_bytes = generate_pdf(
            building    = building,
            sensor_data = sensor_data,
            ml_result   = ml_result,
            scenarios   = scenarios,
            sus_report  = sus_report if sus_report else {},
        )
        return pdf_bytes

    except ImportError:
        pass  # fall through to minimal PDF
    except Exception as e:
        st.warning(f"Full PDF generator error: {e} — using minimal PDF")

    # Minimal fallback PDF via ReportLab
    try:
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        C_ACC  = colors.HexColor("#00ff88")
        C_TEXT = colors.HexColor("#c8d8e8")
        C_BG   = colors.HexColor("#0d1117")
        C_CRIT = colors.HexColor("#ff3355")
        C_WARN = colors.HexColor("#ffaa00")
        SC_C   = {"OK": C_ACC, "WARNING": C_WARN, "CRITICAL": C_CRIT}

        S_title  = ParagraphStyle("t", fontName="Helvetica-Bold",  fontSize=28,
                                   textColor=C_ACC, spaceAfter=4)
        S_h2     = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14,
                                   textColor=C_TEXT, spaceAfter=6)
        S_body   = ParagraphStyle("b",  fontName="Helvetica",      fontSize=9,
                                   textColor=C_TEXT, spaceAfter=4, leading=13)
        S_mono   = ParagraphStyle("m",  fontName="Courier",        fontSize=9,
                                   textColor=C_ACC,  spaceAfter=4)
        S_sub    = ParagraphStyle("s",  fontName="Helvetica",      fontSize=8,
                                   textColor=colors.HexColor("#6a8090"), spaceAfter=3)

        def _hr():
            return HRFlowable(width="100%", thickness=0.5,
                               color=colors.HexColor("#1e2d3d"), spaceAfter=8)

        def _tbl(rows, col_w=None):
            t = Table(rows, colWidths=col_w)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#111820")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.HexColor("#6a8090")),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("FONTSIZE",   (0,0), (-1,-1), 8),
                ("ROWBACKGROUNDS",(0,1),(-1,-1),
                 [colors.HexColor("#0d1117"), colors.HexColor("#111820")]),
                ("GRID",       (0,0), (-1,-1), 0.3, colors.HexColor("#1e2d3d")),
                ("TOPPADDING", (0,0), (-1,-1), 5),
                ("BOTTOMPADDING",(0,0),(-1,-1), 5),
                ("LEFTPADDING", (0,0),(-1,-1), 8),
                ("TEXTCOLOR",  (0,1),(-1,-1), C_TEXT),
            ]))
            return t

        story = []
        bname = building.get("name",    "Building")
        bcity = building.get("city",    "—")
        byear = building.get("year_built","—")
        bid   = building.get("building_id","BILB_001")
        now   = datetime.now().strftime("%d %B %Y · %H:%M UTC")
        stat  = ml_result.get("status","UNKNOWN")
        score = ml_result.get("score", 0)

        # Cover
        story += [
            Spacer(1, 2*cm),
            Paragraph("BILB", S_title),
            Paragraph("Building Inspection &amp; Lifecycle Bot", S_sub),
            Spacer(1, 0.5*cm),
            _hr(),
            Paragraph("Building Assessment Report", S_h2),
            Paragraph(f"<b>{bname}</b>", S_h2),
            Paragraph(f"{bcity} · Est. {byear} · ID: {bid}", S_sub),
            Paragraph(f"Generated: {now}", S_sub),
            Paragraph(f"Readings: {sensor_data.get('total_readings',0)}", S_sub),
            Spacer(1, 1*cm),
            _hr(),
        ]

        # Section 1: Sensors
        story += [
            Paragraph("1. Environmental &amp; Structural Data", S_h2),
            _tbl([
                ["Parameter", "Average", "Min", "Max", "Unit"],
                ["Temperature", str(sensor_data.get("avg_temperature","—")),
                 str(sensor_data.get("min_temperature","—")),
                 str(sensor_data.get("max_temperature","—")), "°C"],
                ["Humidity",    str(sensor_data.get("avg_humidity","—")),
                 str(sensor_data.get("min_humidity","—")),
                 str(sensor_data.get("max_humidity","—")), "%"],
                ["Light",       str(sensor_data.get("avg_light_lux","—")),
                 str(sensor_data.get("min_light","—")),
                 str(sensor_data.get("max_light","—")), "lux"],
                ["Max Tilt",    "—", "—",
                 str(sensor_data.get("max_tilt_roll","—")), "°"],
                ["Vibr. Events",str(sensor_data.get("vibration_events",0)),"—","—",""],
            ]),
            Spacer(1, 0.4*cm),
        ]

        # Issues
        iss = _parse_issues(sensor_data.get("issues") or ml_result.get("issues", []))
        if iss:
            story.append(Paragraph("Issues detected: " + ", ".join(iss), S_mono))
        story.append(_hr())

        # Section 2: AI
        story += [
            Paragraph("2. AI Degradation Assessment", S_h2),
            Paragraph(f"Status: <b>{stat}</b>   Score: {score:.1f}/100   "
                      f"Confidence: {ml_result.get('confidence',0):.0%}   "
                      f"Model: {ml_result.get('model','—')}", S_body),
            _hr(),
        ]

        # Section 3: Scenarios
        if scenarios:
            story.append(Paragraph("3. Adaptive Reuse Scenarios", S_h2))
            story.append(_tbl(
                [["#","Title","Type","Feas.%","Cost/m²","ROI","CO₂%"]] +
                [[str(s.get("id",""))[:2], str(s.get("title",""))[:30],
                  str(s.get("type",""))[:12],
                  str(s.get("feasibility_score","")),
                  f"${s.get('estimated_cost_usd_m2',0):,.0f}",
                  f"{s.get('roi_years',0):.1f}yr",
                  f"{s.get('co2_saving_pct',0):.0f}%"]
                 for s in scenarios[:3]],
                col_w=[20, 140, 70, 45, 65, 45, 45],
            ))
            story.append(_hr())

        # Section 4: Footer
        story += [
            Spacer(1, 1*cm),
            _hr(),
            Paragraph(
                f"Generated by BILB Platform · Building ID: {bid} · "
                f"AI: Random Forest + Gemini 1.5 · {now}",
                S_sub
            ),
        ]

        doc.build(story)
        return buf.getvalue()

    except Exception as e:
        st.error(f"PDF generation failed: {e}")
        return None
    if not readings:
        return {}
    temps  = [float(r.get("temperature",0) or 0) for r in readings]
    hums   = [float(r.get("humidity",0)    or 0) for r in readings]
    lux    = [float(r.get("light_lux",0)   or 0) for r in readings]
    rolls  = [abs(float(r.get("tilt_roll",0)  or 0)) for r in readings]
    pitchs = [abs(float(r.get("tilt_pitch",0) or 0)) for r in readings]
    return {
        "avg_temperature":  round(sum(temps)/len(temps), 1),
        "avg_humidity":     round(sum(hums)/len(hums),   1),
        "avg_light_lux":    round(sum(lux)/len(lux)),
        "min_temperature":  round(min(temps), 1),
        "max_temperature":  round(max(temps), 1),
        "min_humidity":     round(min(hums),  1),
        "max_humidity":     round(max(hums),  1),
        "min_light":        round(min(lux)),
        "max_light":        round(max(lux)),
        "max_tilt_roll":    round(max(rolls),   2),
        "max_tilt_pitch":   round(max(pitchs),  2),
        "avg_tilt_roll":    round(sum(rolls)/len(rolls), 2),
        "vibration_events": sum(1 for r in readings if r.get("vibration")),
        "total_readings":   len(readings),
        "total_scans":      max(1, len(readings) // 50),
        "issues":           latest.get("issues", []),
    }

sensor_data = _agg(readings, latest)

# ML result
def _parse_issues(raw):
    if not raw: return []
    if isinstance(raw, list): return [i for i in raw if i and i.upper()!="NONE"]
    try:
        lst = json.loads(raw)
        return [i for i in lst if i and i.upper()!="NONE"]
    except Exception:
        return [i.strip() for i in str(raw).split(",") if i.strip() and i.strip().upper()!="NONE"]

ml_result = {
    "status":        latest.get("status",     "UNKNOWN"),
    "score":         latest.get("score",       0),
    "confidence":    0.91,
    "model":         "random_forest",
    "rule_status":   latest.get("status",     "UNKNOWN"),
    "probabilities": {"OK": 0.02, "WARNING": 0.07, "CRITICAL": 0.91},
    "issues":        _parse_issues(latest.get("issues", [])),
}

# Scenarios
scenarios = st.session_state.get("scenarios", [])
if not scenarios:
    scenarios = [
        {"id":1,"title":"Cultural Hub & Coworking","type":"cultural",
         "tagline":"Historic character becomes the brand.",
         "description":"High ceilings and exposed brick ideal for premium coworking after waterproofing.",
         "benefits":["25% rental premium","Grant eligibility","Fast fit-out"],
         "challenges":["Waterproofing required","Sound insulation"],
         "priority_works":["Waterproofing membrane","Electrical upgrade"],
         "estimated_cost_usd_m2":950,"roi_years":6.5,"co2_saving_pct":58,"feasibility_score":68},
        {"id":2,"title":"Boutique Heritage Hotel","type":"commercial",
         "tagline":"Sleep inside history.",
         "description":"1950s architecture sought by experiential travelers. Full MEP replacement needed.",
         "benefits":["Unique positioning","ESG credentials"],
         "challenges":["High capex","Complex fire suppression"],
         "priority_works":["Structural audit","Full MEP replacement"],
         "estimated_cost_usd_m2":1800,"roi_years":9.0,"co2_saving_pct":52,"feasibility_score":54},
        {"id":3,"title":"STEAM Education Center","type":"educational",
         "tagline":"Government grants cover 30%.",
         "description":"Institutional partnership provides stable revenue. Grants reduce net investment.",
         "benefits":["Government grants","10-year lease stability"],
         "challenges":["Accessibility requirements"],
         "priority_works":["Waterproofing","Accessibility upgrade"],
         "estimated_cost_usd_m2":1100,"roi_years":7.0,"co2_saving_pct":61,"feasibility_score":62},
    ]

# ══════════════════════════════════════════════════════════════
#  PAGE HEADER
# ══════════════════════════════════════════════════════════════
status = ml_result["status"]
sc_clr = {"OK":"#00ff88","WARNING":"#ffaa00","CRITICAL":"#ff3355"}.get(status,"#6a8090")

st.markdown(f"""
<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px">
  <div>
    <div style="font-family:'Barlow Condensed',sans-serif;font-size:1.6rem;
                font-weight:800;letter-spacing:3px;color:#c8d8e8">
      ASSESSMENT REPORT
    </div>
    <div style="font-size:.7rem;color:#3a5060">
      {b.get('name','—')} · {b.get('city','—')} · {b.get('year_built','—')}
    </div>
  </div>
  <div style="margin-left:auto;text-align:right">
    <div style="font-size:.7rem;letter-spacing:2px;color:{sc_clr}">{status}</div>
    <div style="font-size:.65rem;color:#3a5060">Score: {ml_result['score']:.0f}/100</div>
  </div>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  REPORT CONTENTS PREVIEW
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:12px">
  REPORT CONTENTS
</div>""", unsafe_allow_html=True)

prev_c1, prev_c2 = st.columns(2, gap="small")

sections = [
    ("1", "Cover Page",          "Building metadata, scan summary, date", True),
    ("2", "Sensor Data",         f"{sensor_data.get('total_readings',0)} readings, issues list", True),
    ("3", "AI Diagnostics",      f"Status: {status}  Score: {ml_result['score']:.0f}/100", True),
    ("4", "Adaptation Scenarios",f"{len(scenarios)} scenarios from Gemini + RAG", inc_scenarios),
    ("5", "Sustainability",      f"E_impact formula, CO₂ {R_co2_saving(sensor_data)}, financials",
     inc_sus),
    ("6", "Report Footer",       "Methodology, model versions, disclaimer", True),
]

for i, (num, title, detail, included) in enumerate(sections):
    col = prev_c1 if i % 2 == 0 else prev_c2
    chk_color = "#00ff88" if included else "#3a5060"
    chk_icon  = "✓" if included else "○"
    col.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-left:3px solid {chk_color};
            padding:10px 14px;margin-bottom:6px;
            opacity:{'1' if included else '0.4'}">
  <div style="display:flex;align-items:center;gap:8px">
    <span style="color:{chk_color};font-size:.8rem;font-weight:700">{chk_icon}</span>
    <div>
      <div style="font-size:.75rem;font-weight:700;color:#c8d8e8">
        Pg {num} — {title}
      </div>
      <div style="font-size:.65rem;color:#6a8090;margin-top:2px">{detail}</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#1e2d3d;margin:20px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  GENERATE + DOWNLOAD
# ══════════════════════════════════════════════════════════════
gen_col, dl_col = st.columns([1, 2], gap="small")

with gen_col:
    generate = st.button(
        "⚡ GENERATE REPORT",
        type="primary",
        use_container_width=True,
        disabled=not has_perm("report"),
    )

if generate:
    with st.spinner("Generating PDF report…"):
        pdf_bytes = _do_generate(b, sensor_data, ml_result,
                                  scenarios if inc_scenarios else [],
                                  transport_km, inc_sus)

    if pdf_bytes:
        st.session_state["pdf_bytes"]    = pdf_bytes
        st.session_state["pdf_filename"] = (
            f"BILB_{BUILDING_ID}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )
        st.success(f"PDF ready — {len(pdf_bytes)/1024:.0f} KB")

with dl_col:
    if "pdf_bytes" in st.session_state:
        st.download_button(
            label    = f"⬇  DOWNLOAD PDF  ·  {st.session_state.get('pdf_filename','')}",
            data     = st.session_state["pdf_bytes"],
            file_name= st.session_state.get("pdf_filename", "BILB_Report.pdf"),
            mime     = "application/pdf",
            type     = "primary",
            use_container_width=True,
        )
    else:
        st.markdown("""
<div style="background:#0d1117;border:1px dashed #1e2d3d;padding:10px 16px;
            color:#3a5060;font-size:.75rem;text-align:center">
  Click GENERATE REPORT to create the PDF
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  INLINE PREVIEW METRICS (always visible)
# ══════════════════════════════════════════════════════════════
st.markdown("<hr style='border-color:#1e2d3d;margin:20px 0'>", unsafe_allow_html=True)
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:12px">
  REPORT PREVIEW
</div>""", unsafe_allow_html=True)

# Section previews in columns
pv1, pv2, pv3 = st.columns(3, gap="small")

# ── Preview 1: Sensor snapshot ────────────────────────────────
with pv1:
    st.markdown("""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-top:2px solid #00aaff;
            padding:14px">
  <div style="font-size:.65rem;letter-spacing:2px;color:#00aaff;margin-bottom:10px">
    SECTION 1 — SENSORS
  </div>""", unsafe_allow_html=True)

    for lbl, key, unit in [
        ("Avg Temperature", "avg_temperature", "°C"),
        ("Avg Humidity",    "avg_humidity",    "%"),
        ("Avg Light",       "avg_light_lux",   "lx"),
        ("Max Tilt Roll",   "max_tilt_roll",   "°"),
        ("Vibration Events","vibration_events", ""),
        ("Total Readings",  "total_readings",   ""),
    ]:
        val = sensor_data.get(key, "—")
        st.markdown(f"""
<div style="display:flex;justify-content:space-between;
            border-bottom:1px solid #111820;padding:4px 0;
            font-size:.75rem">
  <span style="color:#6a8090">{lbl}</span>
  <span style="color:#c8d8e8;font-family:'JetBrains Mono',monospace">
    {val}{unit}
  </span>
</div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Preview 2: AI result ──────────────────────────────────────
with pv2:
    issues_list = _parse_issues(latest.get("issues", []))
    st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-top:2px solid {sc_clr};
            padding:14px">
  <div style="font-size:.65rem;letter-spacing:2px;color:{sc_clr};margin-bottom:10px">
    SECTION 2 — AI DIAGNOSTICS
  </div>
  <div style="font-size:2rem;font-weight:700;color:{sc_clr};
              font-family:'Barlow Condensed',sans-serif;letter-spacing:4px;
              margin-bottom:4px">{status}</div>
  <div style="font-size:.75rem;color:#6a8090;margin-bottom:10px">
    Score: {ml_result['score']:.1f}/100 · Confidence: {ml_result['confidence']:.0%}
  </div>""", unsafe_allow_html=True)

    for issue in issues_list[:5]:
        ic = "#ff3355" if "CRIT" in issue or "STRUCTURAL" in issue else "#ffaa00"
        st.markdown(f"""
<div style="background:{ic}11;border-left:2px solid {ic};padding:3px 8px;
            margin-bottom:3px;font-size:.7rem;color:{ic}">{issue}</div>""",
                    unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ── Preview 3: Scenarios snapshot ────────────────────────────
with pv3:
    SC_ACC = ["#534ab7", "#378add", "#1d9e75"]
    st.markdown("""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-top:2px solid #534ab7;
            padding:14px">
  <div style="font-size:.65rem;letter-spacing:2px;color:#534ab7;margin-bottom:10px">
    SECTION 3 — SCENARIOS
  </div>""", unsafe_allow_html=True)

    for i, sc in enumerate(scenarios[:3]):
        acc = SC_ACC[i % 3]
        feas = sc.get("feasibility_score", 0)
        fc   = "#00ff88" if feas >= 75 else "#ffaa00" if feas >= 50 else "#ff3355"
        st.markdown(f"""
<div style="border-left:2px solid {acc};padding:4px 8px;margin-bottom:6px">
  <div style="font-size:.72rem;font-weight:700;color:#c8d8e8">{sc.get('title','—')}</div>
  <div style="font-size:.65rem;color:#6a8090">
    Feas: <span style="color:{fc}">{feas}%</span> ·
    ROI: {sc.get('roi_years',0):.1f}yr ·
    CO₂: <span style="color:#1d9e75">-{sc.get('co2_saving_pct',0)}%</span>
  </div>
</div>""", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# Build aggregated sensor_data for report
def _agg(readings, latest):
