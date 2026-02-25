import json
from pathlib import Path

import pytest

from app.tools import refresh_tfl_stations as tool


def test_extract_station_records_filters_modes_and_entrances():
    payload = {
        "stopPoints": [
            {
                "id": "940GZZLUWLO",
                "stationNaptan": "940GZZLUWLO",
                "commonName": "Waterloo Underground Station",
                "modes": ["tube"],
                "stopType": "NaptanMetroStation",
                "lat": 51.5036,
                "lon": -0.1143,
            },
            {
                "id": "4900ZZLUWLO1",
                "stationNaptan": "940GZZLUWLO",
                "commonName": "Waterloo",
                "modes": ["tube"],
                "stopType": "NaptanMetroEntrance",
            },
            {
                "id": "910GABCD",
                "commonName": "Some Bus Stop",
                "modes": ["bus"],
                "stopType": "NaptanPublicBusCoachTram",
            },
        ]
    }

    records = tool.extract_station_records(payload, ["tube", "overground"])

    assert len(records) == 1
    assert records[0]["id"] == "940GZZLUWLO"
    assert records[0]["name"] == "Waterloo Underground Station"


def test_extract_station_records_formats_dlr_station_names():
    payload = {
        "stopPoints": [
            {
                "id": "940GZZDLBOG",
                "stationNaptan": "940GZZDLBOG",
                "commonName": "Bow Church",
                "modes": ["dlr"],
                "stopType": "NaptanMetroStation",
            }
        ]
    }

    records = tool.extract_station_records(payload, ["tube", "overground", "dlr"])

    assert len(records) == 1
    assert records[0]["name"] == "Bow Church DLR Station"


@pytest.mark.asyncio
async def test_build_tfl_station_index_handles_paging_and_dedup():
    pages = {
        1: {
            "page": 1,
            "pageSize": 2,
            "total": 4,
            "stopPoints": [
                {
                    "id": "940GZZLUWLO",
                    "stationNaptan": "940GZZLUWLO",
                    "commonName": "Waterloo",
                    "modes": ["tube"],
                    "stopType": "NaptanMetroStation",
                },
                {
                    "id": "910GACTNCTL",
                    "stationNaptan": "910GACTNCTL",
                    "commonName": "Acton Central Rail Station",
                    "modes": ["overground"],
                    "stopType": "NaptanRailStation",
                },
            ],
        },
        2: {
            "page": 2,
            "pageSize": 2,
            "total": 4,
            "stopPoints": [
                {
                    "id": "940GZZLUWLO",
                    "stationNaptan": "940GZZLUWLO",
                    "commonName": "Waterloo Underground Station",
                    "modes": ["tube"],
                    "stopType": "NaptanMetroStation",
                },
                {
                    "id": "940GZZLUGPK",
                    "stationNaptan": "940GZZLUGPK",
                    "commonName": "Green Park Underground Station",
                    "modes": ["tube"],
                    "stopType": "NaptanMetroStation",
                },
            ],
        },
    }

    async def fetcher(page: int) -> dict:
        return pages.get(page, {"page": page, "pageSize": 2, "total": 4, "stopPoints": []})

    index = await tool.build_tfl_station_index(fetcher, ["tube", "overground"])

    assert len(index) == 3
    assert [item["name_normalized"] for item in index] == sorted(item["name_normalized"] for item in index)
    waterloo = next(item for item in index if item["id"] == "940GZZLUWLO")
    assert waterloo["name"] == "Waterloo Underground Station"


@pytest.mark.asyncio
async def test_refresh_tfl_stations_writes_sorted_output(monkeypatch, tmp_path: Path):
    output = tmp_path / "tfl_stations.json"

    async def fake_fetch_mode_page(client, base_url, modes, page, page_size=1000):
        if page == 1:
            return {
                "page": 1,
                "pageSize": 1000,
                "total": 2,
                "stopPoints": [
                    {
                        "id": "940GZZLUGPK",
                        "stationNaptan": "940GZZLUGPK",
                        "commonName": "Green Park Underground Station",
                        "modes": ["tube"],
                        "stopType": "NaptanMetroStation",
                    },
                    {
                        "id": "940GZZLUWLO",
                        "stationNaptan": "940GZZLUWLO",
                        "commonName": "Waterloo Underground Station",
                        "modes": ["tube"],
                        "stopType": "NaptanMetroStation",
                    },
                ],
            }
        return {"page": page, "pageSize": 1000, "total": 2, "stopPoints": []}

    monkeypatch.setattr(tool, "fetch_mode_page", fake_fetch_mode_page)

    total = await tool.refresh_tfl_stations(output_file=output, modes=["tube", "overground"])

    assert total == 2
    saved = json.loads(output.read_text())
    assert [item["id"] for item in saved] == ["940GZZLUGPK", "940GZZLUWLO"]
    assert all("name_normalized" in item for item in saved)
