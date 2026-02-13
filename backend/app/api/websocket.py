"""WebSocket endpoint for real-time log streaming."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.database import SessionLocal
from app.models.test_run import TestRun, TestRunStatus

router = APIRouter()


@router.websocket("/test-runs/{test_run_id}/logs")
async def stream_logs(websocket: WebSocket, test_run_id: int):
    """Stream logs for a test run in real-time.

    Polls the database for new logs and sends them to the client.
    Closes when the test run is completed/failed/cancelled.
    """
    await websocket.accept()
    last_log_id = 0

    try:
        while True:
            db = SessionLocal()
            try:
                test_run = db.get(TestRun, test_run_id)
                if not test_run:
                    await websocket.send_json({"type": "error", "message": "Test run not found"})
                    break

                # Send new logs
                new_logs = [
                    log for log in test_run.logs if log.id > last_log_id
                ]
                for log in new_logs:
                    await websocket.send_json({
                        "type": "log",
                        "data": {
                            "id": log.id,
                            "timestamp": log.timestamp.isoformat(),
                            "log_line": log.log_line,
                            "level": log.level,
                        }
                    })
                    last_log_id = log.id

                # Send status update
                await websocket.send_json({
                    "type": "status",
                    "data": {
                        "status": test_run.status.value,
                        "total_tests": test_run.total_tests,
                        "passed_tests": test_run.passed_tests,
                        "failed_tests": test_run.failed_tests,
                    }
                })

                # Stop streaming if test is done
                if test_run.status in (
                    TestRunStatus.COMPLETED,
                    TestRunStatus.FAILED,
                    TestRunStatus.CANCELLED,
                ):
                    await websocket.send_json({"type": "done", "data": {"status": test_run.status.value}})
                    break
            finally:
                db.close()

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
