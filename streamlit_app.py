"""Airwolf — vahekaartidega õhukvaliteedi, ilma ja liikluse armatuurlaud."""
from __future__ import annotations

import calendar
import os
from pathlib import Path

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

_DATA_DIR = Path(__file__).parent / "data"
_STAGING  = _DATA_DIR / "staging"
_MART     = _DATA_DIR / "mart"

# ─────────────────────────────────────────────────────────────────────────────
# Database connection — used when POSTGRES_HOST is set (Docker / production).
# Falls back to local parquet mart files when the DB is not available.
# ─────────────────────────────────────────────────────────────────────────────

def _db_engine():
    """Return a SQLAlchemy engine if DB env vars are present, else None."""
    host = os.getenv("POSTGRES_HOST")
    if not host:
        return None

    required = ["POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"]
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        st.error(f"Puuduvad andmebaasi keskkonnamuutujad: {', '.join(missing)}")
        return None

    try:
        from sqlalchemy import create_engine, text

        dsn = (
            f"postgresql+psycopg2://{os.environ['POSTGRES_USER']}:"
            f"{os.environ['POSTGRES_PASSWORD']}@{host}:"
            f"{os.getenv('POSTGRES_PORT', '5432')}/"
            f"{os.environ['POSTGRES_DB']}"
        )
        engine = create_engine(dsn, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:
        st.error(f"Andmebaasiga ühendamine ebaõnnestus: {exc}")
        return None


@st.cache_resource
def _get_engine():
    return _db_engine()


def _read_mart(table: str, sql: str | None = None) -> pd.DataFrame:
    """Read mart table from PostgreSQL; optionally fall back to parquet locally."""
    engine = _get_engine()
    if engine is not None:
        query = sql or f"SELECT * FROM marts.{table}"
        try:
            return pd.read_sql(query, engine)
        except Exception as exc:
            st.error(f"Tabeli marts.{table} lugemine ebaõnnestus: {exc}")
            return pd.DataFrame()

    if os.getenv("REQUIRE_POSTGRES", "0") == "1":
        st.error("POSTGRES_HOST ei ole seatud, aga REQUIRE_POSTGRES=1. Dashboard ootab andmeid andmebaasist.")
        return pd.DataFrame()

    parquet = _MART / f"{table}.parquet"
    if parquet.exists():
        return pd.read_parquet(parquet)
    return pd.DataFrame()

st.set_page_config(page_title="Õhuhunt", layout="wide")

# ─────────────────────────────────────────────────────────────────────────────
# Study areas
# ─────────────────────────────────────────────────────────────────────────────

STUDY_AREAS: dict[str, dict] = {
    "Tallinn": {
        "bbox_wgs84": {"lat_n": 59.554594, "lon_w": 24.474231,
                       "lat_s": 59.361424, "lon_e": 25.012994},
        "map_center": [59.458, 24.744],
        "map_zoom":   10,   # one step back from theoretical minimum to guarantee full bbox
    },
    "Narva": {
        "bbox_wgs84": {"lat_n": 59.398837, "lon_w": 28.099803,
                       "lat_s": 59.342551, "lon_e": 28.211009},
        "map_center": [59.371, 28.155],
        "map_zoom":   12,
    },
    "Tartu": {
        "bbox_wgs84": {"lat_n": 58.426894, "lon_w": 26.455566,
                       "lat_s": 58.248549, "lon_e": 26.780029},
        "map_center": [58.338, 26.618],
        "map_zoom":   10,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_MONTH_NAMES = {
    1: "Jaanuar", 2: "Veebruar", 3: "Märts",    4: "Aprill",
    5: "Mai",     6: "Juuni",    7: "Juuli",     8: "August",
    9: "September", 10: "Oktoober", 11: "November", 12: "Detsember",
}

_AQ_STATION_META: dict[int, dict] = {
    4: {"name": "Narva",     "area": "narva",   "lat": 59.3722, "lon": 28.2007},
    5: {"name": "Liivalaia", "area": "tallinn", "lat": 59.4310, "lon": 24.7605},
    7: {"name": "Õismäe",   "area": "tallinn", "lat": 59.4140, "lon": 24.6497},
    8: {"name": "Tartu",     "area": "tartu",   "lat": 58.3706, "lon": 26.7348},
}
_EXCLUDED_DETECTOR_IDS: set[str] = {"944ab"}
_INDICATORS = ["SO2", "O3", "NO2", "PM10", "PM25"]

_INDICATOR_FULL_NAMES: dict[str, str] = {
    "SO2":  "Vääveldioksiid (SO₂)",
    "O3":   "Osoon (O₃)",
    "NO2":  "Lämmastikdioksiid (NO₂)",
    "PM10": "Peened osakesed (PM10)",
    "PM25": "Eriti peened osakesed (PM2.5)",
}


# Colour palette
_C_TEMP         = "#E63946"   # chart 1
_C_PREC         = "#457B9D"   # chart 1
_C_WIND         = "#2A9D8F"   # chart 2
_C_TRAFFIC_MEAN = "#F4A261"   # chart 3
_C_TRAFFIC_GREY = "#BBBBBB"   # chart 3
_C_SO2          = "#F4D35E"   # chart 4
_C_NO2          = "#1E88E5"   # chart 4 — bright blue for legibility
_C_O3           = "#7B2D8B"   # chart 4
_C_PM10         = "#A8DADC"   # chart 4
_C_PM25         = "#BFD3C1"   # chart 4
_AQ_COLOURS     = {"SO2": _C_SO2, "O3": _C_O3, "NO2": _C_NO2,
                   "PM10": _C_PM10, "PM25": _C_PM25}

# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("## Õhuhunt")
st.markdown("*Andmetoru, mis kõnetab su hingetoru*")

# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_station_locations() -> dict:
    dim = _read_mart("dim_stations")
    if not dim.empty:
        traffic = dim[dim["source"] == "traffic"].rename(columns={"station_id": "detector_id"})
        traffic = traffic[~traffic["detector_id"].astype(str).isin(_EXCLUDED_DETECTOR_IDS)]
        return {
            "weather": dim[dim["source"] == "weather"].copy(),
            "aq":      dim[dim["source"] == "air_quality"].copy(),
            "traffic": traffic,
        }
    return {
        "weather": None,
        "aq": pd.DataFrame([
            {"station_id": sid, "station_name": m["name"], "lat": m["lat"], "lon": m["lon"]}
            for sid, m in _AQ_STATION_META.items()
        ]),
        "traffic": None,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_weather_timeseries(area_key: str, year: int, month: int) -> pd.DataFrame:
    _e = pd.DataFrame(columns=["station_id", "station_name", "obs_time",
                                "temperature_c", "wind_speed_ms", "precip_mm"])
    df = _read_mart("mart_weather",
                    f"SELECT * FROM marts.mart_weather"
                    f" WHERE area = '{area_key.lower()}'"
                    f" AND EXTRACT(year FROM obs_time) = {year}"
                    f" AND EXTRACT(month FROM obs_time) = {month}")
    if df.empty:
        return _e
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    df = df[df["area"] == area_key.lower()]
    df = df[(df["obs_time"].dt.year == year) & (df["obs_time"].dt.month == month)]
    return df if not df.empty else _e


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_aq_timeseries(area_key: str, year: int, month: int) -> pd.DataFrame:
    _e = pd.DataFrame(columns=["station_id", "obs_time"] + _INDICATORS)
    df = _read_mart("mart_aq",
                    f"SELECT * FROM marts.mart_aq"
                    f" WHERE area = '{area_key.lower()}'"
                    f" AND EXTRACT(year FROM obs_time) = {year}"
                    f" AND EXTRACT(month FROM obs_time) = {month}")
    if df.empty:
        return _e
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    df = df[df["area"] == area_key.lower()]
    df = df[(df["obs_time"].dt.year == year) & (df["obs_time"].dt.month == month)]
    if df.empty:
        return _e
    avg = df.groupby("obs_time", as_index=False)[_INDICATORS].mean()
    avg["station_id"] = area_key
    return avg[["station_id", "obs_time"] + _INDICATORS]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_traffic_timeseries(area_key: str, year: int, month: int) -> pd.DataFrame:
    _e = pd.DataFrame(columns=["obs_time", "detector_id", "site_name", "total_flow"])
    df = _read_mart("mart_traffic",
                    f"SELECT * FROM marts.mart_traffic"
                    f" WHERE area = '{area_key.lower()}'"
                    f" AND EXTRACT(year FROM obs_time) = {year}"
                    f" AND EXTRACT(month FROM obs_time) = {month}")
    if df.empty:
        return _e
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    df = df[df["area"] == area_key.lower()]
    df = df[(df["obs_time"].dt.year == year) & (df["obs_time"].dt.month == month)]
    if df.empty:
        return _e
    df = df[~df["detector_id"].astype(str).isin(_EXCLUDED_DETECTOR_IDS)].copy()
    df["total_flow"] = pd.to_numeric(df["total_flow"], errors="coerce")
    df["_date"] = df["obs_time"].dt.date
    has_flow = df.groupby(["detector_id", "_date"])["total_flow"].transform(
        lambda x: (x.fillna(0) > 0).any()
    )
    df = df[has_flow].drop(columns=["_date"]).copy()
    if "site_name" not in df.columns:
        df["site_name"] = df["detector_id"]
    return df[["obs_time", "detector_id", "site_name", "total_flow"]]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_joined_data(area_key: str, year: int, month: int) -> pd.DataFrame:
    df = _read_mart("mart_joined",
                    f"SELECT * FROM marts.mart_joined"
                    f" WHERE area = '{area_key.lower()}'"
                    f" AND EXTRACT(year FROM obs_time) = {year}"
                    f" AND EXTRACT(month FROM obs_time) = {month}")
    if df.empty:
        return pd.DataFrame()
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    df = df[df["area"] == area_key.lower()]
    return df[(df["obs_time"].dt.year == year) & (df["obs_time"].dt.month == month)]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_aq_all_areas(year_filter: int | None) -> pd.DataFrame:
    sql = "SELECT * FROM marts.mart_aq"
    if year_filter is not None:
        sql += f" WHERE EXTRACT(year FROM obs_time) = {year_filter}"
    df = _read_mart("mart_aq", sql)
    if df.empty:
        return pd.DataFrame()
    df["obs_time"] = pd.to_datetime(df["obs_time"], errors="coerce")
    if year_filter is not None:
        df = df[df["obs_time"].dt.year == year_filter]
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Map helpers
# ─────────────────────────────────────────────────────────────────────────────

_MAP_LEGEND_HTML = """
<div style="position:fixed;bottom:70px;left:24px;z-index:9999;
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

_ESTONIA_LEGEND_HTML = """
<div style="position:fixed;bottom:24px;left:24px;z-index:9999;
     background:white;padding:8px 14px;border:1px solid #bbb;
     border-radius:6px;font-size:12px;line-height:2;color:#222">
  <svg width="14" height="10" style="vertical-align:middle">
    <rect width="14" height="10" fill="none" stroke="#555"
          stroke-dasharray="4 2" stroke-width="1.5"/>
  </svg>&nbsp;Uuringualad
</div>
"""


def _bbox_filter(df: pd.DataFrame | None, bbox: dict) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    return df[df["lat"].between(bbox["lat_s"], bbox["lat_n"])
              & df["lon"].between(bbox["lon_w"], bbox["lon_e"])]


def _add_marker_layer(m: folium.Map, df: pd.DataFrame, colour: str,
                      radius: int, tooltip_col: str, id_col: str) -> None:
    if df is None or df.empty:
        return
    for _, row in df.iterrows():
        lat, lon = row.get("lat"), row.get("lon")
        if pd.isna(lat) or pd.isna(lon):
            continue
        folium.CircleMarker(
            location=[float(lat), float(lon)],
            radius=radius, color=colour, fill=True,
            fill_color=colour, fill_opacity=0.8, weight=1.5,
            popup=folium.Popup(
                f"<b>{row.get(tooltip_col, '')}</b><br>"
                f"<small>{row.get(id_col, '')}</small>",
                max_width=220,
            ),
            tooltip=row.get(tooltip_col, ""),
        ).add_to(m)


def render_area_map(area_key: str, station_data: dict) -> None:
    area = STUDY_AREAS[area_key]
    bbox = area["bbox_wgs84"]

    # Default tile init (no tiles=None) so Leaflet initialises properly and
    # fit_bounds works.  Unique key prevents Streamlit reusing the same iframe
    # across the three area tabs, which caused world-zoom on non-first tabs.
    m = folium.Map(
        location=area["map_center"],
        zoom_start=area["map_zoom"],
        control_scale=True,
    )

    folium.Rectangle(
        bounds=[[bbox["lat_s"], bbox["lon_w"]], [bbox["lat_n"], bbox["lon_e"]]],
        color="#555555", weight=1.5, dash_array="6 4", fill=False,
    ).add_to(m)
    _add_marker_layer(m, _bbox_filter(station_data.get("weather"), bbox),
                      "#1f77b4", 8, "station_name", "station_id")
    _add_marker_layer(m, _bbox_filter(station_data.get("aq"), bbox),
                      "#d62728", 8, "station_name", "station_id")
    traffic_df = station_data.get("traffic")
    if traffic_df is not None and not traffic_df.empty:
        id_col   = "detector_id" if "detector_id" in traffic_df.columns else "station_id"
        name_col = "site_name"   if "site_name"   in traffic_df.columns else id_col
        _add_marker_layer(m, _bbox_filter(traffic_df, bbox),
                          "#2ca02c", 5, name_col, id_col)
    m.get_root().html.add_child(folium.Element(_MAP_LEGEND_HTML))
    st_folium(m, height=350, width="100%", returned_objects=[],
              key=f"area_map_{area_key}")


def render_estonia_map() -> None:
    m = folium.Map(location=[58.65, 25.5], zoom_start=7, control_scale=True)
    _label_off = {"Tallinn": (0.06, 0), "Narva": (0.03, 0.04), "Tartu": (-0.06, 0)}
    for name, data in STUDY_AREAS.items():
        bb  = data["bbox_wgs84"]
        ctr = data["map_center"]
        off = _label_off.get(name, (0, 0))
        folium.Rectangle(
            bounds=[[bb["lat_s"], bb["lon_w"]], [bb["lat_n"], bb["lon_e"]]],
            color="#555555", weight=1.5, dash_array="6 4",
            fill=True, fill_color="#aaaaaa", fill_opacity=0.15, tooltip=name,
        ).add_to(m)
        folium.Marker(
            location=[ctr[0] + off[0], ctr[1] + off[1]],
            icon=folium.DivIcon(
                html=f'<div style="font-size:13px;font-weight:bold;color:#222;'
                     f'white-space:nowrap;text-shadow:1px 1px 2px white">{name}</div>',
                icon_size=(80, 20),
            ),
        ).add_to(m)
    m.get_root().html.add_child(folium.Element(_ESTONIA_LEGEND_HTML))
    st_folium(m, height=380, width="100%", returned_objects=[],
              key="estonia_map")


# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────

def _x_enc(year: int, month: int) -> alt.X:
    """Time x-axis with explicit day ticks; label centred within each day."""
    import datetime as _dt
    last_day = calendar.monthrange(year, month)[1]
    # Explicit tick list: exactly one tick per day of the month — prevents
    # Vega-Lite from adding a "Jan 1" tick at the right edge.
    tick_values = [_dt.datetime(year, month, d) for d in range(1, last_day + 1)]
    return alt.X(
        "obs_time:T",
        scale=alt.Scale(
            domain=[
                f"{year}-{month:02d}-01T00:00:00",
                f"{year}-{month:02d}-{last_day}T23:59:59",
            ],
            nice=False,
            clamp=True,
        ),
        axis=alt.Axis(
            values=tick_values,    # explicit ticks: no Jan 1
            format="%d",
            labelOffset=15,        # shift label rightward → visually centred in the day
            labelAngle=0,
            title=None,
            tickSize=10,
            tickWidth=2,
            gridColor="#bbbbbb",
            gridWidth=1,
        ),
    )


def _t_tip() -> alt.Tooltip:
    return alt.Tooltip("obs_time:T", format="%d.%m %H:%M", title="Aeg")


def make_weather_chart(df: pd.DataFrame | None, year: int, month: int
                       ) -> alt.LayerChart | None:
    if df is None or df.dropna(subset=["obs_time"]).empty:
        return None
    df = df.dropna(subset=["obs_time"])
    # Slim DataFrames — only the columns each mark needs
    temp_df = df[["obs_time", "temperature_c"]].copy().assign(mõõdik="Õhutemperatuur")
    prec_df = df[["obs_time", "precip_mm"]].copy()
    prec_df["precip_mm"] = prec_df["precip_mm"].clip(lower=0)   # no negative precipitation
    prec_df = prec_df.assign(mõõdik="Sademete hulk")

    cscale = alt.Scale(domain=["Õhutemperatuur", "Sademete hulk"], range=[_C_TEMP, _C_PREC])
    leg    = alt.Legend(title="", orient="bottom")
    x      = _x_enc(year, month)

    temp = (
        alt.Chart(temp_df).mark_line(strokeWidth=1.5)
        .encode(
            x=x,
            y=alt.Y("temperature_c:Q", axis=alt.Axis(title="°C")),
            color=alt.Color("mõõdik:N", scale=cscale, legend=leg),
            tooltip=[_t_tip(), alt.Tooltip("temperature_c:Q", format=".1f", title="Temperatuur °C")],
        )
    )
    prec = (
        alt.Chart(prec_df).mark_bar(opacity=0.6)
        .encode(
            x=x,
            y=alt.Y("precip_mm:Q",
                    axis=alt.Axis(title="mm"),
                    scale=alt.Scale(domainMin=0)),
            color=alt.Color("mõõdik:N", scale=cscale, legend=leg),
            tooltip=[_t_tip(), alt.Tooltip("precip_mm:Q", format=".1f", title="Sademed mm")],
        )
    )
    return (
        alt.layer(temp, prec).resolve_scale(y="independent")
        .properties(title="Temperatuur & Sademed", height=260)
    )


def make_wind_chart(df: pd.DataFrame | None, year: int, month: int
                    ) -> alt.Chart | None:
    if df is None or df.dropna(subset=["obs_time"]).empty:
        return None
    df = df.dropna(subset=["obs_time"])
    # Pass only the required columns — extra numeric columns confuse the Y scale
    wind_df = df[["obs_time", "wind_speed_ms"]].copy().assign(mõõdik="Mõõdetud tuulekiirus")
    return (
        alt.Chart(wind_df).mark_line(strokeWidth=1.5)
        .encode(
            x=_x_enc(year, month),
            y=alt.Y("wind_speed_ms:Q",
                    axis=alt.Axis(title="m/s", tickCount=5),
                    scale=alt.Scale(zero=True, nice=True)),
            color=alt.Color("mõõdik:N",
                            scale=alt.Scale(domain=["Mõõdetud tuulekiirus"],
                                            range=[_C_WIND]),
                            legend=alt.Legend(title="", orient="bottom")),
            tooltip=[_t_tip(), alt.Tooltip("wind_speed_ms:Q", format=".1f", title="Tuul (m/s)")],
        )
        .properties(title="Tuule kiirus", height=220)
    )


def make_traffic_chart(df: pd.DataFrame | None, year: int, month: int
                       ) -> alt.Chart | None:
    if df is None or df.dropna(subset=["obs_time"]).empty:
        return None
    df = df.dropna(subset=["obs_time"])
    hourly  = df.groupby(["obs_time", "detector_id", "site_name"],
                          as_index=False)["total_flow"].sum()

    # Slim DataFrame for mean layer — no extra columns
    mean_df = hourly.groupby("obs_time", as_index=False)["total_flow"].mean()
    mean_df = mean_df[["obs_time", "total_flow"]].copy()
    mean_df["mõõdik"] = "Keskmine liiklussagedus"

    y_scale = alt.Scale(zero=True, nice=True)
    y_axis  = alt.Axis(title="sõidukit/h", tickCount=5)

    mean_layer = (
        alt.Chart(mean_df).mark_line(strokeWidth=2.5)
        .encode(
            x=_x_enc(year, month),
            y=alt.Y("total_flow:Q", scale=y_scale, axis=y_axis),
            color=alt.Color("mõõdik:N",
                            scale=alt.Scale(domain=["Keskmine liiklussagedus"],
                                            range=[_C_TRAFFIC_MEAN]),
                            legend=alt.Legend(title="", orient="bottom")),
            tooltip=[_t_tip(),
                     alt.Tooltip("total_flow:Q", format=".0f", title="Keskmiselt sõidukit/h")],
        )
    )
    n_det = hourly["detector_id"].nunique()
    if n_det > 1:
        # Slim grey layer — only obs_time, total_flow, detector_id, site_name
        grey_df = hourly[["obs_time", "total_flow", "detector_id", "site_name"]].copy()
        grey_layer = (
            alt.Chart(grey_df).mark_line(strokeWidth=1, opacity=0.4)
            .encode(
                x=_x_enc(year, month),
                y=alt.Y("total_flow:Q", scale=y_scale, axis=y_axis),
                color=alt.Color("detector_id:N",
                                scale=alt.Scale(range=[_C_TRAFFIC_GREY] * n_det),
                                legend=None),
                tooltip=[_t_tip(),
                         alt.Tooltip("site_name:N", title="Asukoht"),
                         alt.Tooltip("total_flow:Q", format=".0f", title="Sõidukit/h")],
            )
        )
        chart = (
            alt.layer(grey_layer, mean_layer)
            .resolve_scale(color="independent")
        )
    else:
        chart = mean_layer

    return chart.properties(title="Liiklussagedus", height=220)


def make_aq_chart(df: pd.DataFrame | None, year: int, month: int
                  ) -> alt.Chart | None:
    if df is None or df.dropna(subset=["obs_time"]).empty:
        return None
    df = df.dropna(subset=["obs_time"])
    # Only melt the columns we need — drop station_id etc.
    cols = ["obs_time"] + [c for c in _INDICATORS if c in df.columns]
    long_df = df[cols].melt(id_vars=["obs_time"], value_vars=_INDICATORS,
                            var_name="indikaator", value_name="kontsentratsioon"
                            ).dropna(subset=["kontsentratsioon"])
    if long_df.empty:
        return None
    return (
        alt.Chart(long_df).mark_line(strokeWidth=1.5)
        .encode(
            x=_x_enc(year, month),
            y=alt.Y("kontsentratsioon:Q",
                    axis=alt.Axis(title="µg/m³", tickCount=5),
                    scale=alt.Scale(zero=True, nice=True)),
            color=alt.Color("indikaator:N",
                            scale=alt.Scale(domain=_INDICATORS,
                                            range=[_AQ_COLOURS[i] for i in _INDICATORS]),
                            legend=alt.Legend(orient="bottom", title="Indikaator")),
            tooltip=[_t_tip(),
                     alt.Tooltip("indikaator:N", title="Indikaator"),
                     alt.Tooltip("kontsentratsioon:Q", format=".2f", title="µg/m³")],
        )
        .properties(title="Õhukvaliteet", height=260)
    )


def make_scatter(df: pd.DataFrame, x_col: str, x_title: str,
                 y_col: str, y_title: str, title: str,
                 indicator: str) -> alt.Chart | None:
    if df is None or df.empty:
        return None
    plot_df = df[[x_col, y_col]].dropna()
    # Need at least 3 points to fit a line and compute a meaningful correlation
    if len(plot_df) < 3:
        return None

    r = plot_df[x_col].corr(plot_df[y_col])
    r_str = f"{r:.2f}" if pd.notna(r) else "n/a"
    title_with_r = f"{title} (r = {r_str})"

    colour = _AQ_COLOURS.get(indicator, "#888")

    dots = (
        alt.Chart(plot_df).mark_circle(size=25, opacity=0.45, color=colour)
        .encode(
            x=alt.X(f"{x_col}:Q", title=x_title),
            y=alt.Y(f"{y_col}:Q", title=y_title),
            tooltip=[alt.Tooltip(f"{x_col}:Q", format=".2f", title=x_title),
                     alt.Tooltip(f"{y_col}:Q", format=".2f", title=y_title)],
        )
    )

    trend = (
        alt.Chart(plot_df)
        .mark_line(color="#8B0000", opacity=0.85, strokeWidth=2, strokeDash=[6, 3])
        .transform_regression(x_col, y_col)
        .encode(
            x=alt.X(f"{x_col}:Q"),
            y=alt.Y(f"{y_col}:Q"),
        )
    )

    return (
        alt.layer(dots, trend)
        .properties(title=title_with_r, height=260)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Shared renderer helpers
# ─────────────────────────────────────────────────────────────────────────────

def _show(chart: alt.Chart | None, fallback: str = "Andmed puuduvad.") -> None:
    if chart is None:
        st.info(fallback)
    else:
        st.altair_chart(chart, width="stretch")


def _last_updated_str() -> str:
    import datetime
    for marker in [
        _MART    / "_last_updated.txt",   # written by run_mart.py; tracked in git
        _STAGING / "_last_updated.txt",   # written by run_pipeline.py
    ]:
        if marker.exists():
            return marker.read_text().strip()[:16].replace("T", " ")
    parquets = list(_MART.glob("*.parquet"))
    if parquets:
        ts = max(p.stat().st_mtime for p in parquets)
        return datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
    return "—"


def _area_filter(area_key: str) -> tuple[int, int]:
    """Render year/month selectors for a tab; returns (year, month)."""
    year_key  = f"year_{area_key}"
    month_key = f"month_{area_key}"

    if year_key  not in st.session_state: st.session_state[year_key]  = 2025
    if month_key not in st.session_state: st.session_state[month_key] = 12

    def _reset_month() -> None:
        st.session_state[month_key] = 1

    col_y, col_m, _ = st.columns([1, 2, 6])
    with col_y:
        st.selectbox("Aasta", [2025, 2026], key=year_key,
                     on_change=_reset_month)
    with col_m:
        st.selectbox("Kuu", list(range(1, 13)),
                     format_func=lambda m: _MONTH_NAMES[m],
                     key=month_key)

    return st.session_state[year_key], st.session_state[month_key]


# ─────────────────────────────────────────────────────────────────────────────
# Area tab renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_area_tab(area_key: str) -> None:
    station_data = load_station_locations()
    render_area_map(area_key, station_data)

    year, month = _area_filter(area_key)
    st.caption(f"{_MONTH_NAMES[month]} {year}")

    # ── Mõõdistus- ja vaatlusandmed ──────────────────────────────────────────
    st.subheader("Mõõdistus- ja vaatlusandmed")

    weather_df = None
    try:
        weather_df = fetch_weather_timeseries(area_key, year, month)
    except Exception as exc:
        st.warning(f"Ilmaandmete laadimine ebaõnnestus: {exc}")

    _show(make_weather_chart(weather_df, year, month))
    _show(make_wind_chart(weather_df, year, month))
    st.markdown("")   # breathing room between wind and traffic charts

    traffic_df = None
    try:
        traffic_df = fetch_traffic_timeseries(area_key, year, month)
    except Exception as exc:
        st.warning(f"Liiklusandmete laadimine ebaõnnestus: {exc}")

    _show(make_traffic_chart(traffic_df, year, month),
          fallback="Liiklusandmed puuduvad — käivita `ingest_traffic.py --mode backfill`.")

    aq_df = None
    try:
        aq_df = fetch_aq_timeseries(area_key, year, month)
    except Exception as exc:
        st.warning(f"Õhukvaliteedi andmete laadimine ebaõnnestus: {exc}")

    _show(make_aq_chart(aq_df, year, month))

    # ── Analüütika ────────────────────────────────────────────────────────────
    st.subheader("Analüütika")

    sel_ind = st.selectbox("Indikaator", _INDICATORS, index=0, key=f"ind_{area_key}")

    try:
        joined = fetch_joined_data(area_key, year, month)
    except Exception as exc:
        st.warning(f"Andmete laadimine ebaõnnestus: {exc}")
        joined = pd.DataFrame()

    ind_label = f"{sel_ind} (µg/m³)"
    scatter_defs = [
        ("total_flow",    "Liiklussagedus (sõidukit/h)", f"{sel_ind} vs liiklussagedus"),
        ("temperature_c", "Temperatuur (°C)",             f"{sel_ind} vs temperatuur"),
        ("precip_mm",     "Sademed (mm)",                 f"{sel_ind} vs sademed"),
        ("wind_speed_ms", "Tuulekiirus (m/s)",            f"{sel_ind} vs tuulekiirus"),
    ]
    r1c1, r1c2 = st.columns(2)
    r2c1, r2c2 = st.columns(2)
    for (x_col, x_title, title), container in zip(
        scatter_defs, [r1c1, r1c2, r2c1, r2c2]
    ):
        with container:
            _show(make_scatter(joined, x_col, x_title, sel_ind, ind_label,
                               title, sel_ind))


# ─────────────────────────────────────────────────────────────────────────────
# Võrdlused tab renderer
# ─────────────────────────────────────────────────────────────────────────────

def render_voordlused_tab() -> None:
    st.subheader("Eesti uuringualad")
    render_estonia_map()

    # Year filter — label without "(võrdlus)", applies to all blocks below
    year_opt = st.selectbox(
        "Aasta", ["2025", "2026", "Kõik"], index=2, key="voordlus_year"
    )
    year_filter = None if year_opt == "Kõik" else int(year_opt)

    try:
        df_all = fetch_aq_all_areas(year_filter)
    except Exception as exc:
        st.warning(f"Andmete laadimine ebaõnnestus: {exc}")
        return

    if df_all.empty:
        st.info("Andmed puuduvad.")
        return

    # Map station IDs → city names; Tallinn has two stations → averaged
    _station_city = {8: "Tartu", 5: "Tallinn", 7: "Tallinn", 4: "Narva"}
    df_all = df_all[df_all["station_id"].isin(_station_city)].copy()
    df_all["linn"]     = df_all["station_id"].map(_station_city)
    df_all["month_ts"] = df_all["obs_time"].dt.to_period("M").dt.to_timestamp()

    _city_order = ["Tallinn", "Tartu", "Narva"]

    # ── One block per indicator ───────────────────────────────────────────────
    for indicator in _INDICATORS:
        ind_label = _INDICATOR_FULL_NAMES.get(indicator, indicator)
        st.subheader(ind_label)

        # Monthly city averages — exclude 0 values (they represent missing data,
        # not a real zero concentration)
        monthly = (
            df_all[df_all[indicator] > 0]
            .groupby(["linn", "month_ts"], as_index=False)[indicator].mean()
            .dropna(subset=[indicator])
        )

        if monthly.empty:
            st.info("Andmed puuduvad.")
            continue

        # X-axis: numeric MM.YYYY format, horizontal labels, monthly ticks
        x_enc = alt.X(
            "month_ts:T",
            title=None,
            axis=alt.Axis(
                format="%m.%Y",
                labelAngle=0,
                tickCount="month",
            ),
        )
        y_enc = alt.Y(
            f"{indicator}:Q",
            title="µg/m³",
            scale=alt.Scale(zero=True, nice=True),
            axis=alt.Axis(tickCount=5),
        )

        line = (
            alt.Chart(monthly).mark_line(point=True)
            .encode(
                x=x_enc,
                y=y_enc,
                color=alt.Color("linn:N", title="Linn", sort=_city_order),
                tooltip=[
                    alt.Tooltip("linn:N",         title="Linn"),
                    alt.Tooltip("month_ts:T",      format="%m.%Y", title="Kuu"),
                    alt.Tooltip(f"{indicator}:Q",  format=".2f",   title="µg/m³"),
                ],
            )
        )

        # Dashed vertical rules at year boundaries when data spans multiple years
        years_present = sorted(monthly["month_ts"].dt.year.unique())
        if len(years_present) > 1:
            boundaries = pd.DataFrame({
                "yr": [pd.Timestamp(f"{y}-01-01") for y in years_present[1:]]
            })
            year_rules = (
                alt.Chart(boundaries)
                .mark_rule(strokeDash=[4, 4], strokeWidth=1, color="#999999", opacity=0.6)
                .encode(x=alt.X("yr:T"))
            )
            chart = alt.layer(year_rules, line).properties(height=260)
        else:
            chart = line.properties(height=260)

        st.altair_chart(chart, width="stretch")

        # 3 KPI metrics: Tallinn | Tartu | Narva
        st.markdown("##### Kõige saastatum kuu")
        cols = st.columns(3)
        for col, city in zip(cols, _city_order):
            city_monthly = monthly[monthly["linn"] == city].dropna(subset=[indicator])
            if city_monthly.empty:
                col.metric(city, "—")
                continue
            peak      = city_monthly.loc[city_monthly[indicator].idxmax()]
            peak_ts   = peak["month_ts"]
            month_str = _MONTH_NAMES.get(peak_ts.month, "?")
            col.metric(
                label=city,
                value=f"{month_str} {peak_ts.year}",
                delta=f"{peak[indicator]:.2f} µg/m³",
                delta_color="off",
            )

    # ── Korrelatsioonid tuule ja liiklusega kõigi näitajate lõikes ───────────
    st.markdown("---")
    try:
        jdf = _read_mart("mart_joined")
        if jdf.empty:
            st.info("Ühendatud andmed puuduvad korrelatsioonide arvutamiseks.")
        else:
            jdf["obs_time"] = pd.to_datetime(jdf["obs_time"], errors="coerce")
            if year_filter is not None:
                jdf = jdf[jdf["obs_time"].dt.year == year_filter]
            _area_labels = [("tallinn", "Tallinn"), ("tartu", "Tartu"), ("narva", "Narva")]
            for indicator in _INDICATORS:
                if indicator not in jdf.columns:
                    continue
                ind_label = _INDICATOR_FULL_NAMES.get(indicator, indicator)
                st.subheader(f"{ind_label}: tuul vs liiklus")
                idf = jdf[jdf[indicator] > 0]
                conclusions = []
                for area_key, area_label in _area_labels:
                    sub = (idf[idf["area"] == area_key]
                           [[indicator, "wind_speed_ms", "total_flow"]].dropna())
                    if len(sub) < 5:
                        conclusions.append((area_label, float("nan"), float("nan")))
                        continue
                    conclusions.append((
                        area_label,
                        sub[indicator].corr(sub["wind_speed_ms"]),
                        sub[indicator].corr(sub["total_flow"]),
                    ))
                corr_cols = st.columns(3)
                for col, (label, r_wind, r_traffic) in zip(corr_cols, conclusions):
                    with col:
                        w = abs(r_wind) if pd.notna(r_wind) else 0.0
                        t = abs(r_traffic) if pd.notna(r_traffic) else 0.0
                        r_w_str = f"{r_wind:.2f}" if pd.notna(r_wind) else "—"
                        r_t_str = f"{r_traffic:.2f}" if pd.notna(r_traffic) else "—"
                        st.metric(label, f"r(tuul) = {r_w_str}", f"r(liiklus) = {r_t_str}",
                                  delta_color="off")
                        if w > t and w > 0:
                            st.success(f"{indicator} sõltub rohkem tuule kiirusest.")
                        elif t > w and t > 0:
                            st.warning(f"{indicator} sõltub rohkem liiklustihedusest.")
                        else:
                            st.info("Andmed puuduvad või seosed on võrdsed.")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

_source_label = "PostgreSQL / marts skeem" if _get_engine() is not None else "kohalik parquet fallback"
st.caption(f"Andmeallikas: {_source_label} · Viimati uuendatud: {_last_updated_str()}")

tabs = st.tabs(["Tallinn", "Narva", "Tartu", "Võrdlused"])
for _tab, _area_key in zip(tabs[:3], ["Tallinn", "Narva", "Tartu"]):
    with _tab:
        render_area_tab(_area_key)
with tabs[3]:
    render_voordlused_tab()
