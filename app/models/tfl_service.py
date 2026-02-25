from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TflServiceStop(BaseModel):
    stop_id: str
    stop_name: str
    eta_minutes: Optional[int] = None
    eta_time: Optional[str] = None
    arrival_display: str = "No estimate"
    departure_display: str = "No estimate"
    is_current: bool = False
    is_destination: bool = False


class TflServiceDetail(BaseModel):
    line_id: str
    line_name: str
    direction: Optional[str] = None
    from_stop_id: str
    to_stop_id: str
    origin_name: str
    destination_name: str
    resolution_mode: Literal["exact", "fallback"] = "fallback"
    mode_name: str = "tube"
    station_name: Optional[str] = None
    vehicle_id: Optional[str] = None
    trip_id: Optional[str] = None
    expected_arrival: Optional[str] = None
    pulled_at: Optional[str] = Field(None, alias="pulledAt")
    stops: list[TflServiceStop] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
