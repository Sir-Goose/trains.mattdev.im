import httpx
from typing import Optional
from app.config import settings
from app.models.board import Board, Train, ServiceDetails
from app.middleware.cache import cache


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
    
    async def get_board(self, crs_code: str, use_cache: bool = True) -> Optional[Board]:
        """
        Get arrival and departure board for a station
        
        Args:
            crs_code: CRS station code (e.g., 'LHD' for Leatherhead)
            use_cache: Whether to use cached data if available
        
        Returns:
            Board object or None if error
        """
        crs_code = crs_code.upper()
        cache_key = f"board:{crs_code}"
        
        # Check cache first
        if use_cache:
            cached_board = cache.get(cache_key)
            if cached_board:
                return cached_board
        
        # Fetch from API using regular endpoint (not WithDetails) to get up to 150 trains
        # Details will be fetched on-demand for individual services
        url = f"{self.base_url}/GetArrivalDepartureBoard/{crs_code}"
        params = {
            "numRows": settings.rail_api_num_rows,
            "timeWindow": settings.rail_api_time_window,
            "timeOffset": 0  # Start from now
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url, headers=self._get_headers(), params=params)
                response.raise_for_status()
                
                data = response.json()
                
                # Check if data is valid
                if not data:
                    return None
                
                # Parse into Board model
                board = self._parse_board(data)
                
                # Cache the result
                cache.set(cache_key, board, self.cache_ttl)
                
                return board
                
            except httpx.HTTPStatusError as e:
                print(f"HTTP error fetching board for {crs_code}: {e.response.status_code}")
                return None
            except httpx.RequestError as e:
                print(f"Request error fetching board for {crs_code}: {e}")
                return None
            except Exception as e:
                print(f"Unexpected error fetching board for {crs_code}: {e}")
                return None
    
    def _parse_board(self, data: dict) -> Board:
        """Parse API response into Board model and cache service details"""
        # Extract train services if they exist
        train_services = data.get('trainServices', [])
        
        # Parse each train (service details will be fetched on-demand)
        trains = []
        for train_data in train_services:
            try:
                train = Train(**train_data)
                trains.append(train)
            except Exception as e:
                print(f"Error parsing train data: {e}")
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
