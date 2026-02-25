from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class TflPrediction(BaseModel):
    """TfL arrival prediction for a stop point."""

    id: Optional[str] = None
    naptan_id: Optional[str] = Field(None, alias="naptanId")
    station_name: Optional[str] = Field(None, alias="stationName")
    line_id: Optional[str] = Field(None, alias="lineId")
    line_name: Optional[str] = Field(None, alias="lineName")
    platform_name: Optional[str] = Field(None, alias="platformName")
    direction: Optional[str] = None
    mode_name: Optional[str] = Field(None, alias="modeName")
    trip_id: Optional[str] = Field(None, alias="tripId")
    vehicle_id: Optional[str] = Field(None, alias="vehicleId")
    destination_name: Optional[str] = Field(None, alias="destinationName")
    destination_naptan_id: Optional[str] = Field(None, alias="destinationNaptanId")
    towards: Optional[str] = None
    current_location: Optional[str] = Field(None, alias="currentLocation")
    expected_arrival: Optional[datetime] = Field(None, alias="expectedArrival")
    timestamp: Optional[datetime] = None
    time_to_station: Optional[int] = Field(None, alias="timeToStation")

    model_config = {"populate_by_name": True}

    @property
    def expected_arrival_hhmm(self) -> str:
        if not self.expected_arrival:
            return "No information"
        return self.expected_arrival.astimezone(timezone.utc).strftime("%H:%M")


class TflLineStatusSummary(BaseModel):
    """Compact line status for board display."""

    line_id: str
    line_name: str
    status_severity: Optional[int] = None
    status_description: Optional[str] = None
    reason: Optional[str] = None


class TflBoard(BaseModel):
    """TfL board payload for a stop point."""

    stop_point_id: str
    station_name: str
    generated_at: Optional[str] = None
    pulled_at: Optional[str] = None
    trains: list[TflPrediction] = Field(default_factory=list)
    line_status: list[TflLineStatusSummary] = Field(default_factory=list)


class TflBoardResponse(BaseModel):
    """API response wrapper for TfL board data."""

    success: bool = True
    data: Optional[TflBoard] = None
    error: Optional[str] = None
    cached: bool = False
