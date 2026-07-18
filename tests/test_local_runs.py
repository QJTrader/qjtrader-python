from qjtrader.local_runs import clear_stop, get, list_runs, record, request_stop, stop_requested


def test_local_run_can_be_discovered_and_stopped(tmp_path):
    record("first", {"status": "running", "symbols": ["CA:RY"]}, root=tmp_path)
    assert get("first", root=tmp_path)["status"] == "running"
    assert list_runs(root=tmp_path)[0]["id"] == "first"
    assert request_stop("first", root=tmp_path)["status"] == "stop requested"
    assert stop_requested("first", root=tmp_path)
    clear_stop("first", root=tmp_path)
    assert not stop_requested("first", root=tmp_path)


def test_unknown_local_run_is_safe(tmp_path):
    assert "error" in request_stop("missing", root=tmp_path)
