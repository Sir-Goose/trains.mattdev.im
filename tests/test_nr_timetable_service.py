from pathlib import Path
import zipfile

from app.services.nr_timetable import NRTimetableService, ServiceLookupHint


def _bs_line(uid: str, start: str, end: str, days: str = "1111111", train_status: str = "1") -> str:
    line = [" "] * 80
    line[0:2] = list("BS")
    line[2] = "N"
    line[3:9] = list(uid.ljust(6)[:6])
    line[9:15] = list(start)
    line[15:21] = list(end)
    line[21:28] = list(days)
    line[29] = train_status
    line[79] = "N"
    return "".join(line)


def _bx_line(operator_code: str) -> str:
    line = [" "] * 80
    line[0:2] = list("BX")
    line[11:13] = list(operator_code.ljust(2)[:2])
    return "".join(line)


def _lo_line(tiploc: str, dep: str, pub_dep: str) -> str:
    line = [" "] * 80
    line[0:2] = list("LO")
    line[2:9] = list(tiploc.ljust(7)[:7])
    line[10:15] = list(dep.ljust(5)[:5])
    line[15:19] = list(pub_dep.ljust(4)[:4])
    return "".join(line)


def _li_line(tiploc: str, arr: str, dep: str, pub_arr: str, pub_dep: str) -> str:
    line = [" "] * 80
    line[0:2] = list("LI")
    line[2:9] = list(tiploc.ljust(7)[:7])
    line[10:15] = list(arr.ljust(5)[:5])
    line[15:20] = list(dep.ljust(5)[:5])
    line[25:29] = list(pub_arr.ljust(4)[:4])
    line[29:33] = list(pub_dep.ljust(4)[:4])
    return "".join(line)


def _lt_line(tiploc: str, arr: str, pub_arr: str) -> str:
    line = [" "] * 80
    line[0:2] = list("LT")
    line[2:9] = list(tiploc.ljust(7)[:7])
    line[10:15] = list(arr.ljust(5)[:5])
    line[15:19] = list(pub_arr.ljust(4)[:4])
    return "".join(line)


def _msn_line(name: str, tiploc: str, crs: str) -> str:
    line = [" "] * 80
    line[0] = "A"
    line[5:35] = list(name.ljust(30)[:30])
    line[35] = "2"
    line[36:43] = list(tiploc.ljust(7)[:7])
    line[43:46] = list(crs.ljust(3)[:3])
    line[49:52] = list(crs.ljust(3)[:3])
    return "".join(line)


def _write_fixture_zip(path: Path) -> None:
    msn_lines = [
        _msn_line("GUILDFORD", "GUILDFD", "GLD"),
        _msn_line("LEATHERHEAD", "LETHRHD", "LHD"),
        _msn_line("LONDON WATERLOO", "WATRLMN", "WAT"),
        _msn_line("DORKING", "DORKING", "DKG"),
        _msn_line("LONDON VICTORIA", "VICTRIC", "VIC"),
    ]

    mca_lines = [
        _bs_line("TRN001", "260301", "260331"),
        _bx_line("SW"),
        _lo_line("GUILDFD", "2050", "2050"),
        _li_line("LETHRHD", "2110", "2110", "2110", "2110"),
        _lt_line("WATRLMN", "2140", "2140"),
        _bs_line("TRN002", "260301", "260331"),
        _bx_line("SN"),
        _lo_line("DORKING", "2055", "2055"),
        _li_line("LETHRHD", "2110", "2110", "2110", "2110"),
        _lt_line("VICTRIC", "2145", "2145"),
    ]

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("TESTMSN.TXT", "\n".join(msn_lines) + "\n")
        zf.writestr("TESTMCA.TXT", "\n".join(mca_lines) + "\n")


def test_timetable_service_matches_best_schedule(tmp_path):
    zip_path = tmp_path / "timetable_full.zip"
    _write_fixture_zip(zip_path)
    service = NRTimetableService(zip_path=str(zip_path), enabled=True)

    detail = service.find_service_detail(
        service_id="service-123",
        requested_crs="LHD",
        hint=ServiceLookupHint(
            crs="LHD",
            scheduled_arrival_time="21:10",
            scheduled_departure_time="21:10",
            origin_crs="GLD",
            destination_crs="WAT",
            operator_code="SW",
            operator_name="South Western Railway",
            generated_at="2026-03-02T20:30:00+00:00",
            service_type="train",
        ),
    )

    assert detail is not None
    assert detail.locationName == "LEATHERHEAD"
    assert detail.crs == "LHD"
    assert detail.origin[0].crs == "GLD"
    assert detail.destination[0].crs == "WAT"
    assert detail.std == "21:10"
    assert detail.sta == "21:10"
    assert detail.operatorCode == "SW"
    assert len(detail.all_previous_stops) == 1
    assert len(detail.all_subsequent_stops) == 1


def test_timetable_service_returns_none_when_source_missing(tmp_path):
    service = NRTimetableService(zip_path=str(tmp_path / "missing.zip"), enabled=True)
    detail = service.find_service_detail(
        service_id="service-123",
        requested_crs="LHD",
        hint=ServiceLookupHint(crs="LHD"),
    )
    assert detail is None


def test_timetable_service_builds_sqlite_index_and_reuses_it(tmp_path):
    zip_path = tmp_path / "timetable_full.zip"
    work_dir = tmp_path / "work"
    _write_fixture_zip(zip_path)
    service = NRTimetableService(zip_path=str(zip_path), enabled=True, work_dir=str(work_dir))

    hint = ServiceLookupHint(
        crs="LHD",
        scheduled_arrival_time="21:10",
        scheduled_departure_time="21:10",
        origin_crs="GLD",
        destination_crs="WAT",
        operator_code="SW",
        operator_name="South Western Railway",
        generated_at="2026-03-02T20:30:00+00:00",
        service_type="train",
    )

    first = service.find_service_detail("service-123", "LHD", hint)
    second = service.find_service_detail("service-123", "LHD", hint)

    assert first is not None
    assert second is not None

    sqlite_files = list(work_dir.glob("nr_timetable.*.sqlite3"))
    assert len(sqlite_files) == 1
    assert sqlite_files[0].stat().st_size > 0


def test_prebuild_index_returns_ready_metadata(tmp_path):
    zip_path = tmp_path / "timetable_full.zip"
    work_dir = tmp_path / "work"
    _write_fixture_zip(zip_path)
    service = NRTimetableService(zip_path=str(zip_path), enabled=True, work_dir=str(work_dir))

    result = service.prebuild_index()

    assert result["status"] == "ok"
    assert result["mca_member"] == "TESTMCA.TXT"
    assert result["msn_member"] == "TESTMSN.TXT"
    assert int(result["tiploc_count"]) >= 5
    assert Path(str(result["index_path"])).exists()
