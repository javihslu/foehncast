"""Small HTML demo for optional Feast-backed online features."""

from __future__ import annotations

from html import escape

from foehncast.config import get_spots

_DEFAULT_FEATURES = "wind_speed_10m, gust_factor"


def render_online_features_demo() -> str:
    """Render a lightweight HTML page for querying the online features endpoint."""
    options = "\n".join(
        (
            f'<option value="{escape(spot["id"])}">'
            f"{escape(spot['name'])} ({escape(spot['id'])})"
            "</option>"
        )
        for spot in get_spots()
    )

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>FoehnCast Online Features</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f3efe6;
        --panel: rgba(255, 252, 245, 0.92);
        --ink: #14213d;
        --muted: #5d6b82;
        --accent: #136f63;
        --accent-strong: #0b4f47;
        --line: rgba(20, 33, 61, 0.12);
      }}

      * {{ box-sizing: border-box; }}

      body {{
        margin: 0;
        font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(19, 111, 99, 0.16), transparent 30%),
          radial-gradient(circle at bottom right, rgba(245, 158, 11, 0.18), transparent 28%),
          linear-gradient(180deg, #f8f4ea, var(--bg));
        min-height: 100vh;
      }}

      main {{
        width: min(920px, calc(100vw - 32px));
        margin: 32px auto;
        padding: 28px;
        border: 1px solid var(--line);
        border-radius: 24px;
        background: var(--panel);
        box-shadow: 0 20px 60px rgba(20, 33, 61, 0.08);
        backdrop-filter: blur(14px);
      }}

      h1 {{
        margin: 0 0 8px;
        font-size: clamp(2rem, 4vw, 3rem);
        line-height: 1;
      }}

      p {{
        margin: 0 0 16px;
        color: var(--muted);
        max-width: 70ch;
      }}

      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 18px;
        margin: 24px 0;
      }}

      label {{
        display: block;
        margin-bottom: 8px;
        font-size: 0.95rem;
        font-weight: 700;
      }}

      select,
      input,
      button,
      textarea {{
        width: 100%;
        border-radius: 14px;
        border: 1px solid var(--line);
        padding: 12px 14px;
        font: inherit;
        color: var(--ink);
        background: rgba(255, 255, 255, 0.9);
      }}

      select {{ min-height: 168px; }}

      textarea {{
        min-height: 320px;
        resize: vertical;
        font-family: "SFMono-Regular", "Menlo", monospace;
        font-size: 0.92rem;
      }}

      button {{
        width: auto;
        min-width: 180px;
        border: 0;
        background: linear-gradient(135deg, var(--accent), var(--accent-strong));
        color: #fff;
        font-weight: 700;
        cursor: pointer;
      }}

      button:hover {{ filter: brightness(1.03); }}

      .row {{
        display: flex;
        gap: 12px;
        align-items: center;
        flex-wrap: wrap;
      }}

      .note {{
        font-size: 0.92rem;
        color: var(--muted);
      }}

      .status {{
        margin: 16px 0 12px;
        min-height: 24px;
        font-weight: 700;
      }}

      .status.error {{ color: #9f1239; }}
      .status.ok {{ color: var(--accent-strong); }}
    </style>
  </head>
  <body>
    <main>
      <h1>Online Feature Lookup</h1>
      <p>
        This page calls <code>/features/online</code> against the running app. It stays optional:
        the normal rank and predict flow does not depend on Feast.
      </p>

      <div class="grid">
        <div>
          <label for="spot_ids">Spots</label>
          <select id="spot_ids" multiple>{options}</select>
          <p class="note">Select one or more configured spots.</p>
        </div>
        <div>
          <label for="feature_names">Feature names</label>
          <input id="feature_names" value="{_DEFAULT_FEATURES}" />
          <p class="note">Comma-separated names. Leave empty only if you want the default feature service.</p>
        </div>
      </div>

      <div class="row">
        <button id="lookup" type="button">Fetch Online Features</button>
        <span class="note">Requires Feast setup, apply, and materialization to have already run.</span>
      </div>

      <div id="status" class="status"></div>

      <label for="result">Response</label>
      <textarea id="result" readonly></textarea>
    </main>

    <script>
      const button = document.getElementById('lookup');
      const status = document.getElementById('status');
      const result = document.getElementById('result');
      const spotIds = document.getElementById('spot_ids');
      const featureNames = document.getElementById('feature_names');

      function selectedSpots() {{
        return Array.from(spotIds.selectedOptions).map((option) => option.value);
      }}

      async function fetchFeatures() {{
        status.className = 'status';
        status.textContent = 'Loading...';
        result.value = '';

        const rawFeatureNames = featureNames.value
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean);

        const payload = {{
          spot_ids: selectedSpots(),
          feature_names: rawFeatureNames.length > 0 ? rawFeatureNames : null,
        }};

        try {{
          const response = await fetch('/features/online', {{
            method: 'POST',
            headers: {{ 'content-type': 'application/json' }},
            body: JSON.stringify(payload),
          }});
          const body = await response.json();

          if (!response.ok) {{
            status.className = 'status error';
            status.textContent = 'Request failed (' + response.status + ')';
            result.value = JSON.stringify(body, null, 2);
            return;
          }}

          status.className = 'status ok';
          status.textContent = 'Online features loaded.';
          result.value = JSON.stringify(body, null, 2);
        }} catch (error) {{
          status.className = 'status error';
          status.textContent = 'Request failed before the API responded.';
          result.value = String(error);
        }}
      }}

      button.addEventListener('click', fetchFeatures);
      result.value = JSON.stringify({{
        feature_service: null,
        returned_features: ['wind_speed_10m', 'gust_factor'],
        rows: [],
      }}, null, 2);
    </script>
  </body>
</html>
"""
