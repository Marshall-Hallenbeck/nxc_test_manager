"""Tests for the log-streaming WebSocket endpoint."""
from app.models.test_log import TestLog
from app.models.test_run import TestRun, TestRunStatus


def make_run(db, status=TestRunStatus.COMPLETED, log_lines=()):
    run = TestRun(target_hosts="10.0.0.1", status=status)
    db.add(run)
    db.commit()
    db.refresh(run)
    for line in log_lines:
        db.add(TestLog(test_run_id=run.id, log_line=line, level="INFO"))
    db.commit()
    return run


class TestLogStreaming:
    def test_sends_existing_logs_then_status_and_done(self, client, db):
        run = make_run(db, log_lines=["first line", "second line"])

        with client.websocket_connect(f"/ws/test-runs/{run.id}/logs") as ws:
            first = ws.receive_json()
            second = ws.receive_json()
            status = ws.receive_json()
            done = ws.receive_json()

        assert first["type"] == "log"
        assert first["data"]["log_line"] == "first line"
        assert second["data"]["log_line"] == "second line"
        assert status["type"] == "status"
        assert done["type"] == "done"
        assert done["data"]["status"] == "completed"

    def test_missing_run_reports_error(self, client):
        with client.websocket_connect("/ws/test-runs/999999/logs") as ws:
            msg = ws.receive_json()
        assert msg["type"] == "error"

    def test_only_new_logs_are_sent_on_each_poll(self, client, db, monkeypatch):
        """Regression: the endpoint read `test_run.logs`, loading every row for
        the run on every one-second poll and filtering in Python. A long run
        accumulating tens of thousands of lines re-read the whole table each
        second. Only rows newer than the last sent id should be queried.
        """
        from app.api import websocket as ws_module

        run = make_run(db, status=TestRunStatus.RUNNING, log_lines=["old one", "old two"])

        # Between the first and second poll, add one log line and finish the
        # run so the socket closes after the second pass.
        async def fake_sleep(seconds):
            assert seconds == 1
            db.add(TestLog(test_run_id=run.id, log_line="new line", level="INFO"))
            run.status = TestRunStatus.COMPLETED
            db.commit()

        monkeypatch.setattr(ws_module.asyncio, "sleep", fake_sleep)

        received = []
        with client.websocket_connect(f"/ws/test-runs/{run.id}/logs") as sock:
            while True:
                msg = sock.receive_json()
                if msg["type"] == "log":
                    received.append(msg["data"]["log_line"])
                if msg["type"] in ("done", "error"):
                    break

        assert received == ["old one", "old two", "new line"]
        assert received.count("old one") == 1, "already-sent logs must not be resent"
