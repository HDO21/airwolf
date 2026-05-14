import requests
from typing import Any


class EnvirClient:
    """Thin HTTP client for the keskkonnaandmed.envir.ee PostgREST API."""

    BASE_URL = "https://keskkonnaandmed.envir.ee"
    SCHEMA = "apijahiala"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept-Profile": self.SCHEMA,
                "Accept": "application/json",
            }
        )

    def get(
        self,
        endpoint: str,
        params: list[tuple[str, Any]] | dict[str, Any] | None = None,
        limit: int = 5000,
    ) -> list[dict]:
        """GET an endpoint and return the JSON array.

        Pass params as a list of tuples to support repeated keys (PostgREST
        range filters on the same column).
        """
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        base: list[tuple[str, Any]] = [("limit", limit)]
        if isinstance(params, dict):
            base += list(params.items())
        elif params:
            base += params
        resp = self.session.get(url, params=base, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        raise ValueError(f"Unexpected response from {endpoint}: {data}")
