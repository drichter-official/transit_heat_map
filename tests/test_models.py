from backend.models import HeatmapPoint, JobRecord, Stop, StopTime, Transfer, TripStop


def test_stop_time_and_trip_stop_fields_are_numeric():
    stop_time = StopTime(
        trip_id="trip-1",
        stop_id="stop-a",
        arrival_sec=8 * 3600 + 60,
        departure_sec=8 * 3600 + 120,
        stop_sequence=2,
    )
    trip_stop = TripStop(
        trip_id="trip-1",
        stop_id="stop-b",
        arrival_sec=8 * 3600 + 600,
        departure_sec=8 * 3600 + 660,
        stop_sequence=3,
    )

    assert stop_time.departure_sec == 28920
    assert trip_stop.arrival_sec == 29400


def test_shared_models_hold_api_shapes():
    stop = Stop(id="8503000", name="Zurich HB", lat=47.378, lon=8.54)
    transfer = Transfer(to_stop_id="8503001", transfer_time_sec=120)
    point = HeatmapPoint(lat=47.378, lng=8.54, weight=0.8)
    job = JobRecord(id="hm_test", status="running")

    assert stop.name == "Zurich HB"
    assert transfer.transfer_time_sec == 120
    assert point.weight == 0.8
    assert job.status == "running"
