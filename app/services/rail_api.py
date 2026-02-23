import logging
from dataclasses import dataclass
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


class RailAPIService:
    """Service for interacting with National Rail API"""
    
    def __init__(self):
        self.base_url = settings.rail_api_base_url
        self.api_key = settings.rail_api_key
        self.cache_ttl = settings.cache_ttl_seconds
    
    def _get_headers(self) -> dict:
        """Get headers for API requests"""
        return {
            'x-apikey': self.api_key,
            'User-Agent': 'LeatherheadLive/1.0'
        }
    
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
            async with httpx.AsyncClient(timeout=10.0) as client:
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
        crs_code = crs_code.upper()
        cache_key = f"board_details:{crs_code}"
        details_cache_ttl = min(self.cache_ttl, 60)
        data: Optional[dict] = None

        if use_cache:
            data = cache.get(cache_key)

        if data is None:
            url = f"{self.base_url}/GetArrDepBoardWithDetails/{crs_code}"
            params = {
                "numRows": settings.rail_api_num_rows,
                "timeWindow": settings.rail_api_time_window,
                "timeOffset": 0,
            }

            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
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

                cache.set(cache_key, data, details_cache_ttl)

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

        train_services = data.get("trainServices", []) if data else []
        matching_service = next(
            (service for service in train_services if service.get("serviceID") == service_id),
            None,
        )
        if not matching_service:
            return None

        service_payload = {
            "generatedAt": data.get("generatedAt"),
            "locationName": data.get("locationName"),
            "crs": data.get("crs"),
            **matching_service,
        }
        return ServiceDetails(**service_payload)
    
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
