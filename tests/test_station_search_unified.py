import pytest

from app.services import station_search


@pytest.mark.asyncio
async def test_unified_search_includes_nr_and_tfl(monkeypatch):
    monkeypatch.setattr(
        station_search,
        'search_stations',
        lambda query, limit=10: [{"stationName": "Leatherhead", "crsCode": "LHD"}],
    )

    async def fake_tfl_search(query: str, max_results: int = 8):
        return [
            {
                "provider": "tfl",
                "name": "Brixton Underground Station",
                "code": "940GZZLUBXN",
                "badge": "TfL Tube",
                "url": "/board/tfl/940GZZLUBXN/departures",
            }
        ]

    monkeypatch.setattr(station_search.tfl_api_service, 'search_stop_points', fake_tfl_search)

    results = await station_search.search_stations_unified("bri", view="departures", limit=10)

    assert any(result["provider"] == "nr" for result in results)
    assert any(result["provider"] == "tfl" for result in results)


@pytest.mark.asyncio
async def test_unified_search_maps_passing_to_tfl_departures(monkeypatch):
    monkeypatch.setattr(station_search, 'search_stations', lambda query, limit=10: [])

    async def fake_tfl_search(query: str, max_results: int = 8):
        return [{"provider": "tfl", "name": "Brixton", "code": "940GZZLUBXN", "badge": "TfL Tube", "url": ""}]

    monkeypatch.setattr(station_search.tfl_api_service, 'search_stop_points', fake_tfl_search)

    results = await station_search.search_stations_unified("bri", view="passing", limit=10)

    assert results[0]["url"].endswith("/departures")


@pytest.mark.asyncio
async def test_unified_search_ranks_waterloo_tfl_for_plain_waterloo_query(monkeypatch):
    monkeypatch.setattr(
        station_search,
        "search_stations",
        lambda query, limit=10: [
            {"stationName": "Waterloo", "crsCode": "WAT"},
            {"stationName": "London Waterloo", "crsCode": "WAT"},
            {"stationName": "Waterloo (Merseyside)", "crsCode": "WLO"},
        ],
    )

    async def fake_tfl_search(query: str, max_results: int = 8):
        return [
            {
                "provider": "tfl",
                "name": "Waterloo Underground Station",
                "code": "940GZZLUWLO",
                "badge": "TfL Tube",
                "url": "/board/tfl/940GZZLUWLO/departures",
            }
        ]

    monkeypatch.setattr(station_search.tfl_api_service, "search_stop_points", fake_tfl_search)

    results = await station_search.search_stations_unified("waterloo", view="departures", limit=10)

    assert results
    assert results[0]["provider"] == "tfl"
    assert results[0]["name"] == "Waterloo Underground Station"
