"""
pages/4_Sustainability.py  —  Sustainability Dashboard
════════════════════════════════════════════════════════
Sections:
  A — KPI strip: CO₂ saved, money saved, trees equiv, ROI advantage
  B — CO₂ comparison: Demolition path vs Restoration (bar + breakdown)
  C — E_impact formula display with real numbers
  D — Financial waterfall: gross → tax credit → grant → net
  E — ROI comparison + NPV 10-year chart
  F — Sensitivity sliders: area, transport, revenue → live recalculation
"""

import json
import os
import sys
import time

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from frontend.auth import require_auth, render_sidebar_user, building_meta, render_building_form

st.set_page_config(
    page_title="BILB — Sustainability",
    page_icon="♻️",
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
  <div style="font-size:.6rem;letter-spacing:3px;color:#3a5060">SUSTAINABILITY</div>
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
  PARAMETERS
</div>""", unsafe_allow_html=True)

    area    = st.slider("Floor area (m²)",  100, 5000,
                        int(b.get("area_m2") or 500), step=50)
    floors  = st.slider("Floors",           1, 20,
                        int(b.get("floors")  or 4))
    transp  = st.slider("Transport distance (km)", 5, 300, 50, step=5,
                        help="Distance to demolition waste disposal site")
    revenue = st.slider("Revenue (USD/m²/yr)", 50, 500, 150, step=10,
                        help="Expected annual revenue per m² after renovation")
    rest_cost = st.slider("Restoration cost (USD/m²)", 400, 3000, 1200, step=50)

    st.markdown("---")
    st.markdown("""
<div style="font-size:.65rem;color:#3a5060;letter-spacing:1px;margin-bottom:6px">
  TAX & GRANTS
</div>""", unsafe_allow_html=True)
    tax_credit = st.slider("Tax credit %", 0, 40, 20) / 100
    grant_rate = st.slider("Grant %",      0, 40, 10) / 100

if not render_building_form():
    st.stop()

# ══════════════════════════════════════════════════════════════
#  Calculation (inline — no external dependency required)
# ══════════════════════════════════════════════════════════════
# Physical constants (mirror economist/constants.py)
K_CO2_BRICK      = 0.24
K_FUEL_TRANSPORT = 0.062
K_CO2_CONCRETE   = 0.18
DENSITY_BRICK    = 1800.0
DENSITY_CONCRETE = 2400.0
DEMOLITION_WASTE_T_PER_M2 = 1.2
WALL_THICKNESS_M = 0.51
FLOOR_HEIGHT_M   = 3.2
OPENING_FRACTION = 0.30
NEW_BUILD_CO2_KG_M2      = 900.0
RESTORATION_CO2_FRACTION = 0.30
DEMOLITION_COST_USD_M2   = 120.0
NEW_BUILD_COST_USD_M2    = 2500.0
CO2_PER_TREE_KG_YR = 22.0
CO2_PER_CAR_KM     = 0.21
HERITAGE_PREMIUM   = 0.20
DISCOUNT_RATE      = 0.10

# Try to use the real economist module if available
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from economist.calculator import calculate
    _USE_MODULE = True
except ImportError:
    _USE_MODULE = False


def _compute(area_m2, n_floors, transport_km, rev_m2, r_cost_m2, tax_cr, gr):
    """Pure-Python inline calculation — same formulas as economist/calculator.py."""
    import math

    total_area = area_m2 * n_floors

    # ── E_impact ─────────────────────────────────────────────
    side        = math.sqrt(area_m2)
    perim       = 4 * side
    wall_vol    = perim * FLOOR_HEIGHT_M * n_floors * WALL_THICKNESS_M * (1 - OPENING_FRACTION)
    mass_brick  = wall_vol * DENSITY_BRICK / 1000         # tonnes
    mass_waste  = total_area * DEMOLITION_WASTE_T_PER_M2  # tonnes (demolition debris)
    mass_conc   = total_area * 0.15 * DENSITY_CONCRETE / 1000

    co2_brick   = mass_brick * K_CO2_BRICK
    co2_transp  = mass_waste * transport_km * K_FUEL_TRANSPORT
    co2_conc    = mass_conc  * K_CO2_CONCRETE
    co2_dem_tot = co2_brick + co2_transp + co2_conc        # demolition E_impact

    # ── Restoration CO₂ ──────────────────────────────────────
    co2_new_build   = total_area * NEW_BUILD_CO2_KG_M2 / 1000
    co2_restoration = co2_new_build * RESTORATION_CO2_FRACTION
    co2_saved       = co2_new_build - co2_restoration
    co2_saving_pct  = co2_saved / co2_new_build * 100 if co2_new_build > 0 else 0

    trees   = int(co2_saved * 1000 / CO2_PER_TREE_KG_YR)
    car_km  = int(co2_saved * 1000 / CO2_PER_CAR_KM)

    # ── Financials ────────────────────────────────────────────
    dem_cost  = total_area * (DEMOLITION_COST_USD_M2 + NEW_BUILD_COST_USD_M2)
    dem_rev   = total_area * rev_m2
    dem_roi   = dem_cost / dem_rev if dem_rev > 0 else 99

    rest_gross = total_area * r_cost_m2
    rest_credit= rest_gross * tax_cr
    rest_grant = rest_gross * gr
    rest_net   = rest_gross - rest_credit - rest_grant
    rest_rev   = total_area * rev_m2 * (1 + HERITAGE_PREMIUM)
    rest_roi   = rest_net / rest_rev if rest_rev > 0 else 99

    def _npv(annual, invest, r=DISCOUNT_RATE, n=10):
        return sum(annual / (1+r)**t for t in range(1, n+1)) - invest

    dem_npv  = _npv(dem_rev,  dem_cost)
    rest_npv = _npv(rest_rev, rest_net)

    return {
        # E_impact components
        "mass_brick_t":    round(mass_brick,  2),
        "mass_waste_t":    round(mass_waste,  2),
        "co2_brick_t":     round(co2_brick,   2),
        "co2_transp_t":    round(co2_transp,  2),
        "co2_conc_t":      round(co2_conc,    2),
        "co2_dem_total_t": round(co2_dem_tot, 2),
        # Restoration CO₂
        "co2_new_build_t":   round(co2_new_build,   2),
        "co2_restoration_t": round(co2_restoration, 2),
        "co2_saved_t":       round(co2_saved,       2),
        "co2_saving_pct":    round(co2_saving_pct,  1),
        "trees_equivalent":  trees,
        "car_km_equivalent": car_km,
        # Financials
        "dem_cost":     round(dem_cost),
        "dem_rev":      round(dem_rev),
        "dem_roi":      round(dem_roi, 1),
        "dem_npv":      round(dem_npv),
        "rest_gross":   round(rest_gross),
        "rest_credit":  round(rest_credit),
        "rest_grant":   round(rest_grant),
        "rest_net":     round(rest_net),
        "rest_rev":     round(rest_rev),
        "rest_roi":     round(rest_roi, 1),
        "rest_npv":     round(rest_npv),
        "money_saved":  round(dem_cost - rest_net),
        "money_saved_pct": round((dem_cost - rest_net) / dem_cost * 100, 1) if dem_cost > 0 else 0,
        "roi_advantage":   round(dem_roi - rest_roi, 1),
        # For formula display
        "total_area_m2":   total_area,
        "transport_km":    transport_km,
    }


R = _compute(area, floors, transp, revenue, rest_cost, tax_credit, grant_rate)

# ══════════════════════════════════════════════════════════════
#  Plotly shared layout
# ══════════════════════════════════════════════════════════════
def _layout(title="", height=280, showlegend=True):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#0a0d12",
        font=dict(family="JetBrains Mono, monospace", color="#6a8090", size=10),
        margin=dict(l=0, r=0, t=28 if title else 10, b=0),
        height=height,
        title=dict(text=title, font=dict(size=9, color="#3a5060")) if title else {},
        xaxis=dict(gridcolor="#111820", zeroline=False),
        yaxis=dict(gridcolor="#111820", zeroline=False),
        showlegend=showlegend,
        legend=dict(orientation="h", y=1.12,
                    font=dict(size=9, color="#6a8090"),
                    bgcolor="rgba(0,0,0,0)"),
        bargap=0.3,
    )


C_DEM  = "#E24B4A"
C_REST = "#1D9E75"
C_INFO = "#378ADD"
C_WARN = "#EF9F27"

# ══════════════════════════════════════════════════════════════
#  SECTION A — KPI STRIP
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:1.4rem;
            font-weight:800;letter-spacing:3px;color:#c8d8e8;margin-bottom:4px">
  SUSTAINABILITY ANALYSIS
</div>
<div style="font-size:.7rem;color:#3a5060;margin-bottom:16px">
  Renovation vs Demolition · E_impact formula · Investor metrics
</div>""", unsafe_allow_html=True)

kpi_cols = st.columns(4, gap="small")
kpis = [
    (f"{R['co2_saved_t']:,.0f} t",          "CO₂ SAVED",         "#1D9E75",
     f"{R['co2_saving_pct']:.0f}% less than new build"),
    (f"${R['money_saved']/1000:,.0f}K",      "MONEY SAVED",       "#00ff88",
     f"{R['money_saved_pct']:.0f}% vs demolition path"),
    (f"{R['trees_equivalent']:,}",           "TREES EQUIV.",      "#1D9E75",
     "growing for 1 year"),
    (f"{R['roi_advantage']:.1f} yr",         "ROI FASTER",        "#00aaff",
     f"Rest: {R['rest_roi']}yr vs Dem: {R['dem_roi']}yr"),
]
for col, (val, label, color, sub) in zip(kpi_cols, kpis):
    col.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-top:2px solid {color};
            padding:14px 12px;text-align:center;border-radius:0 0 2px 2px">
  <div style="font-size:1.5rem;font-weight:700;color:{color};
              font-family:'JetBrains Mono',monospace;line-height:1.1">{val}</div>
  <div style="font-size:.6rem;letter-spacing:2px;color:#3a5060;margin:4px 0">{label}</div>
  <div style="font-size:.65rem;color:#6a8090">{sub}</div>
</div>""", unsafe_allow_html=True)

st.markdown("<hr style='border-color:#1e2d3d;margin:20px 0'>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION B — CO₂ COMPARISON CHARTS
# ══════════════════════════════════════════════════════════════
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:12px">
  CO₂ EMISSIONS ANALYSIS
</div>""", unsafe_allow_html=True)

c1, c2 = st.columns(2, gap="small")

with c1:
    # Main CO₂ bar comparison
    dem_total  = R["co2_dem_total_t"] + R["co2_new_build_t"]
    rest_total = R["co2_restoration_t"]

    fig_co2 = go.Figure()
    fig_co2.add_trace(go.Bar(
        x=["Demolition + New Build", "Restoration"],
        y=[dem_total, rest_total],
        marker_color=[C_DEM, C_REST],
        text=[f"{dem_total:,.0f} t", f"{rest_total:,.0f} t"],
        textposition="outside",
        textfont=dict(size=9, color="#c8d8e8"),
        width=0.5,
    ))
    fig_co2.add_annotation(
        x=0.5, y=(dem_total + rest_total) / 2,
        xref="paper", yref="y",
        text=f"−{R['co2_saving_pct']:.0f}%",
        font=dict(size=14, color=C_REST, family="JetBrains Mono, monospace"),
        showarrow=False,
    )
    fig_co2.update_layout(**_layout("CO₂ TOTAL EMISSIONS (t CO₂)", showlegend=False),
                          yaxis_title="Tonnes CO₂")
    st.plotly_chart(fig_co2, use_container_width=True)

with c2:
    # E_impact stacked breakdown
    fig_bd = go.Figure()
    fig_bd.add_trace(go.Bar(
        name="Brick  (M_brick × K_CO₂)",
        x=["E_impact components"],
        y=[R["co2_brick_t"]],
        marker_color=C_DEM,
        text=[f"{R['co2_brick_t']:,.1f}t"],
        textposition="inside",
        textfont=dict(size=8),
    ))
    fig_bd.add_trace(go.Bar(
        name="Concrete",
        x=["E_impact components"],
        y=[R["co2_conc_t"]],
        marker_color=C_WARN,
        text=[f"{R['co2_conc_t']:,.1f}t"],
        textposition="inside",
        textfont=dict(size=8),
    ))
    fig_bd.add_trace(go.Bar(
        name="Transport  (M_waste × km × K_fuel)",
        x=["E_impact components"],
        y=[R["co2_transp_t"]],
        marker_color=C_INFO,
        text=[f"{R['co2_transp_t']:,.1f}t"],
        textposition="inside",
        textfont=dict(size=8),
    ))
    fig_bd.update_layout(**_layout("E_IMPACT BREAKDOWN (demolition)", showlegend=True),
                         barmode="stack", yaxis_title="Tonnes CO₂")
    st.plotly_chart(fig_bd, use_container_width=True)

# ══════════════════════════════════════════════════════════════
#  SECTION C — E_IMPACT FORMULA WITH REAL NUMBERS
# ══════════════════════════════════════════════════════════════
st.markdown("<hr style='border-color:#1e2d3d;margin:20px 0'>", unsafe_allow_html=True)
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:10px">
  E_IMPACT FORMULA
</div>""", unsafe_allow_html=True)

f_col, v_col = st.columns([3, 2], gap="small")

with f_col:
    st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-left:3px solid #00ff88;
            padding:16px 20px;font-family:'JetBrains Mono',monospace;border-radius:0 2px 2px 0">

  <div style="font-size:.7rem;color:#3a5060;letter-spacing:2px;margin-bottom:10px">FORMULA</div>

  <div style="font-size:1rem;color:#c8d8e8;margin-bottom:12px">
    E_impact = <span style="color:#00ff88">(M_brick × K_CO₂)</span>
             + <span style="color:#00aaff">(M_transport × km × K_fuel)</span>
  </div>

  <div style="font-size:.8rem;color:#6a8090;line-height:2.0">
    <div>M_brick&nbsp;&nbsp;&nbsp;&nbsp; = <span style="color:#c8d8e8">{R['mass_brick_t']:,.1f} t</span>
         <span style="color:#3a5060"> (wall volume × {DENSITY_BRICK:.0f} kg/m³)</span></div>
    <div>K_CO₂&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; = <span style="color:#c8d8e8">{K_CO2_BRICK}</span>
         <span style="color:#3a5060"> kg CO₂ / kg brick (ICE DB v3)</span></div>
    <div>M_transport = <span style="color:#c8d8e8">{R['mass_waste_t']:,.1f} t</span>
         <span style="color:#3a5060"> ({DEMOLITION_WASTE_T_PER_M2} t/m² × {R['total_area_m2']:,.0f} m²)</span></div>
    <div>km&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; = <span style="color:#c8d8e8">{transp}</span>
         <span style="color:#3a5060"> km to disposal site</span></div>
    <div>K_fuel&nbsp;&nbsp;&nbsp;&nbsp; = <span style="color:#c8d8e8">{K_FUEL_TRANSPORT}</span>
         <span style="color:#3a5060"> kg CO₂ / (t · km) (Euro-VI truck)</span></div>
  </div>

  <div style="border-top:1px solid #1e2d3d;margin-top:12px;padding-top:12px;
              font-size:.9rem;color:#00ff88">
    E_impact = {R['co2_dem_total_t']:,.2f} t CO₂
    <span style="font-size:.7rem;color:#3a5060;margin-left:8px">
      (demolition + new build path)
    </span>
  </div>
</div>
""", unsafe_allow_html=True)

with v_col:
    # CO₂ equivalences visual
    trees_k   = R["trees_equivalent"] / 1000
    car_km_k  = R["car_km_equivalent"] / 1000

    equiv_fig = go.Figure()
    equiv_fig.add_trace(go.Bar(
        x=["Trees (×1000)", "Car km (×1000)"],
        y=[trees_k, car_km_k],
        marker_color=[C_REST, C_INFO],
        text=[f"{trees_k:,.1f}K", f"{car_km_k:,.0f}K"],
        textposition="outside",
        textfont=dict(size=9, color="#c8d8e8"),
        width=0.45,
    ))
    equiv_fig.update_layout(
        **_layout("CO₂ SAVINGS EQUIVALENCES", showlegend=False, height=200),
        yaxis_title="×1000",
    )
    st.plotly_chart(equiv_fig, use_container_width=True)

    st.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;border-left:3px solid #1D9E75;
            padding:10px 14px;font-size:.75rem;color:#6a8090;line-height:1.8">
  Saving <span style="color:#1D9E75;font-weight:700">{R['co2_saved_t']:,.0f} t CO₂</span> ≡<br>
  <span style="color:#c8d8e8">{R['trees_equivalent']:,}</span> trees × 1 year<br>
  <span style="color:#c8d8e8">{R['car_km_equivalent']:,}</span> km driven in avg car
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
#  SECTION D — FINANCIAL COMPARISON
# ══════════════════════════════════════════════════════════════
st.markdown("<hr style='border-color:#1e2d3d;margin:20px 0'>", unsafe_allow_html=True)
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:12px">
  FINANCIAL ANALYSIS
</div>""", unsafe_allow_html=True)

fd1, fd2, fd3 = st.columns(3, gap="small")

with fd1:
    # Investment comparison
    fig_fin = go.Figure()
    fig_fin.add_trace(go.Bar(
        x=["Demolition Path", "Restoration"],
        y=[R["dem_cost"], R["rest_net"]],
        marker_color=[C_DEM, C_REST],
        text=[f"${R['dem_cost']/1000:,.0f}K", f"${R['rest_net']/1000:,.0f}K"],
        textposition="outside",
        textfont=dict(size=9, color="#c8d8e8"),
        width=0.45,
    ))
    fig_fin.update_layout(
        **_layout("TOTAL INVESTMENT (USD)", showlegend=False),
        yaxis_title="USD",
    )
    st.plotly_chart(fig_fin, use_container_width=True)

with fd2:
    # Waterfall: restoration cost breakdown
    fig_wf = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["Gross Cost", "Tax Credit", "Grant", "Net Cost"],
        y=[R["rest_gross"], -R["rest_credit"], -R["rest_grant"], R["rest_net"]],
        text=[f"${R['rest_gross']/1000:,.0f}K",
              f"-${R['rest_credit']/1000:,.0f}K",
              f"-${R['rest_grant']/1000:,.0f}K",
              f"${R['rest_net']/1000:,.0f}K"],
        textposition="outside",
        textfont=dict(size=8, color="#c8d8e8"),
        connector=dict(line=dict(color=C_INFO, width=0.8)),
        increasing=dict(marker=dict(color=C_DEM)),
        decreasing=dict(marker=dict(color=C_REST)),
        totals=dict(marker=dict(color=C_INFO)),
    ))
    fig_wf.update_layout(
        **_layout("RESTORATION COST WATERFALL", showlegend=False),
        yaxis_title="USD",
    )
    st.plotly_chart(fig_wf, use_container_width=True)

with fd3:
    # ROI comparison
    fig_roi = go.Figure()
    fig_roi.add_trace(go.Bar(
        x=["Demolition", "Restoration"],
        y=[R["dem_roi"], R["rest_roi"]],
        marker_color=[C_DEM, C_REST],
        text=[f"{R['dem_roi']:.1f} yr", f"{R['rest_roi']:.1f} yr"],
        textposition="outside",
        textfont=dict(size=9, color="#c8d8e8"),
        width=0.45,
    ))
    fig_roi.update_layout(
        **_layout("ROI (YEARS TO BREAK EVEN)", showlegend=False),
        yaxis_title="Years",
    )
    st.plotly_chart(fig_roi, use_container_width=True)

# ── NPV 10-year line chart ────────────────────────────────────
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.7rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:8px">
  NPV PROJECTION (10 YEARS)
</div>""", unsafe_allow_html=True)

years = list(range(0, 11))

def _cum_pv(annual, invest):
    cumulative = [-invest]
    for yr in range(1, 11):
        pv = sum(annual / (1 + DISCOUNT_RATE)**t for t in range(1, yr + 1))
        cumulative.append(pv - invest)
    return cumulative

dem_cum  = _cum_pv(R["dem_rev"],  R["dem_cost"])
rest_cum = _cum_pv(R["rest_rev"], R["rest_net"])

fig_npv = go.Figure()
fig_npv.add_hline(y=0, line=dict(color="#1e2d3d", width=1))
fig_npv.add_trace(go.Scatter(
    x=years, y=[v/1000 for v in dem_cum],
    mode="lines+markers", name="Demolition path",
    line=dict(color=C_DEM, width=2),
    marker=dict(size=5, color=C_DEM),
    fill="tozeroy", fillcolor="rgba(226,75,74,.05)",
))
fig_npv.add_trace(go.Scatter(
    x=years, y=[v/1000 for v in rest_cum],
    mode="lines+markers", name="Restoration",
    line=dict(color=C_REST, width=2),
    marker=dict(size=5, color=C_REST),
    fill="tozeroy", fillcolor="rgba(29,158,117,.05)",
))
# Mark break-even points
for label, cum, color in [("Dem", dem_cum, C_DEM), ("Rest", rest_cum, C_REST)]:
    for i in range(1, len(cum)):
        if cum[i-1] < 0 <= cum[i]:
            frac = -cum[i-1] / (cum[i] - cum[i-1])
            be_yr = (i - 1) + frac
            fig_npv.add_vline(x=be_yr, line=dict(color=color, width=1, dash="dot"))
            fig_npv.add_annotation(
                x=be_yr, y=0,
                text=f"BE {be_yr:.1f}yr",
                font=dict(size=8, color=color),
                showarrow=False, yshift=10,
            )
            break

fig_npv.update_layout(
    **_layout(showlegend=True, height=220),
    xaxis_title="Year", yaxis_title="USD (thousands)",
)
# update_xaxes() merges rather than replacing, avoiding the TypeError
# that would occur from passing xaxis= twice (once in **_layout, once explicitly)
fig_npv.update_xaxes(tickvals=years, gridcolor="#111820")
st.plotly_chart(fig_npv, use_container_width=True)

# ══════════════════════════════════════════════════════════════
#  SECTION E — COMPARISON TABLE (investor-ready)
# ══════════════════════════════════════════════════════════════
st.markdown("<hr style='border-color:#1e2d3d;margin:20px 0'>", unsafe_allow_html=True)
st.markdown("""
<div style="font-family:'Barlow Condensed',sans-serif;font-size:.75rem;
            letter-spacing:3px;color:#3a5060;margin-bottom:12px">
  INVESTOR SUMMARY TABLE
</div>""", unsafe_allow_html=True)

rows = [
    ("Total investment",         f"${R['dem_cost']/1_000_000:.2f}M",   f"${R['rest_net']/1_000_000:.2f}M"),
    ("Of which: gross build cost",f"${R['dem_cost']/1_000_000:.2f}M",   f"${R['rest_gross']/1_000_000:.2f}M"),
    ("Tax credit",                "—",                                   f"-${R['rest_credit']/1000:,.0f}K"),
    ("Grant",                     "—",                                   f"-${R['rest_grant']/1000:,.0f}K"),
    ("Annual revenue (heritage)", f"${R['dem_rev']/1000:,.0f}K/yr",     f"${R['rest_rev']/1000:,.0f}K/yr"),
    ("ROI (simple payback)",      f"{R['dem_roi']:.1f} years",           f"{R['rest_roi']:.1f} years"),
    ("NPV 10-year",               f"${R['dem_npv']/1000:,.0f}K",        f"${R['rest_npv']/1000:,.0f}K"),
    ("CO₂ emissions",             f"{R['co2_dem_total_t']+R['co2_new_build_t']:,.0f} t",
                                                                         f"{R['co2_restoration_t']:,.0f} t"),
    ("CO₂ saving",                "baseline",                            f"{R['co2_saving_pct']:.0f}%"),
    ("Savings vs demolition",     "—",                                   f"${R['money_saved']/1000:,.0f}K  ({R['money_saved_pct']:.0f}%)"),
]

hdr1, hdr2, hdr3 = st.columns([2, 1.5, 1.5], gap="small")
for col, label, color in [(hdr1, "CRITERION", "#3a5060"),
                           (hdr2, "DEMOLITION PATH", C_DEM),
                           (hdr3, "RESTORATION",     C_REST)]:
    col.markdown(f"""
<div style="background:#0d1117;border:1px solid #1e2d3d;padding:8px 12px;
            font-size:.65rem;letter-spacing:2px;font-weight:700;color:{color}">
  {label}
</div>""", unsafe_allow_html=True)

for criterion, dem_val, rest_val in rows:
    is_savings = "saving" in criterion.lower() or "savings" in criterion.lower()
    r1, r2, r3 = st.columns([2, 1.5, 1.5], gap="small")

    r1.markdown(f"""
<div style="background:#0a0d12;border-bottom:1px solid #111820;
            padding:7px 12px;font-size:.75rem;color:#6a8090">{criterion}</div>""",
                unsafe_allow_html=True)
    r2.markdown(f"""
<div style="background:#0a0d12;border-bottom:1px solid #111820;
            padding:7px 12px;font-size:.78rem;font-weight:700;
            font-family:'JetBrains Mono',monospace;color:{C_DEM}">
  {dem_val}
</div>""", unsafe_allow_html=True)
    rest_c = C_REST if not "—" == rest_val else "#3a5060"
    r3.markdown(f"""
<div style="background:#0a0d12;border-bottom:1px solid #111820;
            padding:7px 12px;font-size:.78rem;font-weight:700;
            font-family:'JetBrains Mono',monospace;color:{rest_c}">
  {rest_val}
</div>""", unsafe_allow_html=True)
