from __future__ import annotations
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
    """Train service information (from WithDetails endpoint)"""
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
    rsid: Optional[str] = Field(None, alias='rsid')  # Retail Service ID
    # Calling points from WithDetails endpoint
    previous_calling_points: Optional[List[CallingPointList]] = Field(default_factory=list, alias='previousCallingPoints')
    subsequent_calling_points: Optional[List[CallingPointList]] = Field(default_factory=list, alias='subsequentCallingPoints')
    
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
        via = self.destination[0].via if self.destination else None
        if not via:
            return None

        cleaned = via.strip()
        if cleaned.lower().startswith("via "):
            cleaned = cleaned[4:].lstrip()

        return cleaned or None
    
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
    
    @property
    def display_time_departure(self) -> str:
        """Smart departure time display with status indicator"""
        if not self.scheduled_departure_time:
            return "N/A"
        
        scheduled = self.scheduled_departure_time
        estimated = self.estimated_departure_time
        
        if self.is_cancelled:
            return scheduled  # Template will add strikethrough + badge
        elif estimated == "On time" or not estimated:
            return scheduled
        else:
            return f"{scheduled} → {estimated}"
    
    @property
    def display_time_arrival(self) -> str:
        """Smart arrival time display with status indicator"""
        if not self.scheduled_arrival_time:
            return "N/A"
        
        scheduled = self.scheduled_arrival_time
        estimated = self.estimated_arrival_time
        
        if self.is_cancelled:
            return scheduled  # Template will add strikethrough + badge
        elif estimated == "On time" or not estimated:
            return scheduled
        else:
            return f"{scheduled} → {estimated}"
    
    @property
    def time_status_class(self) -> str:
        """CSS class for time status styling"""
        if self.is_cancelled:
            return "time-cancelled"
        
        # Check if delayed (for either departure or arrival)
        if self.estimated_departure_time and self.estimated_departure_time not in ["On time", self.scheduled_departure_time]:
            return "time-delayed"
        
        if self.estimated_arrival_time and self.estimated_arrival_time not in ["On time", self.scheduled_arrival_time]:
            return "time-delayed"
        
        return "time-ontime"


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


class CallingPoint(BaseModel):
    """A single station stop on a train's route"""
    locationName: str
    crs: str
    st: str  # Scheduled time "18:35"
    et: str = "On time"  # Estimated time "18:40" or "On time"
    at: Optional[str] = None  # Actual time (if train has passed) "18:39"
    pta: Optional[str] = None  # Planned time of arrival
    eta: Optional[str] = None  # Estimated time of arrival
    ata: Optional[str] = None  # Actual time of arrival
    isCancelled: Optional[bool] = False
    length: Optional[int] = None
    detachFront: Optional[bool] = False
    
    @property
    def has_passed(self) -> bool:
        """Check if train has already been through this station"""
        return self.at is not None or self.ata is not None
    
    @property
    def display_time(self) -> str:
        """Get the best available time to display"""
        # For arrivals, prioritize: actual > estimated > planned/scheduled
        if self.ata:
            return self.ata
        if self.eta and self.eta != "On time":
            return self.eta
        if self.pta:
            return self.pta
        
        # For departures, prioritize: actual > estimated > scheduled
        if self.at:
            return self.at
        if self.et and self.et != "On time":
            return self.et
        return self.st
    
    @property
    def is_delayed(self) -> bool:
        """Check if this stop is delayed"""
        if self.et and self.et not in ["On time", self.st, "Delayed", "Cancelled"]:
            return True
        if self.eta and self.eta not in ["On time", self.pta or self.st, "Delayed", "Cancelled"]:
            return True
        return False
    
    @property
    def status_class(self) -> str:
        """CSS class for time status"""
        if self.isCancelled:
            return "status-cancelled"
        if self.has_passed:
            return "status-passed"
        if self.is_delayed:
            return "status-delayed"
        return "status-ontime"


class CallingPointList(BaseModel):
    """Group of calling points (can have multiple for split services)"""
    callingPoint: List[CallingPoint]
    serviceType: Optional[str] = "train"
    serviceChangeRequired: Optional[bool] = False
    assocIsCancelled: Optional[bool] = False


class ServiceDetails(BaseModel):
    """Detailed information about a specific train service"""
    generatedAt: str
    serviceType: str = "train"  # "train" or "bus"
    locationName: str  # Station name
    crs: str  # Station CRS
    operator: str  # "South Western Railway"
    operatorCode: str  # "SW"
    rsid: Optional[str] = None  # Retail Service ID
    
    # Times at current station
    sta: Optional[str] = None  # Scheduled arrival
    eta: Optional[str] = None  # Estimated arrival
    ata: Optional[str] = None  # Actual arrival
    std: Optional[str] = None  # Scheduled departure
    etd: Optional[str] = None  # Estimated departure
    atd: Optional[str] = None  # Actual departure
    
    # Service info
    platform: Optional[str] = None
    isCancelled: bool = False
    filterLocationName: Optional[str] = None
    cancelReason: Optional[str] = None
    delayReason: Optional[str] = None
    serviceID: str
    
    # Journey endpoints
    origin: List[Location]
    destination: List[Location]
    currentOrigins: Optional[List[Location]] = Field(default_factory=list)
    currentDestinations: Optional[List[Location]] = Field(default_factory=list)
    
    # Calling points
    previousCallingPoints: Optional[List[CallingPointList]] = Field(default_factory=list)
    subsequentCallingPoints: Optional[List[CallingPointList]] = Field(default_factory=list)
    
    # Additional service info
    length: Optional[int] = None  # Number of coaches
    detachFront: Optional[bool] = False
    isReverseFormation: Optional[bool] = False
    
    class Config:
        populate_by_name = True
    
    @property
    def all_previous_stops(self) -> List[CallingPoint]:
        """Flatten previous calling points into a single list"""
        if not self.previousCallingPoints:
            return []
        stops = []
        for cpl in self.previousCallingPoints:
            stops.extend(cpl.callingPoint)
        return stops
    
    @property
    def all_subsequent_stops(self) -> List[CallingPoint]:
        """Flatten subsequent calling points into a single list"""
        if not self.subsequentCallingPoints:
            return []
        stops = []
        for cpl in self.subsequentCallingPoints:
            stops.extend(cpl.callingPoint)
        return stops
    
    @property
    def origin_name(self) -> str:
        """Get origin station name"""
        if self.currentOrigins and len(self.currentOrigins) > 0:
            return self.currentOrigins[0].locationName
        return self.origin[0].locationName if self.origin else "Unknown"
    
    @property
    def destination_name(self) -> str:
        """Get destination station name"""
        if self.currentDestinations and len(self.currentDestinations) > 0:
            return self.currentDestinations[0].locationName
        return self.destination[0].locationName if self.destination else "Unknown"
