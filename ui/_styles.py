"""CSS injection for the FoehnCast rider console."""

from __future__ import annotations

import streamlit as st

from _theme import Palette, active


def _root_vars(pal: Palette) -> str:
    """The theme's colours as CSS variables; the sheet below reads only these."""
    r, g, b = pal.rgb(pal.ink)
    lift = "255, 255, 255" if pal.name == "light" else "168, 214, 205"
    panel_a, panel_b = (0.82, 0.94) if pal.name == "light" else (0.06, 0.10)
    return f"""
<style>
  :root {{
    --bg: {pal.plane_bottom};
    --surface: {pal.surface};
    --panel: rgba({lift}, {panel_a});
    --panel-strong: rgba({lift}, {panel_b});
    --ink: {pal.ink};
    --muted: {pal.ink_secondary};
    --accent: {pal.band};
    --accent-soft: rgba({", ".join(str(v) for v in pal.rgb(pal.band))}, 0.16);
    --accent-text: {pal.accent_text};
    --status-ink: {pal.status_ink};
    --pine: {pal.quality[2]};
    --pine-soft: rgba({", ".join(str(v) for v in pal.rgb(pal.quality[2]))}, 0.16);
    --warm: {pal.reading};
    --warm-soft: rgba({", ".join(str(v) for v in pal.rgb(pal.reading))}, 0.20);
    --line: rgba({r}, {g}, {b}, 0.18);
    --grid: {pal.grid};
    --shadow: 0 20px 60px rgba({r}, {g}, {b}, 0.14);
    --app-gradient: linear-gradient(180deg, {pal.plane_top} 0%, {pal.plane_bottom} 100%);
  }}
</style>
"""


def inject_styles() -> None:
    """Inject the theme variables, then the stylesheet written against them."""
    st.markdown(_root_vars(active()), unsafe_allow_html=True)
    st.markdown(_CSS, unsafe_allow_html=True)


_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Newsreader:opsz,wght@6..72,500;6..72,700&display=swap');

  .stApp {
    background:
      radial-gradient(circle at 12% 8%, rgba(14, 138, 134, 0.12), transparent 42%),
      radial-gradient(circle at 88% 6%, rgba(31, 94, 68, 0.10), transparent 40%),
      radial-gradient(circle at 70% 92%, rgba(255, 122, 38, 0.05), transparent 44%),
      var(--app-gradient);
    color: var(--ink);
  }

  .block-container {
    padding-top: 0.6rem;
    padding-bottom: 2rem;
  }

  /* The Streamlit chrome bar is flattened rather than removed: the sidebar's
     expand control is rendered inside the header, so display:none there leaves
     a collapsed sidebar with no way to reopen it. The header keeps zero height
     and passes clicks through; the expand button is lifted out of its box so a
     zero-height parent cannot collapse it to a zero-size target. */
  header[data-testid="stHeader"] {
    background: transparent !important;
    height: 0 !important;
    min-height: 0 !important;
    pointer-events: none;
  }
  /* stToolbar must stay displayed: the expand button is inside it, so hiding
     the toolbar hides the only way to reopen a collapsed sidebar. Hide the
     toolbar's ACTIONS instead -- deploy button and hamburger menu.
     Match on the testid alone: stMainMenu is a <span> in Streamlit 1.57, so a
     div-qualified selector silently missed it and left the menu on screen. */
  [data-testid="stDecoration"],
  [data-testid="stToolbarActions"],
  [data-testid="stAppDeployButton"],
  [data-testid="stMainMenu"] {
    display: none !important;
  }
  /* The header and toolbar are flex boxes flattened to zero height, so their
     children are centred on the top edge and render half above it. Aligning
     to the start puts them back inside the viewport. */
  div[data-testid="stToolbar"] {
    background: transparent !important;
    pointer-events: none;
  }
  header[data-testid="stHeader"],
  header[data-testid="stHeader"] > div,
  div[data-testid="stToolbar"],
  div[data-testid="stToolbar"] > div {
    align-items: flex-start !important;
  }

  [data-testid="stExpandSidebarButton"] {
    pointer-events: auto;
    z-index: 1001;
    background: var(--panel-strong) !important;
    border: 1px solid var(--line) !important;
    border-radius: 8px;
    width: 2.3rem;
    height: 2.3rem;
    margin-top: 0.45rem !important;
  }
  [data-testid="stExpandSidebarButton"] svg,
  [data-testid="stExpandSidebarButton"] span {
    color: var(--ink) !important;
    fill: var(--ink) !important;
  }

  div[data-testid="stAppViewContainer"] > .main,
  div[data-testid="stAppViewContainer"] section.main {
    padding-top: 0 !important;
  }

  /* The wrapper Streamlit 1.57 puts between stTabs and the tablist is only
     as tall as the bar, so a sticky tablist has no room to travel and
     scrolls away with the page. Flattening it makes the tall tabs container
     the containing block, and the sticky bar actually sticks. */
  div[data-testid="stTabs"] > div > div:has(> div[role="tablist"]) {
    display: contents;
  }
  div[data-testid="stTabs"] div[role="tablist"] {
    position: sticky;
    top: 0;
    z-index: 50;
    margin: -0.6rem -2rem 1.4rem -2rem;
    padding: 0.35rem 2rem 0;
    /* No background of its own: the nav is page chrome, so at rest it is the
       page. The blur alone keeps the tabs legible when content scrolls
       under them. */
    background: transparent;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--line);
    gap: 1.6rem;
  }
  /* Text tabs, not pills: the nav reads as page chrome, so a tab is ink that
     turns brand orange when selected, with the accent carried by the
     underline (a mark) rather than by a filled pill. The teal solid pill this
     replaces introduced a second accent hue and, in light mode, sat a
     near-white button on a near-white bar. */
  div[data-testid="stTabs"] div[role="tablist"] button[role="tab"],
  div[data-testid="stTabs"] div[role="tablist"] button[role="tab"] p {
    font-family: 'Manrope', sans-serif !important;
    font-weight: 800 !important;
    font-size: 1.02rem;
    letter-spacing: 0.01em;
    color: var(--muted) !important;
  }
  div[data-testid="stTabs"] div[role="tablist"] button[role="tab"] {
    padding: 0.55rem 0.1rem;
    border: none;
    border-bottom: none;
    background: transparent;
    transition: color 0.15s ease;
  }
  div[data-testid="stTabs"] div[role="tablist"] button[role="tab"]:hover,
  div[data-testid="stTabs"] div[role="tablist"] button[role="tab"]:hover p {
    background: transparent;
    color: var(--ink) !important;
  }
  div[data-testid="stTabs"] div[role="tablist"] button[role="tab"][aria-selected="true"],
  div[data-testid="stTabs"] div[role="tablist"] button[role="tab"][aria-selected="true"] p {
    color: var(--accent-text) !important;
    background: transparent !important;
    box-shadow: none;
  }
  /* The selected tab's underline: Streamlit positions this element under the
     active tab. The accent hue here is the bright reading orange -- it is a
     mark, so the 3:1 floor applies, which reading clears in both modes. */
  div[data-testid="stTabs"] div[role="tablist"] div[data-baseweb="tab-highlight"] {
    background-color: var(--warm);
    height: 3px;
    border-radius: 2px 2px 0 0;
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

  /* The unified time panel is a measuring strip, so the pointer over it is a
     fine crosshair rather than an arrow. The rules drawn inside the chart snap
     to the hour and to the hovered row; the native crosshair keeps the pointer
     itself exact in between, which is why it is replaced and not hidden --
     cursor:none would leave the reader with only the snapped rules. */
  div[class*="st-key-time_panel_select"],
  div[class*="st-key-time_panel_select"] canvas,
  div[class*="st-key-time_panel_select"] .vega-embed {
    cursor: crosshair;
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
    background: var(--panel-strong);
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

  section[data-testid="stSidebar"] div[data-testid="stSidebarContent"] {
    padding-bottom: 1.5rem;
  }

  /* Dial-as-button: each freshness dial doubles as its pipeline trigger. A
     transparent circular st.button is overlaid on the ring (real button, so
     keyboard focus and Enter work); the dial markdown shows through it. On
     hover the center age swaps to a Run label and the ring lifts. Idle
     rendering is unchanged. Selectors are sidebar-scoped so they outrank the
     generic button styling above. */
  section[data-testid="stSidebar"] div[class*="st-key-dialwrap_"] {
    position: relative;
  }
  /* The st-key-<key> class sits on the button's element container, so pull the
     container itself out of flow to overlay the ring (a 68 px circular hit
     area, centered over the dial). */
  section[data-testid="stSidebar"] div[class*="st-key-dialwrap_"]
    div[class*="st-key-run_"] {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    margin: 0 auto;
    width: 68px;
    height: 68px;
    z-index: 5;
  }
  section[data-testid="stSidebar"] div[class*="st-key-dialwrap_"]
    div[class*="st-key-run_"] div[data-testid="stButton"] {
    width: 68px;
    margin: 0 !important;
  }
  section[data-testid="stSidebar"] div[class*="st-key-dialwrap_"]
    div[class*="st-key-run_"] button {
    width: 68px !important;
    height: 68px !important;
    min-height: 68px !important;
    padding: 0 !important;
    border: none !important;
    border-radius: 50% !important;
    background: transparent !important;
    box-shadow: none !important;
    color: transparent !important;
    cursor: pointer;
  }
  section[data-testid="stSidebar"] div[class*="st-key-dialwrap_"]
    div[class*="st-key-run_"] button p {
    color: transparent !important;
  }
  section[data-testid="stSidebar"] div[class*="st-key-dialwrap_"]
    div[class*="st-key-run_"] button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* The console's comparison dials are buttons too: a transparent st.button is
     stretched across each tile so the dial itself switches the focused spot. A
     link would navigate, which reloads the page and loses the session; a widget
     click reruns the script in place. The st-key-<key> classes are the hook, so
     nothing here depends on where Streamlit puts the element. */
  div[class*="st-key-dialtile_"] {
    position: relative;
  }
  div[class*="st-key-dialtile_"] div[class*="st-key-dial_pick_"] {
    position: absolute;
    inset: 0;
    z-index: 5;
  }
  /* Whatever the widget wraps the button in -- the tooltip target when it
     carries help text -- has to fill the tile as well, or the hit area is only
     as tall as the button's own line box. */
  div[class*="st-key-dialtile_"] div[class*="st-key-dial_pick_"] div {
    width: 100% !important;
    height: 100% !important;
    margin: 0 !important;
  }
  div[class*="st-key-dialtile_"] div[class*="st-key-dial_pick_"] button {
    width: 100% !important;
    height: 100% !important;
    min-height: 0 !important;
    padding: 0 !important;
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    color: transparent !important;
    cursor: pointer;
  }
  div[class*="st-key-dialtile_"] div[class*="st-key-dial_pick_"] button p {
    color: transparent !important;
  }
  div[class*="st-key-dialtile_"] div[class*="st-key-dial_pick_"]
    button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  .fc-ring,
  .fc-ring-arc,
  .fc-disc,
  .fc-disc .fc-age,
  .fc-disc .fc-run {
    transition: filter 0.15s ease, stroke-width 0.15s ease,
      background 0.15s ease, opacity 0.15s ease;
  }
  .fc-disc .fc-age,
  .fc-disc .fc-run {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  section[data-testid="stSidebar"] .fc-disc .fc-age {
    color: #17324d !important;
  }
  section[data-testid="stSidebar"] .fc-disc .fc-run {
    opacity: 0;
    color: var(--warm) !important;
  }
  section[data-testid="stSidebar"]
    div[class*="st-key-dialwrap_"]:has(button:enabled:hover) .fc-age {
    opacity: 0;
  }
  section[data-testid="stSidebar"]
    div[class*="st-key-dialwrap_"]:has(button:enabled:hover) .fc-run {
    opacity: 1;
  }
  section[data-testid="stSidebar"]
    div[class*="st-key-dialwrap_"]:has(button:enabled:hover) .fc-disc {
    background: #fdf2e6 !important;
  }
  section[data-testid="stSidebar"]
    div[class*="st-key-dialwrap_"]:has(button:enabled:hover) .fc-ring {
    filter: brightness(1.08);
  }
  section[data-testid="stSidebar"]
    div[class*="st-key-dialwrap_"]:has(button:enabled:hover) .fc-ring-arc {
    stroke-width: 8.5;
  }

  /* A queued or running pipeline greys its dial and disables the overlay
     button, so no fresh trigger can collide with the live run. */
  section[data-testid="stSidebar"] .fc-busy {
    opacity: 0.45;
    filter: grayscale(0.6);
  }
  section[data-testid="stSidebar"] div[class*="st-key-dialwrap_"]
    div[class*="st-key-run_"] button:disabled {
    cursor: default !important;
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
     same-hue tint (low contrast); force the mode's ink so the message is
     legible on any success / info / warning / error tint. The literal ink this
     used to force was the light mode's, which is the 1.06:1 failure the
     status-role sweep was for, so it reads the role like everything else. */
  div[data-testid="stAlert"] {
    border-radius: 14px !important;
    border: 1px solid var(--line) !important;
    box-shadow: none !important;
  }
  div[data-testid="stAlert"] p,
  div[data-testid="stAlert"] span,
  div[data-testid="stAlert"] div,
  div[data-testid="stAlert"] code {
    color: var(--ink) !important;
    font-family: 'Manrope', sans-serif !important;
    font-weight: 600 !important;
  }

  /* Slider labels ship under the text floor on the light surface: the end
     labels at 4.20:1 and the value readout at 3.57:1, the latter because
     Streamlit paints it in the accent. The thumb already carries the accent,
     so the readout can wear ink and the ends the muted role. */
  div[data-testid="stSliderTickBar"],
  div[data-testid="stSliderTickBar"] p {
    color: var(--muted) !important;
  }
  div[data-testid="stSliderThumbValue"],
  div[data-testid="stSliderThumbValue"] p {
    color: var(--ink) !important;
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
