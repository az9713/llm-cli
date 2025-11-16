"""Tests for Scheduled Prompts feature."""
import pytest
from llm.scheduler import Scheduler


@pytest.fixture
def scheduler(user_path):
    """Create a Scheduler instance."""
    db_path = user_path / "test_scheduler.db"
    return Scheduler(db_path=db_path)


def test_add_job_once(scheduler):
    """Test adding a one-time job."""
    job_id = scheduler.add_job(
        prompt="Test prompt",
        model="gpt-4o",
        schedule_type="once",
        schedule_value="2024-12-31T23:59:59",
        name="New Year Test"
    )

    assert job_id is not None


def test_add_job_cron(scheduler):
    """Test adding a recurring job."""
    job_id = scheduler.add_job(
        prompt="Daily report",
        model="gpt-4o",
        schedule_type="cron",
        schedule_value="0 9 * * *",
        name="Daily Report"
    )

    assert job_id is not None


def test_list_jobs(scheduler):
    """Test listing jobs."""
    scheduler.add_job("Prompt 1", "gpt-4o", "once", "2024-01-01", name="Job 1")
    scheduler.add_job("Prompt 2", "gpt-4o", "once", "2024-01-02", name="Job 2")

    jobs = scheduler.list_jobs()

    assert len(jobs) == 2
    assert any(j["name"] == "Job 1" for j in jobs)


def test_get_job(scheduler):
    """Test getting job details."""
    job_id = scheduler.add_job("Test", "gpt-4o", "once", "2024-01-01", name="Test Job")

    job = scheduler.get_job(job_id)

    assert job is not None
    assert job["name"] == "Test Job"
    assert job["prompt"] == "Test"


def test_delete_job(scheduler):
    """Test deleting a job."""
    job_id = scheduler.add_job("Test", "gpt-4o", "once", "2024-01-01")

    success = scheduler.delete_job(job_id)

    assert success is True

    job = scheduler.get_job(job_id)
    assert job is None


def test_get_job_runs(scheduler):
    """Test getting job run history."""
    job_id = scheduler.add_job("Test", "gpt-4o", "once", "2024-01-01")

    runs = scheduler.get_job_runs(job_id)

    assert isinstance(runs, list)
