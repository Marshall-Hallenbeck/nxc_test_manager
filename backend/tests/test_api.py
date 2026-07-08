"""Tests for API endpoints."""
from unittest.mock import patch
from app.models.test_run import TestRun, TestRunStatus


class TestTestRunClone:
    def test_clone_copies_configurable_fields(self, db):
        original = TestRun(
            pr_number=42,
            branch="my-branch",
            repo="user/repo",
            target_hosts="10.0.0.1",
            target_username="admin",
            target_password="secret",
            protocols="smb,winrm",
            kerberos=1,
            verbose=1,
            show_errors=1,
            ai_review_enabled=1,
            line_nums="1,2,3",
            not_tested=1,
            dns_server="8.8.8.8",
        )
        db.add(original)
        db.commit()
        db.refresh(original)

        cloned = original.clone()

        assert cloned.pr_number == 42
        assert cloned.branch == "my-branch"
        assert cloned.repo == "user/repo"
        assert cloned.target_hosts == "10.0.0.1"
        assert cloned.target_username == "admin"
        assert cloned.target_password == "secret"
        assert cloned.protocols == "smb,winrm"
        assert cloned.kerberos == 1
        assert cloned.verbose == 1
        assert cloned.show_errors == 1
        assert cloned.ai_review_enabled == 1
        assert cloned.line_nums == "1,2,3"
        assert cloned.not_tested == 1
        assert cloned.dns_server == "8.8.8.8"

    def test_clone_excludes_runtime_state(self, db):
        original = TestRun(target_hosts="10.0.0.1")
        db.add(original)
        db.commit()

        original.status = TestRunStatus.COMPLETED
        original.celery_task_id = "some-task-id"
        original.container_id = "abc123"
        original.total_tests = 5
        original.passed_tests = 3
        original.failed_tests = 2
        original.ai_summary = "Some review"
        original.ai_review_status = "completed"
        db.commit()

        cloned = original.clone()
        db.add(cloned)
        db.commit()
        db.refresh(cloned)

        assert cloned.id != original.id
        assert cloned.status == TestRunStatus.QUEUED
        assert cloned.celery_task_id is None
        assert cloned.container_id is None
        assert cloned.total_tests == 0
        assert cloned.passed_tests == 0
        assert cloned.failed_tests == 0
        assert cloned.ai_summary is None
        assert cloned.ai_review_status is None


class TestCreateTestRun:
    @patch("app.api.test_runs.run_pr_test")
    def test_create_basic(self, mock_task, client, db):
        resp = client.post("/api/runs", json={"pr_number": 123})
        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_number"] == 123
        assert data["status"] == "queued"
        assert data["id"] is not None
        mock_task.delay.assert_called_once()

    @patch("app.api.test_runs.run_pr_test")
    def test_create_with_targets(self, mock_task, client, db):
        resp = client.post("/api/runs", json={
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
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @patch("app.api.test_runs.run_pr_test")
    def test_list_with_runs(self, mock_task, client, db):
        # Create some test runs
        client.post("/api/runs", json={"pr_number": 1})
        client.post("/api/runs", json={"pr_number": 2})

        resp = client.get("/api/runs")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @patch("app.api.test_runs.run_pr_test")
    def test_filter_by_status(self, mock_task, client, db):
        client.post("/api/runs", json={"pr_number": 1})
        resp = client.get("/api/runs?status=queued")
        data = resp.json()
        assert data["total"] == 1

        resp = client.get("/api/runs?status=completed")
        data = resp.json()
        assert data["total"] == 0


class TestGetTestRun:
    @patch("app.api.test_runs.run_pr_test")
    def test_get_existing(self, mock_task, client, db):
        create_resp = client.post("/api/runs", json={"pr_number": 42})
        run_id = create_resp.json()["id"]

        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pr_number"] == 42
        assert data["results"] == []

    def test_get_not_found(self, client):
        resp = client.get("/api/runs/99999")
        assert resp.status_code == 404


class TestCancelTestRun:
    @patch("app.api.test_runs.cancel_test_run", return_value=True)
    @patch("app.api.test_runs.run_pr_test")
    def test_cancel_queued(self, mock_task, mock_cancel, client, db):
        create_resp = client.post("/api/runs", json={"pr_number": 10})
        run_id = create_resp.json()["id"]

        resp = client.post(f"/api/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_cancel_not_found(self, client):
        resp = client.post("/api/runs/99999/cancel")
        assert resp.status_code == 404


class TestDeleteTestRun:
    @patch("app.api.test_runs.run_pr_test")
    def test_delete_active_rejected(self, mock_task, client, db):
        create_resp = client.post("/api/runs", json={"pr_number": 10})
        run_id = create_resp.json()["id"]

        resp = client.delete(f"/api/runs/{run_id}")
        assert resp.status_code == 400  # Can't delete active run

    @patch("app.api.test_runs.run_pr_test")
    def test_delete_completed(self, mock_task, client, db):
        create_resp = client.post("/api/runs", json={"pr_number": 10})
        run_id = create_resp.json()["id"]

        # Manually mark as completed
        test_run = db.get(TestRun, run_id)
        test_run.status = TestRunStatus.COMPLETED
        db.commit()

        resp = client.delete(f"/api/runs/{run_id}")
        assert resp.status_code == 200

    def test_delete_not_found(self, client):
        resp = client.delete("/api/runs/99999")
        assert resp.status_code == 404


class TestRerunTestRun:
    @patch("app.api.test_runs.run_pr_test")
    def test_rerun_clones_settings(self, mock_task, client, db):
        resp = client.post("/api/runs", json={
            "pr_number": 42,
            "target_hosts": "10.0.0.1",
            "target_username": "admin",
            "target_password": "secret",
            "verbose": True,
            "kerberos": True,
        })
        run_id = resp.json()["id"]

        resp = client.post(f"/api/runs/{run_id}/rerun")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] != run_id
        assert data["pr_number"] == 42
        assert data["target_hosts"] == "10.0.0.1"
        assert data["target_username"] == "admin"
        assert data["status"] == "queued"
        assert data["kerberos"] is True
        assert data["verbose"] is True
        assert "target_password" not in data

    @patch("app.api.test_runs.run_pr_test")
    def test_rerun_dispatches_celery_task(self, mock_task, client, db):
        resp = client.post("/api/runs", json={"pr_number": 10})
        run_id = resp.json()["id"]

        client.post(f"/api/runs/{run_id}/rerun")
        assert mock_task.delay.call_count == 2  # original + rerun

    def test_rerun_not_found(self, client):
        resp = client.post("/api/runs/99999/rerun")
        assert resp.status_code == 404


class TestCompareTestRuns:
    @patch("app.api.test_runs.run_pr_test")
    def test_compare_reachable(self, mock_task, client, db):
        """Verify /compare is not shadowed by /{test_run_id}."""
        r1 = client.post("/api/runs", json={"pr_number": 1})
        r2 = client.post("/api/runs", json={"pr_number": 2})
        id1 = r1.json()["id"]
        id2 = r2.json()["id"]

        resp = client.get(f"/api/runs/compare?run1={id1}&run2={id2}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run1"]["pr_number"] == 1
        assert data["run2"]["pr_number"] == 2

    def test_compare_not_found(self, client):
        resp = client.get("/api/runs/compare?run1=999&run2=998")
        assert resp.status_code == 404


class TestPasswordNotInResponse:
    @patch("app.api.test_runs.run_pr_test")
    def test_create_response_excludes_password(self, mock_task, client, db):
        resp = client.post("/api/runs", json={
            "pr_number": 1,
            "target_password": "supersecret",
        })
        assert resp.status_code == 200
        assert "target_password" not in resp.json()

    @patch("app.api.test_runs.run_pr_test")
    def test_detail_response_excludes_password(self, mock_task, client, db):
        resp = client.post("/api/runs", json={
            "pr_number": 1,
            "target_password": "supersecret",
        })
        run_id = resp.json()["id"]
        resp = client.get(f"/api/runs/{run_id}")
        assert resp.status_code == 200
        assert "target_password" not in resp.json()


class TestHealthEndpoints:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "claude_available" in data
        assert "claude_unavailable_reason" in data
