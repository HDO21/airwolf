"""Airwolf — vahekaartidega õhukvaliteedi, ilma ja liikluse armatuurlaud."""
from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import folium
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).parent / "src"))
_DATA_DIR     = Path(__file__).parent / "data"
_STAGING      = _DATA_DIR / "staging"
_INTERMEDIATE = _DATA_DIR / "intermediate"
_MART         = _DATA_DIR / "mart"

from airwolf.clients.envir_client import EnvirClient

st.set_page_config(page_title="Airwolf", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# Study areas
# ─────────────────────────────────────────────────────────────────────────────

STUDY_AREAS: dict[str, dict] = {
    "Tallinn": {
        "bbox_wgs84": {"lat_n": 59.554594, "lon_w": 24.474231,
                       "lat_s": 59.361424, "lon_e": 25.012994},
        "bbox_3301":  {"x_min": 526818, "x_max": 557609,
                       "y_min": 6580812, "y_max": 6601992},
        "map_center": [59.437, 24.745],
        "map_zoom":   11,
        "weather_station_codes": ["AJHARK01"],
    },
    "Narva": {
        "bbox_wgs84": {"lat_n": 59.398837, "lon_w": 28.099803,
                       "lat_s": 59.342551, "lon_e": 28.211009},
        "bbox_3301":  {"x_min": 732765, "x_max": 739464,
                       "y_min": 6585793, "y_max": 6591660},
        "map_center": [59.377, 28.179],
        "map_zoom":   13,
        "weather_station_codes": ["AJNARV01"],
    },
    "Tartu": {
        "bbox_wgs84": {"lat_n": 58.426894, "lon_w": 26.455566,
                       "lat_s": 58.248549, "lon_e": 26.780029},
        "bbox_3301":  {"x_min": 643432, "x_max": 663197,
                       "y_min": 6459800, "y_max": 6478907},
        "map_center": [58.380, 26.720],
        "map_zoom":   12,
        "weather_station_codes": ["AJTART01"],
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_DATA_PERIOD = "Detsember 2025"

# Weather stations used in analysis
_WEATHER_STATION_CODES = {"AJHARK01", "AJTART01", "AJNARV01"}

# ohuseire.ee indicator IDs — stations with all indicators (Rahu/6 excluded: no PM2.5)
_AQ_INDICATOR_MAP: dict[int, str] = {1: "SO2", 3: "NO2", 6: "O3", 21: "PM10", 23: "PM25"}
_AQ_AREA_STATIONS: dict[str, list[int]] = {
    "tallinn": [5, 7],
    "narva":   [4],
    "tartu":   [8],
}
# Hardcoded from ohuseire.ee /api/station/et?type=INDICATOR (WGS84)
_AQ_STATION_META: dict[int, dict] = {
    4: {"name": "Narva",     "lat": 59.3722, "lon": 28.2007},
    5: {"name": "Liivalaia", "lat": 59.4310, "lon": 24.7605},
    7: {"name": "Õismäe",   "lat": 59.4140, "lon": 24.6497},
    8: {"name": "Tartu",     "lat": 58.3706, "lon": 26.7348},
}

_EXCLUDED_DETECTOR_IDS: set[str] = {"944ab"}  # Ülenurme — enamasti puuduvad andmed

# ── Colour palette — no colour reused across charts ────────────────────────
_C_TEMP    = "#E63946"   # chart 1 — temperatuur
_C_PREC    = "#457B9D"   # chart 1 — sademed
_C_WIND    = "#2A9D8F"   # chart 2 — tuule kiirus
_C_TRAFFIC_MEAN = "#F4A261"  # chart 3 — keskmine
_C_TRAFFIC_GREY = "#BBBBBB"  # chart 3 — üksikud detektorid
_C_SO2  = "#F4D35E"   # chart 4
_C_NO2  = "#264653"   # chart 4
_C_O3   = "#7B2D8B"   # chart 4
_C_PM10 = "#A8DADC"   # chart 4
_C_PM25 = "#BFD3C1"   # chart 4


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_station_locations() -> dict:
    """Load station/detector positions from mart dim_stations (built by run_mart.py)."""
    data: dict = {}
    errors: dict = {}

    dim_path = _MART / "dim_stations.parquet"
    if dim_path.exists():
        dim = pd.read_parquet(dim_path)
        data["weather"] = dim[dim["source"] == "weather"].rename(
            columns={"station_name": "station_name"}
        )
        data["aq"]      = dim[dim["source"] == "air_quality"].rename(
            columns={"station_name": "station_name"}
        )
        data["traffic"] = dim[dim["source"] == "traffic"].rename(
            columns={"station_id": "detector_id"}
        )
        data["traffic"] = data["traffic"][
            ~data["traffic"]["detector_id"].astype(str).isin(_EXCLUDED_DETECTOR_IDS)
        ]
    else:
        errors["stations"] = (
            "dim_stations.parquet not found — run python run_mart.py to build mart layer"
        )
        # Fallback: hardcoded AQ metadata so the map still shows something
        data["weather"]  = None
        data["aq"]       = pd.DataFrame([
            {"station_id": sid, "station_name": m["name"], "lat": m["lat"], "lon": m["lon"]}
            for sid, m in _AQ_STATION_META.items()
        ])
        data["traffic"] = None

    return {"data": data, "errors": errors}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather_timeseries(area_key: str) -> pd.DataFrame:
    _empty = pd.DataFrame(
        columns=["station_id", "station_name", "obs_time",
                 "temperature_c", "wind_speed_ms", "wind_direction_deg", "precip_mm"]
    )
    path = _MART / "mart_weather.parquet"
    if not path.exists():
        return _empty
    df = pd.read_parquet(path)
    df = df[df["area"] == area_key.lower()].copy()
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    df = df[df["obs_time"].between("2025-12-01", "2025-12-31 23:59:59")].copy()
    return df if not df.empty else _empty


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_aq_timeseries(area_key: str) -> pd.DataFrame:
    _empty = pd.DataFrame(
        columns=["station_id", "obs_time", "SO2", "O3", "NO2", "PM10", "PM25"]
    )
    path = _MART / "mart_aq.parquet"
    if not path.exists():
        return _empty
    df = pd.read_parquet(path)
    df = df[df["area"] == area_key.lower()].copy()
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    df = df[df["obs_time"].between("2025-12-01", "2025-12-31 23:59:59")].copy()
    if df.empty:
        return _empty

    # Average across stations so each pollutant draws one smooth line per area
    averaged = df.groupby("obs_time", as_index=False)[
        ["SO2", "O3", "NO2", "PM10", "PM25"]
    ].mean()
    averaged["station_id"] = area_key
    return averaged[["station_id", "obs_time", "SO2", "O3", "NO2", "PM10", "PM25"]]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_traffic_timeseries(area_key: str) -> pd.DataFrame:
    _empty = pd.DataFrame(
        columns=["obs_time", "detector_id", "site_name", "total_flow"]
    )
    path = _MART / "mart_traffic.parquet"
    if not path.exists():
        return _empty
    df = pd.read_parquet(path)
    df = df[df["area"] == area_key.lower()].copy()
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    df = df[df["obs_time"].between("2025-12-01", "2025-12-31 23:59:59")].copy()
    if df.empty:
        return _empty

    df = df[~df["detector_id"].astype(str).isin(_EXCLUDED_DETECTOR_IDS)].copy()
    df["total_flow"] = pd.to_numeric(df["total_flow"], errors="coerce")

    # Exclude (detector, day) pairs where all hours are zero or null
    df["_date"] = df["obs_time"].dt.date
    has_flow = df.groupby(["detector_id", "_date"])["total_flow"].transform(
        lambda x: (x.fillna(0) > 0).any()
    )
    df = df[has_flow].drop(columns=["_date"]).copy()
    if "site_name" not in df.columns:
        df["site_name"] = df["detector_id"]
    return df[["obs_time", "detector_id", "site_name", "total_flow"]]


# ─────────────────────────────────────────────────────────────────────────────
# Map
# ─────────────────────────────────────────────────────────────────────────────

_MAP_LEGEND_HTML = """
<div style="position:fixed;bottom:24px;left:24px;z-index:9999;
     background:white;padding:8px 14px;border:1px solid #bbb;
     border-radius:6px;font-size:12px;line-height:2;color:#222">
  <svg width="14" height="14" style="vertical-align:middle">
    <circle cx="7" cy="7" r="6" fill="#1f77b4"/></svg>&nbsp;Ilmavaatlusjaam<br>
  <svg width="14" height="14" style="vertical-align:middle">
    <circle cx="7" cy="7" r="6" fill="#d62728"/></svg>&nbsp;Õhukvaliteedi seirejaam<br>
  <svg width="14" height="14" style="vertical-align:middle">
    <circle cx="7" cy="7" r="5" fill="#2ca02c"/></svg>&nbsp;Liikluse loenduspunkt
</div>
"""


def _bbox_filter(df: pd.DataFrame | None, bbox: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df[
        df["lat"].between(bbox["lat_s"], bbox["lat_n"])
        & df["lon"].between(bbox["lon_w"], bbox["lon_e"])
    ]


def render_map(area_key: str, station_data: dict) -> None:
    area = STUDY_AREAS[area_key]
    bbox = area["bbox_wgs84"]

    m = folium.Map(
        location=area["map_center"],
        zoom_start=area["map_zoom"],
        tiles=None,
        control_scale=True,
    )
    # Tile layer with control=False so it doesn't appear in LayerControl
    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        name="Aluskaart",
        control=False,
    ).add_to(m)

    folium.Rectangle(
        bounds=[[bbox["lat_s"], bbox["lon_w"]], [bbox["lat_n"], bbox["lon_e"]]],
        color="#555555", weight=1.5, dash_array="6 4", fill=False,
    ).add_to(m)

    # Weather layer
    raw_weather = station_data.get("weather")
    filtered_weather = _bbox_filter(raw_weather, bbox)
    if not filtered_weather.empty:
        grp = folium.FeatureGroup(name="Ilmavaatlusjaamad", show=True)
        for _, row in filtered_weather.iterrows():
            if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
                continue
            folium.CircleMarker(
                location=[float(row["lat"]), float(row["lon"])],
                radius=8, color="#1f77b4", fill=True,
                fill_color="#1f77b4", fill_opacity=0.8, weight=1.5,
                popup=folium.Popup(
                    f"<b>{row.get('station_name','')}</b><br>"
                    f"<small>{row.get('station_id','')}</small>",
                    max_width=200,
                ),
                tooltip=row.get("station_name", ""),
            ).add_to(grp)
        grp.add_to(m)

    # AQ layer
    raw_aq = station_data.get("aq")
    filtered_aq = _bbox_filter(raw_aq, bbox)
    if not filtered_aq.empty:
        grp = folium.FeatureGroup(name="Õhukvaliteedi seirejaam", show=True)
        for _, row in filtered_aq.iterrows():
            if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
                continue
            folium.CircleMarker(
                location=[float(row["lat"]), float(row["lon"])],
                radius=8, color="#d62728", fill=True,
                fill_color="#d62728", fill_opacity=0.8, weight=1.5,
                popup=folium.Popup(
                    f"<b>{row.get('station_name','')}</b><br>"
                    f"<small>{row.get('station_id','')}</small>",
                    max_width=200,
                ),
                tooltip=row.get("station_name", ""),
            ).add_to(grp)
        grp.add_to(m)

    # Traffic layer
    raw_traffic = station_data.get("traffic")
    if raw_traffic is not None and not raw_traffic.empty:
        id_col   = "detector_id"   if "detector_id"  in raw_traffic.columns else "traffic_detector_id"
        name_col = "site_name"     if "site_name"     in raw_traffic.columns else id_col
        filtered_traffic = _bbox_filter(raw_traffic, bbox)
        if not filtered_traffic.empty:
            grp = folium.FeatureGroup(name="Liikluse loenduspunkt", show=True)
            for _, row in filtered_traffic.iterrows():
                if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
                    continue
                folium.CircleMarker(
                    location=[float(row["lat"]), float(row["lon"])],
                    radius=5, color="#2ca02c", fill=True,
                    fill_color="#2ca02c", fill_opacity=0.8, weight=1.5,
                    popup=folium.Popup(
                        f"<b>{row.get(name_col,'')}</b><br>"
                        f"<small>{row.get(id_col,'')}</small>",
                        max_width=200,
                    ),
                    tooltip=row.get(name_col, ""),
                ).add_to(grp)
            grp.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    m.get_root().html.add_child(folium.Element(_MAP_LEGEND_HTML))
    st_folium(m, height=350, use_container_width=True, returned_objects=[])


# ─────────────────────────────────────────────────────────────────────────────
# Chart builders
# ─────────────────────────────────────────────────────────────────────────────

def _x_enc() -> alt.X:
    return alt.X(
        "obs_time:T",
        axis=alt.Axis(format="%d", tickCount="day", labelAngle=0, title=None),
    )


def _t_tip() -> alt.Tooltip:
    return alt.Tooltip("obs_time:T", format="%d.%m %H:%M", title="Aeg")


def make_weather_chart(df: pd.DataFrame | None) -> alt.LayerChart | None:
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["obs_time"])
    if df.empty:
        return None
    base = alt.Chart(df)
    temp = base.mark_line(color=_C_TEMP, strokeWidth=1.5).encode(
        x=_x_enc(),
        y=alt.Y("temperature_c:Q", axis=alt.Axis(title="°C")),
        tooltip=[_t_tip(), alt.Tooltip("temperature_c:Q", format=".1f", title="Temperatuur °C")],
    )
    prec = base.mark_bar(color=_C_PREC, opacity=0.6).encode(
        x=_x_enc(),
        y=alt.Y("precip_mm:Q", axis=alt.Axis(title="mm")),
        tooltip=[_t_tip(), alt.Tooltip("precip_mm:Q", format=".1f", title="Sademed mm")],
    )
    return (
        alt.layer(temp, prec)
        .resolve_scale(y="independent")
        .properties(title="Temperatuur (°C) & Sademed (mm)", height=180)
    )


def make_wind_chart(df: pd.DataFrame | None) -> alt.Chart | None:
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["obs_time"])
    if df.empty:
        return None
    return (
        alt.Chart(df)
        .mark_line(color=_C_WIND, strokeWidth=1.5)
        .encode(
            x=_x_enc(),
            y=alt.Y("wind_speed_ms:Q", axis=alt.Axis(title="m/s")),
            tooltip=[_t_tip(),
                     alt.Tooltip("wind_speed_ms:Q", format=".1f", title="Tuul (m/s)")],
        )
        .properties(title="Tuule kiirus (m/s)", height=130)
    )


def make_traffic_chart(df: pd.DataFrame | None) -> alt.Chart | None:
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["obs_time"])
    if df.empty:
        return None

    # Aggregate per (time, detector) — lanes already summed by fetch function
    hourly = df.groupby(["obs_time", "detector_id"], as_index=False)["total_flow"].sum()
    mean_df = hourly.groupby("obs_time", as_index=False)["total_flow"].mean()

    y_scale = alt.Y("total_flow:Q", axis=alt.Axis(title="sõidukit/h"))

    n_detectors = hourly["detector_id"].nunique()
    if n_detectors > 1:
        n_det = hourly["detector_id"].nunique()
        grey = (
            alt.Chart(hourly)
            .mark_line(strokeWidth=1, opacity=0.5)
            .encode(
                x=_x_enc(),
                y=y_scale,
                color=alt.Color(
                    "detector_id:N",
                    scale=alt.Scale(range=[_C_TRAFFIC_GREY] * n_det),
                    legend=None,
                ),
                tooltip=[
                    _t_tip(),
                    alt.Tooltip("site_name:N",   title="Asukoht"),
                    alt.Tooltip("total_flow:Q",  format=".0f", title="Sõidukit/h"),
                ],
            )
        )
        orange = (
            alt.Chart(mean_df)
            .mark_line(color=_C_TRAFFIC_MEAN, strokeWidth=2.5)
            .encode(
                x=_x_enc(),
                y=y_scale,
                tooltip=[_t_tip(),
                         alt.Tooltip("total_flow:Q", format=".0f", title="Keskmiselt sõidukit/h")],
            )
        )
        chart = alt.layer(grey, orange)
    else:
        chart = (
            alt.Chart(mean_df)
            .mark_line(color=_C_TRAFFIC_MEAN, strokeWidth=2)
            .encode(
                x=_x_enc(),
                y=y_scale,
                tooltip=[_t_tip(),
                         alt.Tooltip("total_flow:Q", format=".0f", title="Sõidukit/h")],
            )
        )
    return chart.properties(title="Liiklussagedus (sõidukit tunnis)", height=150)


def make_aq_chart(df: pd.DataFrame | None) -> alt.Chart | None:
    if df is None or df.empty:
        return None
    df = df.dropna(subset=["obs_time"])
    if df.empty:
        return None
    long_df = df.melt(
        id_vars=["obs_time"],
        value_vars=["SO2", "O3", "NO2", "PM10", "PM25"],
        var_name="pollutant",
        value_name="concentration",
    ).dropna(subset=["concentration"])
    if long_df.empty:
        return None
    return (
        alt.Chart(long_df)
        .mark_line(strokeWidth=1.5)
        .encode(
            x=_x_enc(),
            y=alt.Y("concentration:Q", axis=alt.Axis(title="µg/m³")),
            color=alt.Color(
                "pollutant:N",
                scale=alt.Scale(
                    domain=["SO2", "O3",  "NO2",   "PM10",  "PM25"],
                    range= [_C_SO2, _C_O3, _C_NO2, _C_PM10, _C_PM25],
                ),
                legend=alt.Legend(title="Indikaator"),
            ),
            tooltip=[
                _t_tip(),
                alt.Tooltip("pollutant:N",     title="Indikaator"),
                alt.Tooltip("concentration:Q", format=".2f", title="µg/m³"),
            ],
        )
        .properties(title="Õhukvaliteet (µg/m³)", height=180)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab renderer
# ─────────────────────────────────────────────────────────────────────────────

def _show(chart: alt.Chart | None, fallback: str = "Andmed puuduvad.") -> None:
    if chart is None:
        st.info(fallback)
    else:
        st.altair_chart(chart, use_container_width=True)


def _last_updated_str() -> str:
    marker = _STAGING / "_last_updated.txt"
    if marker.exists():
        return marker.read_text().strip()[:16].replace("T", " ")
    # Fall back to newest parquet modification time
    parquets = list(_STAGING.glob("*.parquet"))
    if parquets:
        import datetime
        ts = max(p.stat().st_mtime for p in parquets)
        return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    return "—"


def render_area_tab(area_key: str) -> None:
    loc = load_station_locations()
    for src, msg in loc["errors"].items():
        st.warning(f"Ei saanud laadida {src} jaamaandmeid: {msg}")

    render_map(area_key, loc["data"])

    # Context label
    st.caption(_DATA_PERIOD)

    # ── Weather ──────────────────────────────────────────────────────────────
    weather_df = None
    try:
        weather_df = fetch_weather_timeseries(area_key)
    except Exception as exc:
        st.warning(f"Ilmaandmete laadimine ebaõnnestus: {exc}")

    _show(make_weather_chart(weather_df))
    _show(make_wind_chart(weather_df))

    # ── Traffic ──────────────────────────────────────────────────────────────
    traffic_df = None
    try:
        traffic_df = fetch_traffic_timeseries(area_key)
    except Exception as exc:
        st.warning(f"Liiklusandmete laadimine ebaõnnestus: {exc}")

    _show(
        make_traffic_chart(traffic_df),
        fallback="Liiklusandmed puuduvad — käivita `ingest_traffic.py --mode backfill`.",
    )

    # ── Air quality ───────────────────────────────────────────────────────────
    aq_df = None
    try:
        aq_df = fetch_aq_timeseries(area_key)
    except Exception as exc:
        st.warning(f"Õhukvaliteedi andmete laadimine ebaõnnestus: {exc}")

    _show(make_aq_chart(aq_df))


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

st.caption(f"Viimati uuendatud: {_last_updated_str()}")

tabs = st.tabs(["Tallinn", "Narva", "Tartu"])
for _tab, _area_key in zip(tabs, ["Tallinn", "Narva", "Tartu"]):
    with _tab:
        render_area_tab(_area_key)
