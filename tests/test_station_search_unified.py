import pytest

from app.services import station_search


@pytest.mark.asyncio
async def test_unified_search_includes_nr_and_tfl(monkeypatch):
    monkeypatch.setattr(
        station_search,
        'search_stations',
        lambda query, limit=10: [{"stationName": "Leatherhead", "crsCode": "LHD"}],
    )

    def fake_tfl_search(query: str, limit: int = 10):
        return [
            {
                "provider": "tfl",
                "name": "Brixton Underground Station",
                "code": "940GZZLUBXN",
                "badge": "TfL Tube",
                "url": "/board/tfl/940GZZLUBXN/departures",
            }
        ]

    monkeypatch.setattr(station_search, "search_tfl_stations_local", fake_tfl_search)

    results = await station_search.search_stations_unified("bri", view="departures", limit=10)

    assert any(result["provider"] == "nr" for result in results)
    assert any(result["provider"] == "tfl" for result in results)


@pytest.mark.asyncio
async def test_unified_search_maps_passing_to_tfl_departures(monkeypatch):
    monkeypatch.setattr(station_search, 'search_stations', lambda query, limit=10: [])

    def fake_tfl_search(query: str, limit: int = 10):
        return [{"provider": "tfl", "name": "Brixton", "code": "940GZZLUBXN", "badge": "TfL Tube", "url": ""}]

    monkeypatch.setattr(station_search, "search_tfl_stations_local", fake_tfl_search)

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

    def fake_tfl_search(query: str, limit: int = 10):
        return [
            {
                "provider": "tfl",
                "name": "Waterloo Underground Station",
                "code": "940GZZLUWLO",
                "badge": "TfL Tube",
                "url": "/board/tfl/940GZZLUWLO/departures",
            }
        ]

    monkeypatch.setattr(station_search, "search_tfl_stations_local", fake_tfl_search)

    results = await station_search.search_stations_unified("waterloo", view="departures", limit=10)

    assert results
    assert results[0]["provider"] == "tfl"
    assert results[0]["name"] == "Waterloo Underground Station"


def test_search_tfl_stations_local_fallback_on_missing_file(monkeypatch):
    station_search.load_tfl_stations.cache_clear()
    monkeypatch.setattr(station_search, "TFL_STATIONS_FILE", station_search.Path("/tmp/no_such_tfl_stations_file.json"))

    results = station_search.search_tfl_stations_local("waterloo", limit=10)

    assert results == []


def test_search_tfl_stations_local_fallback_on_invalid_json(monkeypatch, tmp_path):
    bad_file = tmp_path / "tfl_stations.json"
    bad_file.write_text("{ not valid json")
    station_search.load_tfl_stations.cache_clear()
    monkeypatch.setattr(station_search, "TFL_STATIONS_FILE", bad_file)

    results = station_search.search_tfl_stations_local("waterloo", limit=10)

    assert results == []


def test_search_tfl_stations_local_ranks_waterloo_with_plain_query(monkeypatch):
    monkeypatch.setattr(
        station_search,
        "load_tfl_stations",
        lambda: [
            {"id": "940GZZLUWRR", "name": "Warren Street Underground Station", "modes": ["tube"]},
            {"id": "940GZZLUWLO", "name": "Waterloo", "modes": ["tube"]},
            {"id": "910GACTNCTL", "name": "Acton Central Rail Station", "modes": ["overground"]},
        ],
    )

    results = station_search.search_tfl_stations_local("waterloo", limit=5)

    assert results
    assert results[0]["code"] == "940GZZLUWLO"
    assert results[0]["name"] == "Waterloo Underground Station"
