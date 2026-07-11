"""CSS injection for the FoehnCast rider console."""

from __future__ import annotations

import streamlit as st


def inject_styles() -> None:
    """Inject the full CSS stylesheet into the Streamlit app."""
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Newsreader:opsz,wght@6..72,500;6..72,700&display=swap');

  :root {
    --bg: #c4d9d2;
    --panel: rgba(255, 255, 255, 0.82);
    --panel-strong: rgba(255, 255, 255, 0.94);
    --ink: #07252a;
    --muted: #3b5a5a;
    --accent: #0e8a86;
    --accent-soft: rgba(14, 138, 134, 0.16);
    --pine: #1f5e44;
    --pine-soft: rgba(31, 94, 68, 0.16);
    --warm: #ff7a26;
    --warm-soft: rgba(255, 122, 38, 0.20);
    --line: rgba(7, 37, 42, 0.18);
    --shadow: 0 20px 60px rgba(7, 37, 42, 0.14);
  }

  .stApp {
    background:
      radial-gradient(circle at 12% 8%, rgba(14, 138, 134, 0.12), transparent 42%),
      radial-gradient(circle at 88% 6%, rgba(31, 94, 68, 0.10), transparent 40%),
      radial-gradient(circle at 70% 92%, rgba(255, 122, 38, 0.05), transparent 44%),
      linear-gradient(180deg, #eaf3ef 0%, #dbe9e3 100%);
    color: var(--ink);
  }

  .block-container {
    padding-top: 0.6rem;
    padding-bottom: 2rem;
  }

  header[data-testid="stHeader"],
  div[data-testid="stDecoration"],
  div[data-testid="stToolbar"] {
    display: none !important;
  }
  div[data-testid="stAppViewContainer"] > .main,
  div[data-testid="stAppViewContainer"] section.main {
    padding-top: 0 !important;
  }

  div[data-testid="stTabs"] > div[role="tablist"] {
    position: sticky;
    top: 0;
    z-index: 50;
    margin: -0.6rem -2rem 1.4rem -2rem;
    padding: 0.55rem 2rem 0.55rem;
    background: rgba(234, 243, 239, 0.94);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--line);
    box-shadow: 0 4px 16px rgba(7, 37, 42, 0.08);
    gap: 0.5rem;
  }
  div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"],
  div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"] p {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 800 !important;
    font-size: 1.02rem;
    letter-spacing: 0.01em;
    color: var(--ink) !important;
  }
  div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"] {
    padding: 0.5rem 1.3rem;
    border-bottom: none;
    background: rgba(255, 255, 255, 0.55);
    border: 1px solid var(--line);
    border-radius: 999px;
    transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
  }
  div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"]:hover,
  div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"]:hover p {
    background: rgba(14, 138, 134, 0.12);
    color: var(--ink) !important;
  }
  div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"][aria-selected="true"],
  div[data-testid="stTabs"] > div[role="tablist"] button[role="tab"][aria-selected="true"] p {
    color: #ffffff !important;
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    box-shadow: 0 6px 16px rgba(14, 138, 134, 0.28);
  }
  div[data-testid="stTabs"] > div[role="tablist"] div[data-baseweb="tab-highlight"] {
    display: none;
  }

  button[role="tab"] {
    font-family: 'Manrope', sans-serif;
    font-weight: 700;
  }

  h1, h2, h3 {
    font-family: 'Newsreader', serif;
    color: var(--ink);
    letter-spacing: -0.02em;
  }

  p, li, div[data-testid="stMarkdownContainer"] {
    font-family: 'Manrope', sans-serif;
  }

  div[data-testid="stVegaLiteChart"],
  div[data-testid="stPlotlyChart"],
  .vega-embed,
  .vega-embed canvas,
  .vega-embed svg {
    background: transparent !important;
  }

  div[data-testid="stButton"] > button,
  div[data-testid="stFormSubmitButton"] > button {
    background: #4d5450 !important;
    background-image: none !important;
    color: #e4e2db !important;
    border: 1px solid rgba(7, 37, 42, 0.32) !important;
    border-radius: 12px !important;
    box-shadow: none !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 700 !important;
    height: 44px !important;
    min-height: 44px !important;
    padding: 0 14px !important;
    width: 100% !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    transition: background 0.15s ease, color 0.15s ease;
  }
  div[data-testid="stButton"] > button:hover,
  div[data-testid="stFormSubmitButton"] > button:hover {
    background: #404641 !important;
    color: #ffffff !important;
    border-color: rgba(7, 37, 42, 0.40) !important;
  }
  div[data-testid="stButton"] > button[kind="primary"],
  div[data-testid="stButton"] > button[data-testid="baseButton-primary"] {
    background: #404641 !important;
    color: var(--warm) !important;
    border-color: rgba(255, 122, 38, 0.55) !important;
    border-bottom-left-radius: 0 !important;
    border-bottom-right-radius: 0 !important;
    border-bottom-color: rgba(255, 122, 38, 0.55) !important;
    margin-bottom: 0 !important;
  }
  div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #363b37 !important;
    color: var(--warm) !important;
  }

  .ranked-stack {
    display: grid;
    gap: 1rem;
    width: 100%;
    margin-top: -1px;
    font-family: 'Manrope', sans-serif;
  }
  .ranked-stack .col {
    display: flex;
    flex-direction: column;
  }
  .ranked-stack .col.lead {
    text-align: right;
    color: var(--muted);
    padding-top: 8px;
  }
  .ranked-stack .col.lead .cell {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding: 6px 12px;
  }
  .ranked-stack .col.spot {
    text-align: center;
    color: var(--ink);
    padding: 8px 12px 12px;
    border: 1px solid transparent;
    border-top: none;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
  }
  .ranked-stack .col.spot.active {
    background: #404641;
    color: var(--warm);
    font-weight: 700;
    border-color: rgba(255, 122, 38, 0.55);
  }
  .ranked-stack .col.spot .cell {
    font-size: 0.9rem;
    padding: 6px 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .spot-map-shell {
    border: 1px solid var(--line);
    border-radius: 28px;
    background: var(--panel);
    box-shadow: var(--shadow);
    padding: 18px 22px 22px;
    margin-top: 1rem;
  }
  .spot-map-shell p.eyebrow {
    margin-bottom: 8px;
  }

  section[data-testid="stSidebar"] {
    background: rgba(210, 226, 220, 0.88);
    border-right: 1px solid var(--line);
    color: var(--ink);
  }

  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] span,
  section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"],
  section[data-testid="stSidebar"] .stCaption,
  section[data-testid="stSidebar"] label {
    color: var(--ink) !important;
  }

  section[data-testid="stSidebar"] div[data-testid="stButton"] > button,
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button p,
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button span,
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button div {
    color: #e4e2db !important;
  }
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover,
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover p,
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover span,
  section[data-testid="stSidebar"] div[data-testid="stButton"] > button:hover div {
    color: #ffffff !important;
  }

  section[data-testid="stSidebar"] button[data-testid="stPopoverButton"] p {
    white-space: nowrap;
  }
  section[data-testid="stSidebar"] div[data-testid="stSidebarContent"] {
    padding-bottom: 1.5rem;
  }

  div[data-testid="stMetric"] {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 16px 18px;
    box-shadow: var(--shadow);
  }

  .hero-shell,
  .feature-card,
  .profile-card {
    border: 1px solid var(--line);
    border-radius: 28px;
    background: var(--panel);
    box-shadow: var(--shadow);
  }

  .hero-shell {
    padding: 28px 30px;
    margin-bottom: 1.2rem;
  }

  .eyebrow {
    margin: 0 0 8px;
    font-family: 'Manrope', sans-serif;
    font-size: 0.85rem;
    font-weight: 800;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--accent);
  }

  .hero-title {
    margin: 0;
    font-size: clamp(2.5rem, 5vw, 4.2rem);
    line-height: 0.95;
  }

  .hero-lede {
    margin: 12px 0 0;
    max-width: 68ch;
    color: var(--muted);
    font-size: 1.02rem;
    line-height: 1.6;
  }

  .profile-card h3 {
    margin: 0 0 10px;
    font-size: 1.6rem;
  }

  .profile-card {
    padding: 18px 18px 10px;
    margin-top: 1rem;
  }

  .profile-row {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 0;
    border-top: 1px solid rgba(23, 50, 77, 0.08);
    color: var(--muted);
    font-size: 0.94rem;
  }

  .profile-row:first-of-type {
    border-top: 0;
    padding-top: 0;
  }

  .profile-row strong {
    color: var(--ink);
    font-weight: 800;
  }

  /* Readable Streamlit alerts. The default theme renders mid-tone text on a
     same-hue tint (low contrast); force dark ink so the message is legible on
     any success / info / warning / error tint. */
  div[data-testid="stAlert"] {
    border-radius: 14px !important;
    border: 1px solid rgba(7, 37, 42, 0.14) !important;
    box-shadow: none !important;
  }
  div[data-testid="stAlert"] p,
  div[data-testid="stAlert"] span,
  div[data-testid="stAlert"] div,
  div[data-testid="stAlert"] code {
    color: #07252a !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600 !important;
  }

  /* Expander: solid panel, legible header label. */
  div[data-testid="stExpander"] {
    border: 1px solid var(--line) !important;
    border-radius: 16px !important;
    background: var(--panel) !important;
    box-shadow: none !important;
  }
  div[data-testid="stExpander"] summary,
  div[data-testid="stExpander"] summary p,
  div[data-testid="stExpander"] summary span:not([data-testid="stIconMaterial"]) {
    color: var(--ink) !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 700 !important;
  }
</style>
"""
