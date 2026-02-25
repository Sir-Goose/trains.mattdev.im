from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app.config import settings
from app.middleware.cache import cache
from app.models.tfl import TflBoard, TflLineStatusSummary, TflPrediction
from app.models.tfl_service import TflServiceDetail, TflServiceStop

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

    def _stop_resolution_cache_key(self, stop_point_id: str) -> str:
        return f"tfl:resolved_stop:{stop_point_id.lower()}"

    def _prediction_snapshot_cache_key(self, stop_point_id: str) -> str:
        return f"tfl:predictions:{stop_point_id.lower()}"

    def _route_sequence_cache_key(self, line_id: str, direction: str) -> str:
        return f"tfl:route_sequence:{line_id.lower()}:{direction.lower()}"

    def _timetable_cache_key(self, line_id: str, from_stop_id: str, to_stop_id: str) -> str:
        return f"tfl:timetable:{line_id.lower()}:{from_stop_id.lower()}:{to_stop_id.lower()}"

    def _stop_name_cache_key(self, stop_id: str) -> str:
        return f"tfl:stop_name:{stop_id.lower()}"

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

        query_variants = [normalized_query]
        normalized_core_query = self._normalize_station_search_text(normalized_query)
        if normalized_core_query and normalized_core_query.lower() != normalized_query.lower():
            query_variants.append(normalized_core_query)

        merged_matches: dict[str, dict] = {}
        for query_variant in query_variants:
            payload = await self._get_json(
                "/StopPoint/Search",
                params={
                    "query": query_variant,
                    "modes": ",".join(self.modes),
                    "maxResults": max(max_results, 12),
                    "includeHubs": False,
                },
            )
            for stop in (payload or {}).get("matches", []):
                stop_id = (stop.get("id") or "").strip()
                if not stop_id:
                    continue
                merged_matches[stop_id] = stop

        ranked_matches = sorted(
            merged_matches.values(),
            key=lambda stop: self._stop_search_rank(stop, normalized_core_query or normalized_query),
        )

        results: list[dict] = []
        for stop in ranked_matches:
            stop_modes = [mode for mode in (stop.get("modes") or []) if mode in self.modes]
            if not stop_modes:
                continue

            if "tube" in stop_modes:
                mode_label = "Tube"
            elif "overground" in stop_modes:
                mode_label = "Overground"
            elif "dlr" in stop_modes:
                mode_label = "DLR"
            else:
                mode_label = "TfL"
            code = stop.get("id") or ""
            display_name = self._format_search_stop_name(stop.get("name") or code, stop_modes)
            results.append(
                {
                    "provider": "tfl",
                    "name": display_name,
                    "code": code,
                    "badge": f"TfL {mode_label}",
                    "url": f"/board/tfl/{code}/departures",
                }
            )
            if len(results) >= max_results:
                break

        cache.set(cache_key, results, self.cache_ttl)
        return results

    @staticmethod
    def _normalize_station_search_text(value: str) -> str:
        normalized = value.strip().lower()
        suffixes = [
            " underground station",
            " overground station",
            " dlr station",
            " station",
        ]
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)].strip()
                break
        return normalized

    def _stop_search_rank(self, stop: dict, query: str) -> tuple[int, int, str]:
        raw_name = (stop.get("name") or "").strip()
        normalized_name = self._normalize_station_search_text(raw_name)
        normalized_query = self._normalize_station_search_text(query)
        if not normalized_query:
            normalized_query = query.strip().lower()

        score = 0
        if normalized_name == normalized_query:
            score += 100
        if raw_name.lower() == query.strip().lower():
            score += 80
        if normalized_name.startswith(normalized_query):
            score += 60
        elif any(word.startswith(normalized_query) for word in normalized_name.split()):
            score += 30
        elif normalized_query in normalized_name:
            score += 15

        if "tube" in (stop.get("modes") or []):
            score += 5

        name_len_penalty = len(normalized_name)
        return (-score, name_len_penalty, raw_name.lower())

    @staticmethod
    def _format_search_stop_name(raw_name: str, modes: list[str]) -> str:
        """Return a stable, human-readable station label for search results."""
        cleaned = (raw_name or "").strip()
        if not cleaned:
            return cleaned

        lower = cleaned.lower()
        if lower.endswith("underground station") or lower.endswith("overground station") or lower.endswith("dlr station"):
            return cleaned

        mode_set = set(modes or [])
        if "tube" in mode_set and "overground" not in mode_set:
            base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
            return f"{base} Underground Station"
        if "overground" in mode_set and "tube" not in mode_set:
            base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
            return f"{base} Overground Station"
        if "dlr" in mode_set and "tube" not in mode_set and "overground" not in mode_set:
            base = cleaned[:-8].strip() if lower.endswith(" station") else cleaned
            return f"{base} DLR Station"
        return cleaned

    async def resolve_stop_point_id(self, stop_point_id: str) -> str:
        """
        Resolve hub stop IDs (e.g. HUBBDS) to a concrete platform/station
        stop point that returns arrivals for configured TfL modes.
        """
        normalized = stop_point_id.strip()
        if not normalized:
            return stop_point_id

        cache_key = self._stop_resolution_cache_key(normalized)
        cached = cache.get(cache_key)
        if isinstance(cached, str) and cached:
            return cached

        resolved = normalized
        if normalized.upper().startswith("HUB"):
            try:
                payload = await self._get_json(f"/StopPoint/{normalized}")
                candidates = payload.get("children", []) if isinstance(payload, dict) else []
                for child in candidates:
                    child_modes = set(child.get("modes") or [])
                    if child_modes.intersection(self.modes):
                        child_id = child.get("id")
                        if child_id:
                            resolved = child_id
                            break
            except (TflAPIError, TflBoardNotFoundError):
                resolved = normalized

        cache.set(cache_key, resolved, self.cache_ttl)
        return resolved

    @staticmethod
    def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if cleaned.endswith("Z"):
            cleaned = f"{cleaned[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(cleaned)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _format_eta_display(minutes: Optional[int]) -> tuple[str, Optional[str]]:
        if minutes is None:
            return "No estimate", None
        if minutes <= 0:
            return "Due", datetime.now(timezone.utc).strftime("%H:%M")
        eta = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        eta_hhmm = eta.strftime("%H:%M")
        return f"{minutes} min ({eta_hhmm})", eta_hhmm

    async def _get_predictions_for_stop(
        self,
        stop_point_id: str,
        use_cache: bool = True,
    ) -> list[TflPrediction]:
        cache_key = self._prediction_snapshot_cache_key(stop_point_id)
        if use_cache:
            cached = cache.get(cache_key)
            if isinstance(cached, list):
                try:
                    return [TflPrediction(**item) for item in cached]
                except Exception:
                    pass

        payload = await self._get_json(f"/StopPoint/{stop_point_id}/Arrivals")
        predictions: list[TflPrediction] = []
        for item in payload or []:
            try:
                predictions.append(TflPrediction(**item))
            except Exception as exc:
                logger.warning("Failed to parse TfL prediction snapshot: %s", exc)

        predictions.sort(key=self._prediction_sort_key)
        cache.set(cache_key, [item.model_dump(mode="json") for item in predictions], self.cache_ttl)
        return predictions

    async def _get_stop_name(self, stop_id: str) -> str:
        cache_key = self._stop_name_cache_key(stop_id)
        cached = cache.get(cache_key)
        if isinstance(cached, str) and cached:
            return cached

        try:
            payload = await self._get_json(f"/StopPoint/{stop_id}")
            name = payload.get("commonName") or payload.get("name") or stop_id
        except (TflBoardNotFoundError, TflAPIError):
            name = stop_id

        cache.set(cache_key, name, self.cache_ttl)
        return name

    def _match_prediction_for_click(
        self,
        predictions: list[TflPrediction],
        line_id: str,
        to_stop_id: str,
        direction: Optional[str],
        trip_id: Optional[str],
        vehicle_id: Optional[str],
        expected_arrival: Optional[str],
    ) -> Optional[TflPrediction]:
        target_line = line_id.lower().strip()
        target_to = to_stop_id.lower().strip()
        target_direction = self._normalize_direction(direction)
        target_eta = self._parse_iso_datetime(expected_arrival)
        target_trip = (trip_id or "").strip()
        target_vehicle = (vehicle_id or "").strip()

        candidates = [p for p in predictions if (p.line_id or "").lower().strip() == target_line]
        if target_to:
            candidates = [p for p in candidates if (p.destination_naptan_id or "").lower().strip() == target_to]
        if target_direction:
            directional = [p for p in candidates if self._normalize_direction(p.direction) == target_direction]
            if directional:
                candidates = directional

        if not candidates:
            return None

        def eta_distance_seconds(prediction: TflPrediction) -> float:
            if target_eta and prediction.expected_arrival:
                return abs((prediction.expected_arrival - target_eta).total_seconds())
            return float(prediction.time_to_station or 10**9)

        if target_trip:
            trip_matches = [p for p in candidates if (p.trip_id or "").strip() == target_trip]
            if trip_matches:
                return min(trip_matches, key=eta_distance_seconds)

        if target_vehicle:
            vehicle_matches = [p for p in candidates if (p.vehicle_id or "").strip() == target_vehicle]
            if vehicle_matches:
                return min(vehicle_matches, key=eta_distance_seconds)

        if target_eta:
            return min(candidates, key=eta_distance_seconds)

        return candidates[0]

    async def _get_route_sequence(
        self,
        line_id: str,
        direction: str,
        use_cache: bool = True,
    ) -> dict:
        cache_key = self._route_sequence_cache_key(line_id, direction)
        if use_cache:
            cached = cache.get(cache_key)
            if isinstance(cached, dict):
                return cached

        payload = await self._get_json(
            f"/Line/{line_id}/Route/Sequence/{direction}",
            params={"serviceTypes": "Regular"},
        )
        if isinstance(payload, dict):
            cache.set(cache_key, payload, self.cache_ttl)
            return payload
        return {}

    async def _get_timetable_payload(
        self,
        line_id: str,
        from_stop_id: str,
        to_stop_id: str,
        use_cache: bool = True,
    ) -> dict:
        cache_key = self._timetable_cache_key(line_id, from_stop_id, to_stop_id)
        if use_cache:
            cached = cache.get(cache_key)
            if isinstance(cached, dict):
                return cached

        payload = await self._get_json(f"/Line/{line_id}/Timetable/{from_stop_id}/to/{to_stop_id}")
        if isinstance(payload, dict):
            cache.set(cache_key, payload, self.cache_ttl)
            return payload
        return {}

    @staticmethod
    def _segment_from_sequence(
        route_sequence_payload: dict,
        from_stop_id: str,
        to_stop_id: str,
    ) -> list[dict]:
        candidates: list[list[dict]] = []
        sequences = route_sequence_payload.get("stopPointSequences") or []
        for sequence in sequences:
            points = sequence.get("stopPoint") or []
            ids = [point.get("id") for point in points]
            if from_stop_id in ids and to_stop_id in ids:
                from_index = ids.index(from_stop_id)
                to_index = ids.index(to_stop_id)
                if from_index <= to_index:
                    candidates.append(points[from_index : to_index + 1])

        if not candidates:
            return []
        candidates.sort(key=len)
        return candidates[0]

    @staticmethod
    def _extract_timetable_eta_lookup(timetable_payload: dict) -> dict[str, int]:
        eta_lookup: dict[str, int] = {}
        routes = ((timetable_payload.get("timetable") or {}).get("routes") or [])
        for route in routes:
            for station_interval in route.get("stationIntervals") or []:
                for interval in station_interval.get("intervals") or []:
                    stop_id = interval.get("stopId")
                    eta_value = interval.get("timeToArrival")
                    if stop_id is None or eta_value is None:
                        continue
                    minutes = int(round(float(eta_value)))
                    if stop_id not in eta_lookup or minutes < eta_lookup[stop_id]:
                        eta_lookup[stop_id] = minutes
        return eta_lookup

    async def _fallback_points_from_timetable(
        self,
        timetable_payload: dict,
        from_stop_id: str,
        to_stop_id: str,
    ) -> list[dict]:
        station_name_lookup: dict[str, str] = {}
        for station in timetable_payload.get("stations") or []:
            station_id = station.get("id")
            station_name = station.get("name")
            if station_id and station_name:
                station_name_lookup[station_id] = station_name

        eta_lookup = self._extract_timetable_eta_lookup(timetable_payload)
        if not eta_lookup:
            return [
                {"id": from_stop_id, "name": station_name_lookup.get(from_stop_id) or await self._get_stop_name(from_stop_id)},
                {"id": to_stop_id, "name": station_name_lookup.get(to_stop_id) or await self._get_stop_name(to_stop_id)},
            ]

        if from_stop_id not in eta_lookup:
            eta_lookup[from_stop_id] = 0

        ordered = sorted(eta_lookup.items(), key=lambda item: item[1])
        ordered_ids = [stop_id for stop_id, _ in ordered]

        if to_stop_id not in ordered_ids:
            ordered_ids.append(to_stop_id)

        if from_stop_id in ordered_ids and to_stop_id in ordered_ids:
            from_index = ordered_ids.index(from_stop_id)
            to_index = ordered_ids.index(to_stop_id)
            if from_index <= to_index:
                ordered_ids = ordered_ids[from_index : to_index + 1]

        points: list[dict] = []
        for stop_id in ordered_ids:
            name = station_name_lookup.get(stop_id)
            if not name:
                name = await self._get_stop_name(stop_id)
            points.append({"id": stop_id, "name": name})
        return points

    def _build_service_stops(
        self,
        points: list[dict],
        eta_lookup: dict[str, int],
        from_stop_id: str,
        to_stop_id: str,
    ) -> list[TflServiceStop]:
        stops: list[TflServiceStop] = []
        for point in points:
            stop_id = point.get("id")
            if not stop_id:
                continue
            stop_name = point.get("name") or stop_id
            eta_minutes = eta_lookup.get(stop_id)
            display, eta_clock = self._format_eta_display(eta_minutes)
            stops.append(
                TflServiceStop(
                    stop_id=stop_id,
                    stop_name=stop_name,
                    eta_minutes=eta_minutes,
                    eta_time=eta_clock,
                    arrival_display=display,
                    departure_display=display,
                    is_current=stop_id == from_stop_id,
                    is_destination=stop_id == to_stop_id,
                )
            )
        return stops

    async def get_service_route_detail(
        self,
        line_id: str,
        from_stop_id: str,
        to_stop_id: str,
        direction: Optional[str] = None,
        trip_id: Optional[str] = None,
        vehicle_id: Optional[str] = None,
        expected_arrival: Optional[str] = None,
        station_name: Optional[str] = None,
        destination_name: Optional[str] = None,
        use_cache: bool = True,
    ) -> TflServiceDetail:
        line_id = (line_id or "").strip().lower()
        if not line_id:
            raise TflBoardNotFoundError("TfL line id is required.")

        from_stop_id = await self.resolve_stop_point_id(from_stop_id)
        to_stop_id = await self.resolve_stop_point_id(to_stop_id)

        predictions = await self._get_predictions_for_stop(from_stop_id, use_cache=use_cache)
        matched = self._match_prediction_for_click(
            predictions=predictions,
            line_id=line_id,
            to_stop_id=to_stop_id,
            direction=direction,
            trip_id=trip_id,
            vehicle_id=vehicle_id,
            expected_arrival=expected_arrival,
        )

        resolved_mode = "exact" if matched else "fallback"
        resolved_direction = self._normalize_direction(direction) or (
            self._normalize_direction(matched.direction) if matched else None
        )
        resolved_line_name = (matched.line_name if matched else None) or line_id.replace("-", " ").title()
        resolved_origin_name = station_name or (matched.station_name if matched else None) or await self._get_stop_name(from_stop_id)
        resolved_destination_name = (
            destination_name
            or (matched.destination_name if matched else None)
            or await self._get_stop_name(to_stop_id)
        )
        inferred_mode_name = "dlr" if line_id == "dlr" else (self.modes[0] if self.modes else "tube")
        resolved_mode_name = (matched.mode_name if matched else None) or inferred_mode_name
        resolved_trip_id = (matched.trip_id if matched else None) or trip_id
        resolved_vehicle_id = (matched.vehicle_id if matched else None) or vehicle_id
        resolved_expected_arrival = (
            matched.expected_arrival.isoformat() if matched and matched.expected_arrival else expected_arrival
        )

        directions_to_try: list[str] = []
        if resolved_direction in {"inbound", "outbound"}:
            directions_to_try.append(resolved_direction)
            directions_to_try.append("outbound" if resolved_direction == "inbound" else "inbound")
        else:
            directions_to_try.extend(["inbound", "outbound"])

        selected_points: list[dict] = []
        selected_direction: Optional[str] = resolved_direction
        for direction_candidate in directions_to_try:
            try:
                route_payload = await self._get_route_sequence(line_id, direction_candidate, use_cache=use_cache)
            except (TflAPIError, TflBoardNotFoundError):
                continue
            segment = self._segment_from_sequence(route_payload, from_stop_id, to_stop_id)
            if segment:
                selected_points = segment
                selected_direction = direction_candidate
                break

        timetable_payload: dict = {}
        try:
            timetable_payload = await self._get_timetable_payload(
                line_id=line_id,
                from_stop_id=from_stop_id,
                to_stop_id=to_stop_id,
                use_cache=use_cache,
            )
        except (TflAPIError, TflBoardNotFoundError):
            timetable_payload = {}

        eta_lookup = self._extract_timetable_eta_lookup(timetable_payload)
        if not selected_points:
            selected_points = await self._fallback_points_from_timetable(
                timetable_payload=timetable_payload,
                from_stop_id=from_stop_id,
                to_stop_id=to_stop_id,
            )

        stops = self._build_service_stops(
            points=selected_points,
            eta_lookup=eta_lookup,
            from_stop_id=from_stop_id,
            to_stop_id=to_stop_id,
        )
        if not stops:
            stops = [
                TflServiceStop(stop_id=from_stop_id, stop_name=resolved_origin_name, is_current=True),
                TflServiceStop(stop_id=to_stop_id, stop_name=resolved_destination_name, is_destination=True),
            ]

        return TflServiceDetail(
            line_id=line_id,
            line_name=resolved_line_name,
            direction=selected_direction or resolved_direction,
            from_stop_id=from_stop_id,
            to_stop_id=to_stop_id,
            origin_name=resolved_origin_name,
            destination_name=resolved_destination_name,
            resolution_mode=resolved_mode,
            mode_name=resolved_mode_name,
            station_name=resolved_origin_name,
            vehicle_id=resolved_vehicle_id,
            trip_id=resolved_trip_id,
            expected_arrival=resolved_expected_arrival,
            pulledAt=self._current_timestamp_iso(),
            stops=stops,
        )

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

        stop_point_id = await self.resolve_stop_point_id(stop_point_id)

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
        no_direction = [p for p in predictions if self._normalize_direction(p.direction) is None]
        if view == "departures":
            outbound = [p for p in predictions if self._normalize_direction(p.direction) == "outbound"]
            return outbound + no_direction if outbound else predictions
        if view == "arrivals":
            inbound = [p for p in predictions if self._normalize_direction(p.direction) == "inbound"]
            return inbound + no_direction if inbound else predictions
        return predictions


# Global service instance
tfl_api_service = TflAPIService()
