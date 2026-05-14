import sys
from datetime import date
from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).parent / "src"))

from airwolf.ingestion.air_quality import fetch_air_quality_stations
from airwolf.ingestion.traffic import fetch_traffic_detectors
from airwolf.ingestion.weather import fetch_weather_stations

st.set_page_config(page_title="Airwolf – Station Map", layout="wide")
st.title("Airwolf – Measurement Station Map")
st.caption("Weather · Air quality · Traffic — all sources on one map")

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Controls")
    selected_date = st.date_input(
        "Reference month (weather filter)",
        value=date(2025, 12, 1),
        min_value=date(2020, 1, 1),
        max_value=date(2030, 12, 31),
    )
    st.divider()
    show_weather = st.checkbox("Weather stations", value=True)
    show_aq = st.checkbox("Air quality stations", value=True)
    show_traffic = st.checkbox("Traffic detectors", value=True)
    st.divider()
    fetch_btn = st.button("Fetch data", type="primary", use_container_width=True)

    st.divider()
    st.markdown(
        """
**Layer colours**
- 🔵 Weather stations
- 🔴 Air quality stations
- 🟢 Traffic detectors

**Data notes**
- Weather: stations active in selected month
- Air quality: all known Välisõhu seire sites (date filter not supported by API — unindexed column)
- Traffic: live detector snapshot only (no historical archive)
"""
    )


# ── Data fetching (cached per date) ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_all(date_str: str) -> dict:
    results: dict = {}
    errors: dict = {}
    for key, fn in [
        ("weather", fetch_weather_stations),
        ("aq", fetch_air_quality_stations),
        ("traffic", fetch_traffic_detectors),
    ]:
        try:
            results[key] = fn(date_str)
        except Exception as exc:
            errors[key] = str(exc)
            results[key] = None
    return {"data": results, "errors": errors}


# Auto-load on first render; re-load when button clicked.
if "last_date" not in st.session_state or fetch_btn:
    st.session_state.last_date = selected_date.isoformat()
    with st.spinner("Fetching data from all sources…"):
        st.session_state.loaded = load_all(st.session_state.last_date)

loaded = st.session_state.get("loaded", {})
data = loaded.get("data", {})
errors = loaded.get("errors", {})

for src, msg in errors.items():
    st.warning(f"**{src}**: {msg}")

# ── Metrics ───────────────────────────────────────────────────────────────────
col_w, col_a, col_t = st.columns(3)
col_w.metric(
    "Weather stations",
    len(data["weather"]) if data.get("weather") is not None else "–",
    help=f"Stations with observations in {selected_date.strftime('%B %Y')}",
)
col_a.metric(
    "Air quality stations",
    len(data["aq"]) if data.get("aq") is not None else "–",
    help="All known Välisõhu seire monitoring sites",
)
col_t.metric(
    "Traffic detectors",
    len(data["traffic"]) if data.get("traffic") is not None else "–",
    help="Active detectors in current live snapshot",
)

# ── Folium map ────────────────────────────────────────────────────────────────
m = folium.Map(
    location=[58.8, 25.5],
    zoom_start=7,
    tiles="OpenStreetMap",
    control_scale=True,
)

LAYER_CFG = [
    (
        "weather",
        show_weather,
        "Weather stations",
        "#1f77b4",
        lambda r: (
            f"<b>{r['station_name']}</b><br>"
            f"<small>{r['station_id']}</small>"
        ),
        lambda r: r.get("station_name", ""),
    ),
    (
        "aq",
        show_aq,
        "Air quality stations",
        "#d62728",
        lambda r: (
            f"<b>{r['station_name']}</b><br>"
            f"<small>{r['station_id']}</small><br>"
            f"{r.get('region', '')}"
        ),
        lambda r: r.get("station_name", ""),
    ),
    (
        "traffic",
        show_traffic,
        "Traffic detectors",
        "#2ca02c",
        lambda r: (
            f"<b>{r['site_name']}</b><br>"
            f"<small>{r['detector_id']}</small><br>"
            f"{r.get('road_name', '')}"
        ),
        lambda r: r.get("site_name", ""),
    ),
]

for key, visible, layer_name, colour, popup_fn, tooltip_fn in LAYER_CFG:
    df = data.get(key)
    if df is None or df.empty:
        continue
    group = folium.FeatureGroup(name=layer_name, show=visible)
    for _, row in df.iterrows():
        lat, lon = row["lat"], row["lon"]
        if lat != lat or lon != lon:  # NaN guard
            continue
        folium.CircleMarker(
            location=[lat, lon],
            radius=7,
            color=colour,
            fill=True,
            fill_color=colour,
            fill_opacity=0.75,
            weight=1.5,
            popup=folium.Popup(popup_fn(row), max_width=240),
            tooltip=tooltip_fn(row),
        ).add_to(group)
    group.add_to(m)

folium.LayerControl(collapsed=False).add_to(m)

st_folium(m, height=600, use_container_width=True, returned_objects=[])

# ── Raw data tables ───────────────────────────────────────────────────────────
with st.expander("Raw data tables"):
    tabs = st.tabs(["Weather", "Air quality", "Traffic"])
    for tab, key in zip(tabs, ["weather", "aq", "traffic"]):
        with tab:
            df = data.get(key)
            if df is not None and not df.empty:
                st.dataframe(df, use_container_width=True)
            else:
                st.info("No data loaded yet.")
