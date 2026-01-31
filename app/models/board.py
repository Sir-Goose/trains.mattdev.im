from typing import Optional, List
from pydantic import BaseModel, Field


class Location(BaseModel):
    """Location information for origin/destination"""
    locationName: str
    crs: str
    via: Optional[str] = None
    futureChangeTo: Optional[str] = None
    assocIsCancelled: Optional[bool] = None


class Train(BaseModel):
    """Train service information"""
    scheduled_arrival_time: Optional[str] = Field(None, alias='sta')
    estimated_arrival_time: Optional[str] = Field(None, alias='eta')
    scheduled_departure_time: Optional[str] = Field(None, alias='std')
    estimated_departure_time: Optional[str] = Field(None, alias='etd')
    origin: List[Location] = Field(default_factory=list)
    destination: List[Location] = Field(default_factory=list)
    platform: Optional[str] = Field(None)
    operator: Optional[str] = None
    operator_code: Optional[str] = Field(None, alias='operatorCode')
    service_id: Optional[str] = Field(None, alias='serviceID')
    service_type: Optional[str] = Field(None, alias='serviceType')  # Usually "train" or "bus"
    length: Optional[int] = Field(0)
    is_cancelled: bool = Field(False, alias='isCancelled')
    is_circular_route: bool = Field(False, alias='isCircularRoute')
    is_reverse_formation: bool = Field(False, alias='isReverseFormation')
    filter_location_cancelled: bool = Field(False, alias='filterLocationCancelled')
    future_cancellation: bool = Field(False, alias='futureCancellation')
    future_delay: bool = Field(False, alias='futureDelay')
    detach_front: bool = Field(False, alias='detachFront')
    delay_reason: Optional[str] = Field(None, alias='delayReason')
    cancel_reason: Optional[str] = Field(None, alias='cancelReason')
    
    class Config:
        populate_by_name = True
    
    @property
    def is_departing(self) -> bool:
        """Returns True if train has a scheduled departure time"""
        return self.scheduled_departure_time is not None
    
    @property
    def is_arriving(self) -> bool:
        """Returns True if train has a scheduled arrival time"""
        return self.scheduled_arrival_time is not None
    
    @property
    def is_passing_through(self) -> bool:
        """Returns True if train is both arriving and departing"""
        return self.is_arriving and self.is_departing
    
    @property
    def origin_name(self) -> Optional[str]:
        """Helper to get first origin's location name"""
        return self.origin[0].locationName if self.origin else None
    
    @property
    def destination_name(self) -> Optional[str]:
        """Helper to get first destination's location name"""
        return self.destination[0].locationName if self.destination else None
    
    @property
    def destination_via(self) -> Optional[str]:
        """Helper to get 'via' routing info if present"""
        return self.destination[0].via if self.destination else None
    
    @property
    def display_status(self) -> str:
        """Smart status string for display"""
        if self.is_cancelled:
            return "Cancelled"
        
        # For departures, prioritize etd
        if self.is_departing:
            if self.estimated_departure_time == "On time":
                return "On time"
            elif self.estimated_departure_time and self.estimated_departure_time != self.scheduled_departure_time:
                return f"Exp {self.estimated_departure_time}"
            return self.estimated_departure_time or "No information"
        
        # For arrivals, use eta
        if self.is_arriving:
            if self.estimated_arrival_time == "On time":
                return "On time"
            elif self.estimated_arrival_time and self.estimated_arrival_time != self.scheduled_arrival_time:
                return f"Exp {self.estimated_arrival_time}"
            return self.estimated_arrival_time or "No information"
        
        return "Unknown"


class Board(BaseModel):
    """Train station departure/arrival board"""
    location_name: Optional[str] = Field(None, alias='locationName')
    crs: Optional[str] = None
    generated_at: Optional[str] = Field(None, alias='generatedAt')
    filter_type: Optional[str] = Field(None, alias='filterType')  # Usually "to" or "from"
    platform_available: bool = Field(True, alias='platformAvailable')
    are_services_available: bool = Field(True, alias='areServicesAvailable')
    trains: List[Train] = Field(default_factory=list, alias='trainServices')
    nrcc_messages: Optional[List[dict]] = Field(None, alias='nrccMessages')
    
    class Config:
        populate_by_name = True
    
    @property
    def departures(self) -> List[Train]:
        """Returns only trains that are departing (have std)"""
        return [train for train in self.trains if train.is_departing]
    
    @property
    def arrivals(self) -> List[Train]:
        """Returns only trains that are arriving (have sta)"""
        return [train for train in self.trains if train.is_arriving]
    
    @property
    def passing_through(self) -> List[Train]:
        """Returns trains that are both arriving and departing"""
        return [train for train in self.trains if train.is_passing_through]


class BoardResponse(BaseModel):
    """API response wrapper for board data"""
    success: bool = True
    data: Optional[Board] = None
    error: Optional[str] = None
    cached: bool = False
