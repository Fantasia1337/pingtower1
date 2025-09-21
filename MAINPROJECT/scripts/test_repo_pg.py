import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.append(str(Path(__file__).parent.parent))

from app.db.models import Base, engine, Incident
from app.db.repo import (
    create_service,
    list_services,
    insert_check_result,
    get_last_status,
    get_history,
    uptime_24h,
    avg_latency_24h,
    avg_latency_24h_int,
    get_open_incident,
    open_incident,
    close_incident,
    get_last_n_results,
    uptime_,
    avg_latency_,
    delete_service,
)


def setup_module():
    """Create database tables before running tests."""
    Base.metadata.create_all(engine)


def teardown_module():
    """Drop database tables after tests complete."""
    Base.metadata.drop_all(engine)


def test_repository_functions():
    """Test the core repository functions with a PostgreSQL database."""
    # 1. Create a new service
    service = create_service(
        name="Test Service", url="http://example.com", interval_s=60, timeout_s=10
    )
    assert service is not None
    assert service.id is not None
    assert service.name == "Test Service"
    assert service.url == "http://example.com"

    # 2. Verify service appears in list_services
    services = list_services()
    assert len(services) == 1
    assert services[0].id == service.id
    assert services[0].name == "Test Service"

    # 3. Add three check results with different timestamps
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    two_hours_ago = now - timedelta(hours=2)

    # Insert check results in reverse chronological order to test ordering
    insert_check_result(
        service_id=service.id,
        ts=two_hours_ago,
        ok=True,
        status_code=200,
        latency_ms=150,
        error_text="Initial check successful",
    )

    insert_check_result(
        service_id=service.id,
        ts=one_hour_ago,
        ok=False,
        status_code=500,
        latency_ms=None,
        error_text="Server error occurred",
    )

    insert_check_result(
        service_id=service.id,
        ts=now,
        ok=True,
        status_code=200,
        latency_ms=200,
        error_text="Latest check successful",
    )

    # 4a. Test get_last_status - should return the most recent check
    last_status = get_last_status(service.id)
    assert last_status is not None
    assert last_status["ts"] == now
    assert last_status["ok"] is True
    assert last_status["status_code"] == 200
    assert last_status["latency_ms"] == 200
    assert "Latest check successful" in last_status["error_text"]

    # 4b. Test get_history with limit=2 - should return 2 most recent
    history_limit2 = get_history(service.id, limit=2)
    assert len(history_limit2) == 2
    assert history_limit2[0]["ts"] == now  # Most recent first
    assert history_limit2[1]["ts"] == one_hour_ago
    assert history_limit2[0]["ok"] is True
    assert history_limit2[1]["ok"] is False

    # 4c. Test get_history with limit=3 - should return all 3
    history_limit3 = get_history(service.id, limit=3)
    assert len(history_limit3) == 3
    assert history_limit3[0]["ts"] == now
    assert history_limit3[1]["ts"] == one_hour_ago
    assert history_limit3[2]["ts"] == two_hours_ago
    assert history_limit3[2]["ok"] is True

    uptime = uptime_24h(service.id)
    assert 0 <= uptime <= 1
    assert uptime == 2 / 3  # 2 successful out of 3 checks

    avg_latency = avg_latency_24h(service.id)
    assert avg_latency == 175.0  # (150 + 200) / 2
    assert avg_latency_24h_int(service.id) == 175

    # windowed helpers
    assert uptime_(service.id, timedelta(hours=3)) >= 0
    assert avg_latency_(service.id, timedelta(hours=3)) in (150, 175, 200)

    # incidents
    assert get_open_incident(service.id) is None
    started = datetime.now(timezone.utc)
    incident = open_incident(service.id, started, fail_count=3)
    assert incident is not None and incident.id is not None and incident.is_open
    assert get_open_incident(service.id) is not None
    ended = datetime.now(timezone.utc)
    close_incident(incident.id, ended)
    assert get_open_incident(service.id) is None
    # verify closed state
    from app.db.models import SessionLocal as _SL

    with _SL() as s:
        db_inc = s.query(Incident).filter(Incident.id == incident.id).first()
        assert db_inc is not None and (not db_inc.is_open) and db_inc.closed_at == ended

    # get_last_n_results
    last2 = get_last_n_results(service.id, 2)
    assert len(last2) == 2 and last2[0].ts == now

    # delete service (cascade)
    delete_service(service.id)
    services = list_services()
    assert len(services) == 0


if __name__ == "__main__":
    setup_module()
    try:
        test_repository_functions()
        print("All tests passed successfully!")
    finally:
        teardown_module()
