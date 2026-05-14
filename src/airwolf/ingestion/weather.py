import pandas as pd

from ..clients.envir_client import EnvirClient


def fetch_weather_stations(date: str) -> pd.DataFrame:
    """Return unique weather stations that have observations in the month of *date* (YYYY-MM-DD).

    Filtering by year+month (not full date) because the month granularity is
    sufficient for location mapping and avoids empty results on days near the
    data publication boundary.

    Coordinates come from f_kliima_jaam_vaatlus (pikkuskraad/laiuskraad in WGS84).
    """
    year, month, _day = date.split("-")
    client = EnvirClient()

    obs = client.get(
        "f_kliima_paev",
        params=[
            ("aasta", f"eq.{year}"),
            ("kuu", f"eq.{int(month)}"),
            ("select", "jaam_kood,jaam_nimi"),
        ],
    )
    if not obs:
        return pd.DataFrame(columns=["station_id", "station_name", "lon", "lat"])

    station_codes = list({r["jaam_kood"] for r in obs})
    codes_str = ",".join(station_codes)

    meta = client.get(
        "f_kliima_jaam_vaatlus",
        params=[
            ("jaam_kood", f"in.({codes_str})"),
            ("select", "jaam_kood,jaam_nimi,pikkuskraad,laiuskraad"),
        ],
    )
    if not meta:
        return pd.DataFrame(columns=["station_id", "station_name", "lon", "lat"])

    return (
        pd.DataFrame(meta)
        .drop_duplicates(subset=["jaam_kood"])
        .dropna(subset=["pikkuskraad", "laiuskraad"])
        .rename(
            columns={
                "jaam_kood": "station_id",
                "jaam_nimi": "station_name",
                "pikkuskraad": "lon",
                "laiuskraad": "lat",
            }
        )[["station_id", "station_name", "lon", "lat"]]
        .reset_index(drop=True)
    )
