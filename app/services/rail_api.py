import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings
from app.middleware.cache import cache
from app.models.board import Board, ServiceDetails, Train


logger = logging.getLogger(__name__)


class BoardNotFoundError(Exception):
    """Raised when a CRS code cannot be resolved to a station board."""


class RailAPIError(Exception):
    """Raised when the upstream rail API is unavailable or invalid."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class BoardFetchResult:
    """Result object that includes board data and cache provenance."""

    board: Board
    from_cache: bool


@dataclass
class DetailedBoardFetchResult:
    """Detailed board payload plus cache provenance."""

    data: dict
    from_cache: bool


class RailAPIService:
    """Service for interacting with National Rail API"""
    
    def __init__(self):
        self.base_url = settings.rail_api_base_url
        self.api_key = settings.rail_api_key
        self.cache_ttl = settings.cache_ttl_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def startup(self) -> None:
        """Initialize shared HTTP client for outbound rail API requests."""
        await self._get_client()

    async def shutdown(self) -> None:
        """Close shared HTTP client cleanly."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or lazily create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client
    
    def _get_headers(self) -> dict:
        """Get headers for API requests"""
        return {
            'x-apikey': self.api_key,
            'User-Agent': 'trains.mattdev.im/1.0'
        }

    def _current_timestamp_iso(self) -> str:
        """Get current UTC timestamp in ISO-8601 format."""
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _stamp_pulled_at(self, payload: dict) -> dict:
        """Attach pull timestamp to fetched payload."""
        payload["pulledAt"] = self._current_timestamp_iso()
        return payload

    @staticmethod
    def _normalize_crs(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        crs = value.strip().upper()
        if len(crs) != 3 or not crs.isalpha():
            return None
        return crs

    def _service_route_cache_key(self, service_id: str) -> str:
        return f"service_route_candidates:{service_id}"

    def _service_last_seen_cache_key(self, service_id: str) -> str:
        return f"service_last_seen_crs:{service_id}"

    def _service_tracking_ttl(self) -> int:
        # Keep route tracking longer than board snapshots so users can follow
        # services across many stations in one journey.
        return max(self.cache_ttl * 6, 3600)

    def _build_service_crs_candidates(self, service: ServiceDetails) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(crs_value: Optional[str]) -> None:
            crs = self._normalize_crs(crs_value)
            if crs and crs not in seen:
                seen.add(crs)
                candidates.append(crs)

        for stop in service.all_previous_stops:
            add(getattr(stop, "crs", None))
        add(service.crs)
        for stop in service.all_subsequent_stops:
            add(getattr(stop, "crs", None))

        return candidates

    def _cache_service_tracking(self, service_id: str, service: ServiceDetails) -> None:
        ttl = self._service_tracking_ttl()
        candidates = self._build_service_crs_candidates(service)
        if candidates:
            cache.set(self._service_route_cache_key(service_id), candidates, ttl)
        current_crs = self._normalize_crs(service.crs)
        if current_crs:
            cache.set(self._service_last_seen_cache_key(service_id), current_crs, ttl)

    def _get_cached_service_route_candidates(self, service_id: str) -> list[str]:
        cached = cache.get(self._service_route_cache_key(service_id))
        if not isinstance(cached, list):
            return []
        candidates: list[str] = []
        seen: set[str] = set()
        for value in cached:
            crs = self._normalize_crs(value if isinstance(value, str) else None)
            if crs and crs not in seen:
                seen.add(crs)
                candidates.append(crs)
        return candidates

    def _get_cached_last_seen_crs(self, service_id: str) -> Optional[str]:
        cached = cache.get(self._service_last_seen_cache_key(service_id))
        if isinstance(cached, str):
            return self._normalize_crs(cached)
        return None

    def _extract_service_from_detailed_payload(
        self,
        data: Optional[dict],
        service_id: str,
    ) -> Optional[ServiceDetails]:
        train_services = data.get("trainServices", []) if data else []
        matching_service = next(
            (service for service in train_services if service.get("serviceID") == service_id),
            None,
        )
        if not matching_service:
            return None

        service_payload = {
            "generatedAt": data.get("generatedAt"),
            "pulledAt": data.get("pulledAt"),
            "locationName": data.get("locationName"),
            "crs": data.get("crs"),
            **matching_service,
        }
        return ServiceDetails(**service_payload)

    async def _get_detailed_board(
        self,
        crs_code: str,
        use_cache: bool = True,
    ) -> DetailedBoardFetchResult:
        crs_code = crs_code.upper()
        cache_key = f"board_details:{crs_code}"
        details_cache_ttl = min(self.cache_ttl, 60)
        data: Optional[dict] = None
        from_cache = False

        if use_cache:
            data = cache.get(cache_key)
            from_cache = data is not None

        if data is not None:
            return DetailedBoardFetchResult(data=data, from_cache=True)

        url = f"{self.base_url}/GetArrDepBoardWithDetails/{crs_code}"
        params = {
            "numRows": settings.rail_api_num_rows,
            "timeWindow": settings.rail_api_time_window,
            "timeOffset": 0,
        }

        try:
            client = await self._get_client()
            response = await client.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as exc:
                logger.warning("Invalid JSON from detailed rail API for %s", crs_code)
                raise RailAPIError(
                    "Rail data service returned an invalid response.",
                    status_code=502,
                ) from exc

            if not data:
                raise BoardNotFoundError(
                    f"Could not fetch board data for station '{crs_code}'. Please check the CRS code is valid."
                )

            data = self._stamp_pulled_at(data)
            cache.set(cache_key, data, details_cache_ttl)
            return DetailedBoardFetchResult(data=data, from_cache=from_cache)

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {400, 404}:
                raise BoardNotFoundError(
                    f"Could not fetch board data for station '{crs_code}'. Please check the CRS code is valid."
                ) from exc
            if status_code in {401, 403}:
                raise RailAPIError(
                    "Rail data service authentication failed.",
                    status_code=503,
                ) from exc
            if 500 <= status_code < 600:
                raise RailAPIError(
                    "Rail data service is temporarily unavailable.",
                    status_code=503,
                ) from exc
            raise RailAPIError(
                "Rail data service returned an unexpected response.",
                status_code=502,
            ) from exc
        except httpx.RequestError as exc:
            raise RailAPIError(
                "Unable to reach rail data service.",
                status_code=503,
            ) from exc
        except (BoardNotFoundError, RailAPIError):
            raise
        except Exception as exc:
            logger.exception("Unexpected error fetching detailed board for %s", crs_code)
            raise RailAPIError(
                "Unexpected error fetching route data.",
                status_code=502,
            ) from exc
    
    async def get_board(self, crs_code: str, use_cache: bool = True) -> BoardFetchResult:
        """
        Get arrival and departure board for a station
        
        Args:
            crs_code: CRS station code (e.g., 'LHD' for Leatherhead)
            use_cache: Whether to use cached data if available
        
        Returns:
            BoardFetchResult with board payload and cache-hit metadata
        """
        crs_code = crs_code.upper()
        cache_key = f"board:{crs_code}"
        
        # Check cache first
        if use_cache:
            cached_board = cache.get(cache_key)
            if cached_board:
                if isinstance(cached_board, Board):
                    return BoardFetchResult(board=cached_board, from_cache=True)
                if isinstance(cached_board, dict):
                    parsed_cached_board = self._parse_board(cached_board)
                    return BoardFetchResult(board=parsed_cached_board, from_cache=True)
        
        # Fetch from API using regular endpoint (not WithDetails) to get up to 150 trains
        # Details will be fetched on-demand for individual services
        url = f"{self.base_url}/GetArrivalDepartureBoard/{crs_code}"
        params = {
            "numRows": settings.rail_api_num_rows,
            "timeWindow": settings.rail_api_time_window,
            "timeOffset": 0  # Start from now
        }
        
        try:
            client = await self._get_client()
            response = await client.get(url, headers=self._get_headers(), params=params)
            response.raise_for_status()

            try:
                data = response.json()
            except ValueError as exc:
                logger.warning("Invalid JSON from rail API for %s", crs_code)
                raise RailAPIError(
                    "Rail data service returned an invalid response.",
                    status_code=502,
                ) from exc

            if not data:
                raise BoardNotFoundError(
                    f"Could not fetch board data for station '{crs_code}'. Please check the CRS code is valid."
                )

            # Track when we actually pulled this payload, so UI timestamps stay
            # aligned with cache freshness rather than page render time.
            data = self._stamp_pulled_at(data)
            board = self._parse_board(data)

            # Defensive guard for malformed success payloads
            if not board.location_name and not board.crs:
                raise BoardNotFoundError(
                    f"Could not fetch board data for station '{crs_code}'. Please check the CRS code is valid."
                )

            cache.set(cache_key, data, self.cache_ttl)
            return BoardFetchResult(board=board, from_cache=False)

        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {400, 404}:
                raise BoardNotFoundError(
                    f"Could not fetch board data for station '{crs_code}'. Please check the CRS code is valid."
                ) from exc
            if status_code in {401, 403}:
                raise RailAPIError(
                    "Rail data service authentication failed.",
                    status_code=503,
                ) from exc
            if 500 <= status_code < 600:
                raise RailAPIError(
                    "Rail data service is temporarily unavailable.",
                    status_code=503,
                ) from exc
            raise RailAPIError(
                "Rail data service returned an unexpected response.",
                status_code=502,
            ) from exc
        except httpx.RequestError as exc:
            raise RailAPIError(
                "Unable to reach rail data service.",
                status_code=503,
            ) from exc
        except (BoardNotFoundError, RailAPIError):
            raise
        except Exception as exc:
            logger.exception("Unexpected error fetching board for %s", crs_code)
            raise RailAPIError(
                "Unexpected error fetching board data.",
                status_code=502,
            ) from exc

    async def get_service_route(
        self,
        crs_code: str,
        service_id: str,
        use_cache: bool = True,
    ) -> Optional[ServiceDetails]:
        """Get detailed route information for a specific service from a station board."""
        detailed_board = await self._get_detailed_board(crs_code, use_cache=use_cache)
        service = self._extract_service_from_detailed_payload(detailed_board.data, service_id)
        if service:
            self._cache_service_tracking(service_id, service)
            return service

        # Avoid stale-negative misses where this station board was cached before
        # the service entered the window.
        if use_cache and detailed_board.from_cache:
            fresh_board = await self._get_detailed_board(crs_code, use_cache=False)
            service = self._extract_service_from_detailed_payload(fresh_board.data, service_id)
            if service:
                self._cache_service_tracking(service_id, service)
            return service

        return None

    async def get_service_route_following(
        self,
        crs_code: str,
        service_id: str,
        use_cache: bool = True,
        max_stations_to_check: int = 10,
    ) -> Optional[ServiceDetails]:
        """
        Get service details, following the train along known calling points when it
        drops off the current station's board.
        """
        requested_crs = crs_code.upper()
        candidate_stations: list[str] = []
        seen: set[str] = set()

        def add_candidate(candidate: Optional[str]) -> None:
            crs = self._normalize_crs(candidate)
            if crs and crs not in seen:
                seen.add(crs)
                candidate_stations.append(crs)

        # Prioritize the best likely station first.
        add_candidate(self._get_cached_last_seen_crs(service_id))
        add_candidate(requested_crs)
        for candidate in self._get_cached_service_route_candidates(service_id):
            add_candidate(candidate)

        if not candidate_stations:
            return None

        for station_crs in candidate_stations[:max_stations_to_check]:
            service = await self.get_service_route(
                station_crs,
                service_id,
                use_cache=use_cache,
            )
            if service:
                self._cache_service_tracking(service_id, service)
                return service

        return None
    
    def _parse_board(self, data: dict) -> Board:
        """Parse API response into Board model."""
        # Extract train services if they exist
        train_services = data.get('trainServices', [])
        
        # Parse each train (service details will be fetched on-demand)
        trains = []
        for train_data in train_services:
            try:
                train = Train(**train_data)
                trains.append(train)
            except Exception as exc:
                logger.warning("Error parsing train data: %s", exc)
                continue
        
        # Create board
        board_data = {
            'locationName': data.get('locationName'),
            'crs': data.get('crs'),
            'generatedAt': data.get('generatedAt'),
            'pulledAt': data.get('pulledAt'),
            'filterType': data.get('filterType'),
            'platformAvailable': data.get('platformAvailable', True),
            'areServicesAvailable': data.get('areServicesAvailable', True),
            'trainServices': trains,
            'nrccMessages': data.get('nrccMessages')
        }
        
        return Board(**board_data)

    def clear_cache(self, crs_code: Optional[str] = None) -> None:
        """Clear cache for a specific station or all stations"""
        if crs_code:
            cache.delete(f"board:{crs_code.upper()}")
        else:
            cache.clear()
    
    # Service details endpoint disabled - Darwin REST API doesn't support individual service queries
    # Would require switching to SOAP API to implement this feature
    
    # async def get_service_details(self, service_id: str, use_cache: bool = True) -> Optional[ServiceDetails]:
    #     """
    #     Get detailed information about a specific train service.
    #     Fetches from the GetServiceDetails API endpoint with 60-second caching.
    #     
    #     DISABLED: The Darwin REST API doesn't have a GetServiceDetails endpoint.
    #     This functionality is only available in the SOAP API.
    #     
    #     Args:
    #         service_id: The unique service identifier from the board
    #         use_cache: Whether to use cached data if available
    #     
    #     Returns:
    #         ServiceDetails object or None if service not found
    #     """
    #     return None


# Global service instance
rail_api_service = RailAPIService()
