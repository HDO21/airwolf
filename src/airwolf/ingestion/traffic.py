import pandas as pd
from pyproj import Transformer

from ..clients.traffic_client import TrafficClient

# EPSG:3301 → WGS84; always_xy=True means (easting, northing) → (lon, lat)
_t = Transformer.from_crs("EPSG:3301", "EPSG:4326", always_xy=True)


def fetch_traffic_detectors(_date: str | None = None) -> pd.DataFrame:
    """Return all traffic detector locations from the live ArcGIS snapshot.

    A date argument is accepted for API consistency but not used as a filter:
    the tarktee.mnt.ee service stores only the current measurement snapshot
    (no historical archive), so date filtering would return empty results.
    """
    client = TrafficClient()
    result = client.query(
        {
            "where": "1=1",
            "resultRecordCount": 2000,
        }
    )

    features = result.get("features", [])
    if not features:
        return pd.DataFrame(columns=["detector_id", "site_name", "road_name", "lon", "lat"])

    rows = []
    for f in features:
        attr = f.get("attributes", {})
        geom = f.get("geometry") or {}
        rows.append(
            {
                "detector_id": attr.get("traffic_detector_id"),
                "site_name": attr.get("site_name"),
                "road_name": attr.get("road_name"),
                "easting": geom.get("x"),
                "northing": geom.get("y"),
            }
        )

    df = (
        pd.DataFrame(rows)
        .drop_duplicates(subset=["detector_id"])
        .dropna(subset=["easting", "northing"])
    )
    if df.empty:
        return pd.DataFrame(columns=["detector_id", "site_name", "road_name", "lon", "lat"])

    lons, lats = _t.transform(df["easting"].to_numpy(), df["northing"].to_numpy())
    return (
        df.assign(lon=lons, lat=lats)
        .drop(columns=["easting", "northing"])
        .reset_index(drop=True)
    )
