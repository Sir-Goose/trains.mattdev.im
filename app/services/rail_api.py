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
        
        # Fetch from API using WithDetails endpoint to get calling points
        url = f"{self.base_url}/GetArrDepBoardWithDetails/{crs_code}"
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
        
        # Parse each train and cache its service details
        trains = []
        for train_data in train_services:
            try:
                train = Train(**train_data)
                trains.append(train)
                
                # Cache this train's service details for the service detail page
                if train.service_id:
                    service_details = self._train_to_service_details(train, data)
                    cache.set(f"service:{train.service_id}", service_details, 120)  # Cache for 2 minutes
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
    
    def _train_to_service_details(self, train: Train, board_data: dict) -> ServiceDetails:
        """Convert a Train object to ServiceDetails for the service detail page"""
        return ServiceDetails(
            generatedAt=board_data.get('generatedAt', ''),
            serviceType=train.service_type or 'train',
            locationName=board_data.get('locationName', ''),
            crs=board_data.get('crs', ''),
            operator=train.operator or 'Unknown',
            operatorCode=train.operator_code or '',
            rsid=train.rsid,
            serviceID=train.service_id or '',
            platform=train.platform,
            isCancelled=train.is_cancelled,
            cancelReason=train.cancel_reason,
            delayReason=train.delay_reason,
            length=train.length if train.length and train.length > 0 else None,
            isReverseFormation=train.is_reverse_formation,
            sta=train.scheduled_arrival_time,
            eta=train.estimated_arrival_time,
            std=train.scheduled_departure_time,
            etd=train.estimated_departure_time,
            origin=train.origin,
            destination=train.destination,
            previousCallingPoints=train.previous_calling_points,
            subsequentCallingPoints=train.subsequent_calling_points
        )
    
    def clear_cache(self, crs_code: Optional[str] = None) -> None:
        """Clear cache for a specific station or all stations"""
        if crs_code:
            cache.delete(f"board:{crs_code.upper()}")
        else:
            cache.clear()
    
    async def get_service_details(self, service_id: str, use_cache: bool = True) -> Optional[ServiceDetails]:
        """
        Get detailed information about a specific train service from cache.
        Service details are cached when fetching the board with the WithDetails endpoint.
        
        Args:
            service_id: The unique service identifier from the board
            use_cache: Whether to use cached data if available (always True for this implementation)
        
        Returns:
            ServiceDetails object or None if service has expired from cache
        """
        cache_key = f"service:{service_id}"
        
        # Check cache - service details are stored when fetching board data
        cached_service = cache.get(cache_key)
        if cached_service:
            return cached_service
        
        # Service not in cache - it has likely expired (services only available for ~2 minutes after departure)
        print(f"Service {service_id} not found in cache - may have expired")
        return None


# Global service instance
rail_api_service = RailAPIService()
