"""
app.py  —  BILB Platform Frontend Entry Point
═══════════════════════════════════════════════
Run: streamlit run app.py

Pages:
  🏠 Dashboard      — live mission control (pages/1_Dashboard.py)
  📡 Live Monitor   — sensor time series (pages/2_Monitor.py)
  🤖 AI Diagnostics — ML results (pages/3_Diagnostics.py)
  🌿 Scenarios      — adaptive reuse (pages/4_Scenarios.py)
  ♻  Sustainability — CO2 / financial (pages/5_Sustainability.py)
  📄 Report         — PDF download (pages/6_Report.py)
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st

st.set_page_config(
    page_title="BILB Platform",
    page_icon="🏛",
    layout="wide",
    initial_sidebar_state="expanded",
)

from frontend.auth import require_auth, render_sidebar_user, building_meta

require_auth()

# ── Sidebar navigation ────────────────────────────────────────
with st.sidebar:
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Barlow+Condensed:wght@700;800&display=swap');
</style>
<div style="padding:12px 0 8px;text-align:center">
  <div style="font-family:'Barlow Condensed',sans-serif;font-size:2.2rem;
              font-weight:800;letter-spacing:8px;color:#00ff88;
              text-shadow:0 0 20px rgba(0,255,136,.2)">BILB</div>
  <div style="font-size:.6rem;letter-spacing:3px;color:#3a5060">INSPECTION PLATFORM</div>
</div>
""", unsafe_allow_html=True)
    render_sidebar_user()
    st.markdown("---")

    b = building_meta()
    if b["name"] != "—":
        st.markdown(f"""
<div style="font-size:.65rem;color:#3a5060;letter-spacing:1px;margin-bottom:8px">
  <div style="color:#4a7090;margin-bottom:2px">ACTIVE BUILDING</div>
  <div style="color:#c8d8e8;font-weight:700">{b['name']}</div>
  <div>{b['city']} · {b['year_built']}</div>
</div>""", unsafe_allow_html=True)

# ── Default page content ──────────────────────────────────────
st.title("BILB Platform")
st.markdown("""
<div style="color:#6a8090;font-size:.85rem;line-height:1.8">
  Select a page from the sidebar to get started.<br>
  <span style="color:#3a5060">Start with</span>
  <span style="color:#00ff88"> 🏠 Dashboard</span>
  <span style="color:#3a5060"> to connect to the robot.</span>
</div>
""", unsafe_allow_html=True)
