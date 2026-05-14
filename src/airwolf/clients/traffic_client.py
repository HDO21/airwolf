import requests
from typing import Any


class TrafficClient:
    """Thin HTTP client for the tarktee.mnt.ee ArcGIS REST traffic detector service."""

    BASE_URL = "https://tarktee.mnt.ee/tarktee/rest/services/traffic_detectors/MapServer/0"

    def __init__(self) -> None:
        self.session = requests.Session()

    def query(self, params: dict[str, Any] | None = None) -> dict:
        """Query the layer and return the full ArcGIS JSON response."""
        defaults: dict[str, Any] = {
            "f": "json",
            "outFields": "*",
            "outSR": "3301",
            "returnGeometry": "true",
        }
        if params:
            defaults.update(params)
        resp = self.session.get(f"{self.BASE_URL}/query", params=defaults, timeout=30)
        resp.raise_for_status()
        return resp.json()
