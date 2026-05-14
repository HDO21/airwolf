import pandas as pd
from pyproj import Transformer

from ..clients.envir_client import EnvirClient

# EPSG:3301 → WGS84; always_xy=True means (easting, northing) → (lon, lat)
_t = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)


def fetch_air_quality_stations(_date: str | None = None) -> pd.DataFrame:
    """Return all known air-quality monitoring sites for the Välisõhu seire programme.

    A date argument is accepted for API consistency but not used as a filter:
    the seireaeg_algus column is unindexed and date-range queries time out.
    Station locations are static, so all known sites are returned regardless.
    """
    client = EnvirClient()

    records = client.get(
        "f_keskkonnaseire",
        params=[
            ("seiretoo_seotud_programmi_nimi_ii", "eq.Välisõhu seire"),
            (
                "select",
                "seirekoht_kood,seirekoht_nimi,seirekoht_koordx,seirekoht_koordy,seirekoht_ehak_tekst",
            ),
        ],
        limit=2000,
    )
    if not records:
        return pd.DataFrame(columns=["station_id", "station_name", "region", "lon", "lat"])

    df = (
        pd.DataFrame(records)
        .drop_duplicates(subset=["seirekoht_kood"])
        .dropna(subset=["seirekoht_koordx", "seirekoht_koordy"])
    )
    if df.empty:
        return pd.DataFrame(columns=["station_id", "station_name", "region", "lon", "lat"])

    # koordx = northing, koordy = easting (Estonian naming convention)
    lons, lats = _t.transform(
        df["seirekoht_koordy"].to_numpy(),  # easting
        df["seirekoht_koordx"].to_numpy(),  # northing
    )
    return (
        df.assign(lon=lons, lat=lats)
        .rename(
            columns={
                "seirekoht_kood": "station_id",
                "seirekoht_nimi": "station_name",
                "seirekoht_ehak_tekst": "region",
            }
        )[["station_id", "station_name", "region", "lon", "lat"]]
        .reset_index(drop=True)
    )
