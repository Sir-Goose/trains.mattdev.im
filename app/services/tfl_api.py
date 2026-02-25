from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.middleware.cache import cache
from app.models.tfl import TflBoard, TflLineStatusSummary, TflPrediction

logger = logging.getLogger(__name__)


class TflBoardNotFoundError(Exception):
    """Raised when a stop point cannot be resolved to a TfL board."""


class TflAPIError(Exception):
    """Raised when upstream TfL API is unavailable/invalid."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class TflBoardFetchResult:
    board: TflBoard
    from_cache: bool


class TflAPIService:
    """Service for interacting with TfL unified API."""

    def __init__(self):
        self.base_url = settings.tfl_api_base_url.rstrip("/")
        self.app_key = settings.tfl_app_key
        self.app_id = settings.tfl_app_id
        self.modes = settings.tfl_modes
        self.cache_ttl = settings.cache_ttl_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def startup(self) -> None:
        await self._get_client()

    async def shutdown(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    def _current_timestamp_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _auth_params(self) -> dict:
        if not self.app_key:
            raise TflAPIError(
                "TfL API key is not configured (set TFL_APP_KEY/TFL_API_KEY or create a local 'tfl_key' file).",
                status_code=503,
            )
        params = {"app_key": self.app_key}
        if self.app_id:
            params["app_id"] = self.app_id
        return params

    async def _get_json(self, path: str, params: Optional[dict] = None):
        request_params = self._auth_params()
        if params:
            request_params.update(params)

        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}{path}", params=request_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code == 404:
                raise TflBoardNotFoundError("TfL stop point was not found.") from exc
            if status_code in {401, 403}:
                raise TflAPIError("TfL API authentication failed.", status_code=503) from exc
            if 500 <= status_code < 600:
                raise TflAPIError("TfL API is temporarily unavailable.", status_code=503) from exc
            raise TflAPIError("TfL API returned an unexpected response.", status_code=502) from exc
        except httpx.RequestError as exc:
            raise TflAPIError("Unable to reach TfL API.", status_code=503) from exc
        except ValueError as exc:
            raise TflAPIError("TfL API returned invalid JSON.", status_code=502) from exc

    @staticmethod
    def _normalize_direction(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return value.strip().lower()

    def _board_cache_key(self, stop_point_id: str) -> str:
        return f"tfl:board:{stop_point_id.lower()}"

    def _status_cache_key(self) -> str:
        return f"tfl:status:{','.join(self.modes)}"

    def _search_cache_key(self, query: str) -> str:
        return f"tfl:search:{query.strip().lower()}"

    @staticmethod
    def _prediction_sort_key(prediction: TflPrediction):
        time_to_station = prediction.time_to_station if prediction.time_to_station is not None else 10**9
        expected = prediction.expected_arrival or datetime.max.replace(tzinfo=timezone.utc)
        return (time_to_station, expected)

    async def get_line_status(self) -> list[TflLineStatusSummary]:
        cache_key = self._status_cache_key()
        cached = cache.get(cache_key)
        if isinstance(cached, list):
            try:
                return [TflLineStatusSummary(**item) for item in cached]
            except Exception:
                pass

        payload = await self._get_json(f"/Line/Mode/{','.join(self.modes)}/Status")
        summaries: list[TflLineStatusSummary] = []

        for line in payload or []:
            statuses = line.get("lineStatuses") or []
            for status in statuses:
                summaries.append(
                    TflLineStatusSummary(
                        line_id=line.get("id") or "unknown",
                        line_name=line.get("name") or "Unknown",
                        status_severity=status.get("statusSeverity"),
                        status_description=status.get("statusSeverityDescription"),
                        reason=status.get("reason"),
                    )
                )

        cache.set(cache_key, [item.model_dump() for item in summaries], self.cache_ttl)
        return summaries

    async def search_stop_points(self, query: str, max_results: int = 8) -> list[dict]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        cache_key = self._search_cache_key(normalized_query)
        cached = cache.get(cache_key)
        if isinstance(cached, list):
            return cached

        payload = await self._get_json(
            "/StopPoint/Search",
            params={
                "query": normalized_query,
                "modes": ",".join(self.modes),
                "maxResults": max_results,
                "includeHubs": False,
            },
        )

        results: list[dict] = []
        for stop in (payload or {}).get("matches", []):
            stop_modes = [mode for mode in (stop.get("modes") or []) if mode in self.modes]
            if not stop_modes:
                continue

            mode_label = "Overground" if "overground" in stop_modes else "Tube"
            code = stop.get("id") or ""
            results.append(
                {
                    "provider": "tfl",
                    "name": stop.get("name") or code,
                    "code": code,
                    "badge": f"TfL {mode_label}",
                    "url": f"/board/tfl/{code}/departures",
                }
            )

        cache.set(cache_key, results, self.cache_ttl)
        return results

    def _build_board(
        self,
        stop_point_id: str,
        station_name: str,
        predictions_payload: list[dict],
        line_status: list[TflLineStatusSummary],
    ) -> TflBoard:
        predictions: list[TflPrediction] = []
        for item in predictions_payload or []:
            try:
                predictions.append(TflPrediction(**item))
            except Exception as exc:
                logger.warning("Failed to parse TfL prediction: %s", exc)

        predictions.sort(key=self._prediction_sort_key)

        # Include only line statuses relevant to this stop when possible.
        line_ids = {p.line_id for p in predictions if p.line_id}
        if line_ids:
            filtered_status = [status for status in line_status if status.line_id in line_ids]
        else:
            filtered_status = line_status

        return TflBoard(
            stop_point_id=stop_point_id,
            station_name=station_name,
            generated_at=self._current_timestamp_iso(),
            pulled_at=self._current_timestamp_iso(),
            trains=predictions,
            line_status=filtered_status,
        )

    async def get_board(self, stop_point_id: str, use_cache: bool = True) -> TflBoardFetchResult:
        stop_point_id = stop_point_id.strip()
        if not stop_point_id:
            raise TflBoardNotFoundError("TfL stop point id is required.")

        cache_key = self._board_cache_key(stop_point_id)

        if use_cache:
            cached = cache.get(cache_key)
            if isinstance(cached, dict):
                try:
                    return TflBoardFetchResult(board=TflBoard(**cached), from_cache=True)
                except Exception:
                    pass

        predictions_payload = await self._get_json(f"/StopPoint/{stop_point_id}/Arrivals")

        # Lookup station name from prediction payload; fall back to stop id.
        station_name = stop_point_id
        if predictions_payload:
            station_name = predictions_payload[0].get("stationName") or stop_point_id
        else:
            try:
                stop_payload = await self._get_json(f"/StopPoint/{stop_point_id}")
                station_name = stop_payload.get("commonName") or stop_payload.get("name") or stop_point_id
            except (TflBoardNotFoundError, TflAPIError):
                station_name = stop_point_id

        line_status = await self.get_line_status()
        board = self._build_board(stop_point_id, station_name, predictions_payload, line_status)

        cache.set(cache_key, board.model_dump(mode="json"), self.cache_ttl)
        return TflBoardFetchResult(board=board, from_cache=False)

    def predictions_for_view(self, predictions: list[TflPrediction], view: str) -> list[TflPrediction]:
        if view == "departures":
            outbound = [p for p in predictions if self._normalize_direction(p.direction) == "outbound"]
            return outbound if outbound else predictions
        if view == "arrivals":
            inbound = [p for p in predictions if self._normalize_direction(p.direction) == "inbound"]
            return inbound if inbound else predictions
        return predictions


# Global service instance
tfl_api_service = TflAPIService()
