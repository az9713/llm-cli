"""Tests for Cost Tracking feature."""
import pytest
from datetime import datetime, timedelta
from llm.cost_tracking import CostTracker


@pytest.fixture
def tracker(user_path):
    """Create a CostTracker instance with test database."""
    db_path = user_path / "test_costs.db"
    return CostTracker(db_path=db_path)


def test_calculate_cost_gpt4o(tracker):
    """Test cost calculation for GPT-4o."""
    # GPT-4o: $0.0025 per 1K input, $0.01 per 1K output
    cost = tracker.calculate_cost("gpt-4o", input_tokens=1000, output_tokens=1000)
    expected = (1000/1000 * 0.0025) + (1000/1000 * 0.01)  # $0.0125
    assert abs(cost - expected) < 0.0001


def test_calculate_cost_claude_sonnet(tracker):
    """Test cost calculation for Claude Sonnet."""
    # Claude Sonnet 3.5: $0.003 per 1K input, $0.015 per 1K output
    cost = tracker.calculate_cost("claude-sonnet-3.5", input_tokens=2000, output_tokens=500)
    expected = (2000/1000 * 0.003) + (500/1000 * 0.015)  # $0.006 + $0.0075 = $0.0135
    assert abs(cost - expected) < 0.0001


def test_calculate_cost_unknown_model(tracker):
    """Test cost calculation for unknown model uses default pricing."""
    cost = tracker.calculate_cost("unknown-model", input_tokens=1000, output_tokens=1000)
    # Should use default: $0.001 input, $0.002 output per 1K
    expected = (1000/1000 * 0.001) + (1000/1000 * 0.002)  # $0.003
    assert abs(cost - expected) < 0.0001


def test_log_cost(tracker):
    """Test logging a cost entry."""
    cost_id = tracker.log_cost(
        model="gpt-4o",
        input_tokens=500,
        output_tokens=200,
        project="test-project"
    )

    assert cost_id is not None
    assert len(cost_id) > 0


def test_log_cost_with_tags(tracker):
    """Test logging cost with tags."""
    cost_id = tracker.log_cost(
        model="gpt-4o",
        input_tokens=500,
        output_tokens=200,
        tags=["test", "example"]
    )

    assert cost_id is not None


def test_get_spending_empty(tracker):
    """Test getting spending when no costs logged."""
    spending = tracker.get_spending(period="month")

    assert spending["total_cost"] == 0
    assert spending["total_prompts"] == 0
    assert spending["total_tokens"] == 0


def test_get_spending_month(tracker):
    """Test getting monthly spending."""
    # Log some costs
    tracker.log_cost("gpt-4o", 1000, 500)
    tracker.log_cost("gpt-4o", 2000, 1000)

    spending = tracker.get_spending(period="month")

    assert spending["total_prompts"] == 2
    assert spending["total_tokens"] == 4500
    assert spending["total_cost"] > 0


def test_get_spending_by_model(tracker):
    """Test spending grouped by model."""
    tracker.log_cost("gpt-4o", 1000, 500)
    tracker.log_cost("gpt-4o-mini", 2000, 1000)
    tracker.log_cost("gpt-4o", 1000, 500)

    spending = tracker.get_spending(period="all")

    assert "gpt-4o" in spending["by_model"]
    assert "gpt-4o-mini" in spending["by_model"]
    assert spending["by_model"]["gpt-4o"]["prompts"] == 2
    assert spending["by_model"]["gpt-4o-mini"]["prompts"] == 1


def test_get_spending_by_project(tracker):
    """Test filtering spending by project."""
    tracker.log_cost("gpt-4o", 1000, 500, project="project-a")
    tracker.log_cost("gpt-4o", 1000, 500, project="project-b")
    tracker.log_cost("gpt-4o", 1000, 500, project="project-a")

    spending_a = tracker.get_spending(period="all", project="project-a")
    spending_b = tracker.get_spending(period="all", project="project-b")

    assert spending_a["total_prompts"] == 2
    assert spending_b["total_prompts"] == 1


def test_set_budget(tracker):
    """Test setting a budget."""
    budget_id = tracker.set_budget(
        name="monthly-budget",
        amount=100.0,
        period="monthly",
        category="global"
    )

    assert budget_id is not None


def test_set_budget_with_threshold(tracker):
    """Test setting budget with custom alert threshold."""
    budget_id = tracker.set_budget(
        name="test-budget",
        amount=50.0,
        period="monthly",
        alert_threshold=0.9  # Alert at 90%
    )

    assert budget_id is not None


def test_set_budget_hard_limit(tracker):
    """Test setting budget with hard limit."""
    budget_id = tracker.set_budget(
        name="strict-budget",
        amount=25.0,
        period="weekly",
        hard_limit=True
    )

    assert budget_id is not None


def test_get_budgets(tracker):
    """Test getting all budgets."""
    tracker.set_budget("budget1", 100.0, "monthly")
    tracker.set_budget("budget2", 50.0, "weekly")

    budgets = tracker.get_budgets()

    assert len(budgets) == 2
    assert any(b["name"] == "budget1" for b in budgets)
    assert any(b["name"] == "budget2" for b in budgets)


def test_check_budget_status(tracker):
    """Test checking budget status."""
    # Set a budget
    tracker.set_budget("test-budget", amount=10.0, period="month")

    # Log some spending (should be about $0.0125 for GPT-4o)
    tracker.log_cost("gpt-4o", 1000, 1000)

    status = tracker.check_budget_status("test-budget")

    assert status is not None
    assert status["budget_name"] == "test-budget"
    assert status["amount"] == 10.0
    assert status["spent"] > 0
    assert status["remaining"] < 10.0
    assert status["percentage"] > 0
    assert status["status"] == "ok"  # Should be under 80%


def test_check_budget_status_warning(tracker):
    """Test budget status shows warning when approaching limit."""
    # Set a very low budget
    tracker.set_budget("low-budget", amount=0.01, period="month")

    # Log spending that exceeds 80% of budget
    tracker.log_cost("gpt-4o", 1000, 1000)  # ~$0.0125

    status = tracker.check_budget_status("low-budget")

    # Should be over budget
    assert status["percentage"] > 80


def test_delete_budget(tracker):
    """Test deleting a budget."""
    tracker.set_budget("to-delete", 100.0, "monthly")

    # Verify it exists
    budgets = tracker.get_budgets()
    assert any(b["name"] == "to-delete" for b in budgets)

    # Delete it
    deleted = tracker.delete_budget("to-delete")
    assert deleted is True

    # Verify it's gone
    budgets = tracker.get_budgets()
    assert not any(b["name"] == "to-delete" for b in budgets)


def test_delete_nonexistent_budget(tracker):
    """Test deleting a budget that doesn't exist."""
    deleted = tracker.delete_budget("nonexistent")
    assert deleted is False


def test_budget_per_model(tracker):
    """Test setting budget for specific model."""
    budget_id = tracker.set_budget(
        name="gpt4-budget",
        amount=50.0,
        period="monthly",
        category="model",
        category_value="gpt-4o"
    )

    assert budget_id is not None


def test_budget_per_project(tracker):
    """Test setting budget for specific project."""
    budget_id = tracker.set_budget(
        name="project-budget",
        amount=100.0,
        period="monthly",
        category="project",
        category_value="my-project"
    )

    assert budget_id is not None


def test_avg_cost_per_prompt(tracker):
    """Test average cost per prompt calculation."""
    tracker.log_cost("gpt-4o", 1000, 1000)  # ~$0.0125
    tracker.log_cost("gpt-4o", 1000, 1000)  # ~$0.0125

    spending = tracker.get_spending(period="all")

    assert spending["total_prompts"] == 2
    assert spending["avg_cost_per_prompt"] > 0
    # Average should be around $0.0125
    assert abs(spending["avg_cost_per_prompt"] - 0.0125) < 0.001


def test_spending_periods(tracker):
    """Test different spending periods."""
    tracker.log_cost("gpt-4o", 1000, 1000)

    # Test each period
    for period in ["today", "week", "month", "year", "all"]:
        spending = tracker.get_spending(period=period)
        assert "total_cost" in spending
        assert "period" in spending
        assert spending["period"] == period
