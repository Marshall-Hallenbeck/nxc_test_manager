"""Tests for API endpoints."""
from unittest.mock import patch
from app.models.test_run import TestRun, TestRunStatus


class TestCreateTestRun:
    @patch("app.api.test_runs.run_pr_test")
    def test_create_basic(self, mock_task, client, db):
        resp = client.post("/api/test-runs", json={"pr_number": 123})
        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_number"] == 123
        assert data["status"] == "queued"
        assert data["id"] is not None
        mock_task.delay.assert_called_once()

    @patch("app.api.test_runs.run_pr_test")
    def test_create_with_targets(self, mock_task, client, db):
        resp = client.post("/api/test-runs", json={
            "pr_number": 456,
            "target_hosts": "10.0.0.1,10.0.0.2",
            "target_username": "testuser",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["target_hosts"] == "10.0.0.1,10.0.0.2"
        assert data["target_username"] == "testuser"


class TestListTestRuns:
    @patch("app.api.test_runs.run_pr_test")
    def test_list_empty(self, mock_task, client):
        resp = client.get("/api/test-runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @patch("app.api.test_runs.run_pr_test")
    def test_list_with_runs(self, mock_task, client, db):
        # Create some test runs
        client.post("/api/test-runs", json={"pr_number": 1})
        client.post("/api/test-runs", json={"pr_number": 2})

        resp = client.get("/api/test-runs")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @patch("app.api.test_runs.run_pr_test")
    def test_filter_by_status(self, mock_task, client, db):
        client.post("/api/test-runs", json={"pr_number": 1})
        resp = client.get("/api/test-runs?status=queued")
        data = resp.json()
        assert data["total"] == 1

        resp = client.get("/api/test-runs?status=completed")
        data = resp.json()
        assert data["total"] == 0


class TestGetTestRun:
    @patch("app.api.test_runs.run_pr_test")
    def test_get_existing(self, mock_task, client, db):
        create_resp = client.post("/api/test-runs", json={"pr_number": 42})
        run_id = create_resp.json()["id"]

        resp = client.get(f"/api/test-runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_number"] == 42
        assert data["results"] == []

    def test_get_not_found(self, client):
        resp = client.get("/api/test-runs/99999")
        assert resp.status_code == 404


class TestCancelTestRun:
    @patch("app.api.test_runs.cancel_test_run", return_value=True)
    @patch("app.api.test_runs.run_pr_test")
    def test_cancel_queued(self, mock_task, mock_cancel, client, db):
        create_resp = client.post("/api/test-runs", json={"pr_number": 10})
        run_id = create_resp.json()["id"]

        resp = client.post(f"/api/test-runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_not_found(self, client):
        resp = client.post("/api/test-runs/99999/cancel")
        assert resp.status_code == 404


class TestDeleteTestRun:
    @patch("app.api.test_runs.run_pr_test")
    def test_delete_active_rejected(self, mock_task, client, db):
        create_resp = client.post("/api/test-runs", json={"pr_number": 10})
        run_id = create_resp.json()["id"]

        resp = client.delete(f"/api/test-runs/{run_id}")
        assert resp.status_code == 400  # Can't delete active run

    @patch("app.api.test_runs.run_pr_test")
    def test_delete_completed(self, mock_task, client, db):
        create_resp = client.post("/api/test-runs", json={"pr_number": 10})
        run_id = create_resp.json()["id"]

        # Manually mark as completed
        test_run = db.get(TestRun, run_id)
        test_run.status = TestRunStatus.COMPLETED
        db.commit()

        resp = client.delete(f"/api/test-runs/{run_id}")
        assert resp.status_code == 200

    def test_delete_not_found(self, client):
        resp = client.delete("/api/test-runs/99999")
        assert resp.status_code == 404


class TestHealthEndpoints:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
