# Feature 3: Cost Tracking and Budget Management

## Motivation

Using AI models costs money. API providers charge based on:
- Number of tokens processed (input and output)
- Which model you use (GPT-4o costs more than GPT-4o-mini)
- Special features (image processing, function calling)

**Common problems:**
- Unexpected bills at the end of the month
- Accidentally using expensive models for simple tasks
- No visibility into which projects consume the most API budget
- Difficulty justifying AI costs to management
- Testing and experimentation eating into production budgets

Cost tracking solves these problems by:
- Monitoring spending in real-time
- Setting budgets with automatic alerts
- Tracking costs per project, model, or user
- Generating detailed expense reports
- Preventing bill shock with spending limits

## Overview

The `llm costs` command provides comprehensive cost tracking and budget management for all your LLM usage.

**What you can do:**
- View current spending (daily, weekly, monthly)
- Set budgets with automatic warnings
- Track costs by model, conversation, or project
- Export expense reports for accounting
- Estimate costs before running prompts
- Set spending limits to prevent overages
- Allocate budgets to different projects
- Compare actual vs. estimated costs

## Installation Dependencies

### Basic Installation

Cost tracking is built into LLM with no additional packages required:

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Optional Dependencies

For enhanced reporting and charts:
```bash
pip install plotext  # Terminal-based charts
pip install pandas   # Advanced data analysis
```

For Excel export:
```bash
pip install openpyxl xlsxwriter
```

For PDF reports:
```bash
pip install reportlab
```

### Verification

```bash
# Verify LLM is installed
llm --version

# Check if cost tracking is enabled
llm costs status
```

## Implementation Details

### Architecture

The cost tracking system consists of:

1. **Cost Calculator** (`llm/cost_calculator.py`)
   - Maintains pricing tables for all models
   - Calculates costs from token usage
   - Handles different pricing tiers
   - Updates pricing from API provider data

2. **Budget Manager** (`llm/budget_manager.py`)
   - Tracks spending against budgets
   - Sends warnings when limits approached
   - Enforces hard limits (optional)
   - Manages multiple budget categories

3. **Cost Logger** (`llm/cost_logger.py`)
   - Records every API call with cost data
   - Aggregates costs by time period
   - Tracks costs by project, tag, or conversation
   - Generates expense reports

4. **Alert System** (`llm/cost_alerts.py`)
   - Monitors spending thresholds
   - Sends notifications (terminal, email, webhook)
   - Daily/weekly digest reports

### Data Flow

```
API Call → Token Usage → Cost Calculator → Cost Logger → Database
                                                ↓
                                         Budget Manager
                                                ↓
                                   Check Limits & Send Alerts
```

### Database Schema Additions

**Table: `costs`**
```sql
CREATE TABLE costs (
    id TEXT PRIMARY KEY,
    timestamp TEXT,
    log_id TEXT,  -- References logs.id
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    input_cost REAL,
    output_cost REAL,
    total_cost REAL,
    project TEXT,
    tags TEXT,  -- JSON array
    FOREIGN KEY (log_id) REFERENCES log(id)
);
```

**Table: `budgets`**
```sql
CREATE TABLE budgets (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    amount REAL,
    period TEXT,  -- 'daily', 'weekly', 'monthly', 'yearly'
    category TEXT,  -- 'global', 'project', 'model'
    category_value TEXT,  -- project name or model ID
    alert_threshold REAL,  -- 0.0 to 1.0 (percentage)
    hard_limit BOOLEAN,
    created_at TEXT,
    active BOOLEAN
);
```

**Table: `budget_alerts`**
```sql
CREATE TABLE budget_alerts (
    id TEXT PRIMARY KEY,
    budget_id TEXT,
    timestamp TEXT,
    spent REAL,
    budget_amount REAL,
    percentage REAL,
    alert_type TEXT,  -- 'warning', 'limit_reached'
    FOREIGN KEY (budget_id) REFERENCES budgets(id)
);
```

**Table: `pricing`**
```sql
CREATE TABLE pricing (
    model TEXT PRIMARY KEY,
    input_cost_per_1k REAL,
    output_cost_per_1k REAL,
    last_updated TEXT,
    source TEXT  -- 'manual', 'api', 'default'
);
```

### Cost Calculation Logic

```python
# Example pricing (as of Nov 2024)
PRICING = {
    "gpt-4o": {
        "input": 0.0025,   # per 1K tokens
        "output": 0.01     # per 1K tokens
    },
    "gpt-4o-mini": {
        "input": 0.00015,
        "output": 0.0006
    },
    "claude-opus": {
        "input": 0.015,
        "output": 0.075
    }
}

def calculate_cost(model, input_tokens, output_tokens):
    pricing = PRICING[model]
    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    return input_cost + output_cost
```

## Usage Instructions

### For Complete Beginners

Think of cost tracking like a bank account for AI usage. Every time you ask a question to an AI model, it costs a small amount of money. Cost tracking keeps track of how much you're spending, warns you if you're spending too much, and helps you stay within your budget.

### Basic Usage

#### View Current Spending

See how much you've spent so far:

```bash
llm costs
```

Output:
```
Cost Summary
────────────────────────────────────
Today:        $0.45
This Week:    $3.21
This Month:   $12.87
All Time:     $47.23

Top Models by Cost (This Month):
  gpt-4o:        $8.45  (66%)
  claude-opus:   $3.12  (24%)
  gpt-4o-mini:   $1.30  (10%)
```

#### View Detailed Breakdown

```bash
llm costs --detailed
```

Shows costs broken down by:
- Model
- Day of week
- Project
- Conversation

#### Set a Monthly Budget

```bash
llm costs set-budget --monthly 20
```

This creates a $20/month budget and warns you when you reach 80% and 90%.

#### Check Budget Status

```bash
llm costs budget-status
```

Output:
```
Monthly Budget: $20.00
Spent:          $12.87 (64%)
Remaining:      $7.13
Days Left:      14

Status: On track ✓
Average daily spend: $1.85
Projected end-of-month: $18.50
```

### Setting Up Budgets

#### Different Budget Periods

```bash
# Daily budget
llm costs set-budget --daily 2

# Weekly budget
llm costs set-budget --weekly 10

# Monthly budget (most common)
llm costs set-budget --monthly 50

# Yearly budget
llm costs set-budget --yearly 500
```

#### Project-Specific Budgets

Track costs separately for different projects:

```bash
# Set budget for a project
llm costs set-budget --monthly 15 --project "customer-support"

# Tag prompts with project
llm "Analyze this feedback" --project "customer-support"

# View project costs
llm costs --project "customer-support"
```

#### Model-Specific Budgets

Limit spending on expensive models:

```bash
# Limit GPT-4o usage to $10/month
llm costs set-budget --monthly 10 --model gpt-4o

# If you exceed limit, LLM can auto-switch to cheaper model
llm costs set-budget --monthly 10 --model gpt-4o --fallback gpt-4o-mini
```

### Cost Alerts

#### Configure Alert Thresholds

```bash
# Alert at 75%, 90%, and 100% of budget
llm costs set-alerts --thresholds 0.75 0.90 1.0
```

#### Alert Methods

```bash
# Terminal notifications (default)
llm costs set-alerts --method terminal

# Email notifications
llm costs set-alerts --method email --email your@email.com

# Webhook (for Slack, Discord, etc.)
llm costs set-alerts --method webhook --url "https://hooks.slack.com/..."

# Multiple methods
llm costs set-alerts --method terminal,email
```

#### Example Alert

When you hit 90% of budget:
```
⚠️  BUDGET WARNING ⚠️
You've spent $18.00 of your $20.00 monthly budget (90%)
Remaining: $2.00
Days left in period: 5
Consider: Switching to cheaper models or reducing usage
```

### Estimating Costs Before Execution

#### Estimate a Single Prompt

```bash
llm "Write a detailed essay about climate change" \
  --estimate-cost
```

Output:
```
Cost Estimate:
  Model: gpt-4o
  Estimated input tokens: 12
  Estimated output tokens: 500
  Estimated cost: $0.0053

Proceed? (y/n):
```

#### Estimate Batch Processing

```bash
llm batch prompts.csv --estimate-cost
```

Output:
```
Batch Cost Estimate:
  Prompts: 100
  Model: gpt-4o-mini
  Estimated total tokens: 50,000
  Estimated cost: $0.78

This is within your monthly budget.
Current spent: $12.87 / $20.00
After this batch: $13.65 / $20.00 (68%)

Proceed? (y/n):
```

### Cost Reports

#### Generate Monthly Report

```bash
llm costs report --month 2024-11
```

Output:
```
Cost Report: November 2024
═══════════════════════════════════════

Summary:
  Total Spent:    $47.32
  Total Prompts:  1,247
  Avg per Prompt: $0.038

By Model:
  gpt-4o:         $28.45  (60%)  |  512 prompts
  gpt-4o-mini:    $12.87  (27%)  |  623 prompts
  claude-opus:    $6.00   (13%)  |  112 prompts

By Project:
  customer-support: $22.10  (47%)
  content-gen:      $15.23  (32%)
  research:         $9.99   (21%)

By Day:
  Weekdays avg:   $1.89/day
  Weekends avg:   $0.45/day

Peak Usage:
  Nov 15: $5.67 (highest single day)
  Reason: Batch processing 200 reviews
```

#### Export Report

```bash
# Export as CSV
llm costs report --month 2024-11 --export costs_nov.csv

# Export as Excel
llm costs report --month 2024-11 --export costs_nov.xlsx

# Export as PDF
llm costs report --month 2024-11 --export costs_nov.pdf

# Export as JSON for analysis
llm costs report --month 2024-11 --export costs_nov.json
```

#### Custom Date Ranges

```bash
# Last 7 days
llm costs report --last 7d

# Last 30 days
llm costs report --last 30d

# Specific date range
llm costs report --from 2024-11-01 --to 2024-11-15

# This year
llm costs report --year 2024
```

### Advanced Features

#### Cost Breakdown by Conversation

See which conversations cost the most:

```bash
llm costs by-conversation --top 10
```

Output:
```
Top 10 Most Expensive Conversations:

1. conv_abc123  "Product planning discussion"
   Cost: $2.45  |  32 messages  |  gpt-4o

2. conv_def456  "Code review session"
   Cost: $1.87  |  28 messages  |  claude-opus

3. conv_ghi789  "Market research analysis"
   Cost: $1.34  |  15 messages  |  gpt-4o

...
```

#### Compare Costs Across Time Periods

```bash
llm costs compare --periods "2024-10,2024-11"
```

Output:
```
Cost Comparison:

                  October    November   Change
Total:            $42.10     $47.32     +12%
Prompts:          1,089      1,247      +14%
Avg/Prompt:       $0.039     $0.038     -3%

Model Usage:
  gpt-4o:         $25.00     $28.45     +14%
  gpt-4o-mini:    $14.10     $12.87     -9%
  claude-opus:    $3.00      $6.00      +100%
```

#### Set Hard Limits

Prevent spending over budget:

```bash
llm costs set-budget --monthly 20 --hard-limit
```

When limit is reached:
```
⛔ BUDGET LIMIT REACHED
You've reached your $20.00 monthly budget.
This prompt would cost approximately $0.05.

Options:
  1. Wait until next month (resets in 12 days)
  2. Increase your budget: llm costs set-budget --monthly 30
  3. Use a cheaper model: --model gpt-4o-mini
  4. Override limit: --ignore-budget (not recommended)
```

#### Tag Costs for Categorization

```bash
# Tag individual prompts
llm "Summarize quarterly results" --tags "finance,reports,Q4"

# View costs by tag
llm costs by-tag --tag finance

# Multiple tags
llm costs by-tag --tags "finance,reports"
```

## Command Reference

### `llm costs`

Display cost summary.

```bash
llm costs [OPTIONS]
```

**Options:**
- `--period PERIOD` - Time period: today, week, month, year, all
- `--detailed` - Show detailed breakdown
- `--model TEXT` - Filter by model
- `--project TEXT` - Filter by project
- `--tag TEXT` - Filter by tag
- `--from DATE` - Start date (YYYY-MM-DD)
- `--to DATE` - End date (YYYY-MM-DD)
- `--chart` - Display ASCII chart
- `--format FORMAT` - Output format: table, json, csv

### `llm costs set-budget`

Set a spending budget.

```bash
llm costs set-budget [OPTIONS] AMOUNT
```

**Arguments:**
- `AMOUNT` - Budget amount in dollars

**Options:**
- `--daily` - Daily budget
- `--weekly` - Weekly budget
- `--monthly` - Monthly budget (default)
- `--yearly` - Yearly budget
- `--project TEXT` - Budget for specific project
- `--model TEXT` - Budget for specific model
- `--hard-limit` - Enforce strict limit
- `--fallback MODEL` - Switch to this model when limit reached
- `--alert-at THRESHOLD` - Alert thresholds (0.0-1.0, can specify multiple)

**Examples:**

```bash
# Simple monthly budget
llm costs set-budget --monthly 25

# Daily budget with hard limit
llm costs set-budget --daily 2 --hard-limit

# Project budget with alerts
llm costs set-budget --monthly 15 --project research --alert-at 0.8 0.9

# Model budget with fallback
llm costs set-budget --monthly 10 --model gpt-4o --fallback gpt-4o-mini
```

### `llm costs budget-status`

Check budget status.

```bash
llm costs budget-status [OPTIONS]
```

**Options:**
- `--project TEXT` - Show project budget status
- `--model TEXT` - Show model budget status
- `--all` - Show all active budgets

### `llm costs report`

Generate detailed cost report.

```bash
llm costs report [OPTIONS]
```

**Options:**
- `--month YYYY-MM` - Specific month
- `--year YYYY` - Entire year
- `--from DATE` - Start date
- `--to DATE` - End date
- `--last PERIOD` - Last N days/months (e.g., "7d", "3m")
- `--by GROUP` - Group by: model, project, tag, day, week
- `--export PATH` - Export to file (.csv, .xlsx, .pdf, .json)
- `--include-chart` - Include visualization
- `--detailed` - Include per-prompt breakdown

### `llm costs by-conversation`

Show costs by conversation.

```bash
llm costs by-conversation [OPTIONS]
```

**Options:**
- `--top N` - Show top N conversations by cost
- `--from DATE` - Start date
- `--to DATE` - End date

### `llm costs by-tag`

Show costs by tag.

```bash
llm costs by-tag [OPTIONS]
```

**Options:**
- `--tag TEXT` - Specific tag
- `--tags TEXT` - Multiple tags (comma-separated)
- `--from DATE` - Start date
- `--to DATE` - End date

### `llm costs compare`

Compare costs across time periods.

```bash
llm costs compare --periods PERIOD1,PERIOD2
```

**Options:**
- `--periods TEXT` - Comma-separated periods (YYYY-MM)
- `--metric METRIC` - Compare: total, average, count, models

### `llm costs update-pricing`

Update model pricing information.

```bash
llm costs update-pricing [OPTIONS]
```

**Options:**
- `--from-api` - Fetch latest pricing from providers
- `--model TEXT` - Update specific model
- `--manual` - Manually enter pricing

### `llm costs pricing`

View current pricing for all models.

```bash
llm costs pricing [OPTIONS]
```

**Options:**
- `--model TEXT` - Show pricing for specific model
- `--format FORMAT` - Output format: table, json

## Configuration

### Cost Configuration File

Create `~/.llm/costs-config.yaml`:

```yaml
# Default budget settings
budgets:
  global:
    monthly: 50.00
    alert_thresholds: [0.75, 0.90, 1.0]
    hard_limit: false

  # Project budgets
  projects:
    customer-support:
      monthly: 20.00
      hard_limit: true
    research:
      monthly: 15.00
      hard_limit: false

  # Model budgets
  models:
    gpt-4o:
      monthly: 25.00
      fallback: gpt-4o-mini
    claude-opus:
      monthly: 10.00
      fallback: claude-haiku

# Alert settings
alerts:
  methods: [terminal, email]
  email: your@email.com
  webhook_url: null
  daily_digest: true
  digest_time: "09:00"

# Reporting
reports:
  default_format: table
  include_charts: true
  auto_export_monthly: true
  export_dir: ~/llm-reports/

# Cost tracking
tracking:
  enabled: true
  tag_required_for_work: false
  default_tags: []
  estimate_before_expensive: true
  expensive_threshold: 0.10  # Estimate if > $0.10

# Pricing updates
pricing:
  auto_update: true
  update_frequency: weekly
  source: api  # 'api', 'manual', 'default'
```

### Environment Variables

```bash
# Disable cost tracking
export LLM_COST_TRACKING=false

# Set default budget
export LLM_MONTHLY_BUDGET=30

# Require cost estimation for expensive prompts
export LLM_ESTIMATE_EXPENSIVE=true
```

## Real-World Examples

### Example 1: Team Budget Management

**Scenario:** You manage a team of 5 people using LLM, budget is $100/month.

```bash
# Set team budget
llm costs set-budget --monthly 100 --hard-limit

# Create per-person projects
llm costs set-budget --monthly 20 --project alice
llm costs set-budget --monthly 20 --project bob
llm costs set-budget --monthly 20 --project charlie
llm costs set-budget --monthly 20 --project diana
llm costs set-budget --monthly 20 --project eve

# Team members tag their usage
# Alice runs:
llm "Draft email" --project alice

# Weekly team report
llm costs report --week --by project

# Month-end report for finance
llm costs report --month $(date +%Y-%m) --export team_costs.xlsx
```

### Example 2: Development vs Production

**Scenario:** Separate budgets for testing and production.

```bash
# Development budget (testing, experimentation)
llm costs set-budget --monthly 30 --project development

# Production budget (customer-facing)
llm costs set-budget --monthly 70 --project production --hard-limit

# Development usage
llm "Test prompt" --project development

# Production usage
llm "Generate customer response" --project production

# Compare spending
llm costs compare --projects development,production
```

### Example 3: Model Cost Optimization

**Scenario:** Find the cheapest model that meets quality needs.

```bash
# Track costs for different models
llm "Analyze sentiment" --model gpt-4o --tags "sentiment,test"
llm "Analyze sentiment" --model gpt-4o-mini --tags "sentiment,test"
llm "Analyze sentiment" --model claude-haiku --tags "sentiment,test"

# Compare costs
llm costs by-tag --tag "sentiment"

# Output shows:
# gpt-4o:       $0.0045
# gpt-4o-mini:  $0.0008
# claude-haiku: $0.0003

# Set budget with auto-fallback to cheaper model
llm costs set-budget --monthly 20 --model gpt-4o --fallback gpt-4o-mini
```

### Example 4: Cost-Aware Batch Processing

**Scenario:** Process 1000 reviews but stay within budget.

```bash
# Check current budget status
llm costs budget-status

# Output: $15 remaining of $50 budget

# Estimate batch cost
llm batch reviews.csv --estimate-cost

# Output: Estimated $12.50

# Proceed with batch
llm batch reviews.csv --model gpt-4o-mini

# Monitor costs during processing
llm costs --period today
```

## Troubleshooting

### Costs Don't Match API Provider Bills

**Problem:** LLM costs show $45 but provider bills $52.

**Possible Causes:**
1. **Pricing outdated** - Update pricing: `llm costs update-pricing --from-api`
2. **Hidden fees** - Some providers charge extra for features
3. **Different time zones** - Provider may use different month boundaries
4. **Uncounted usage** - Direct API calls not through LLM

**Solution:**
```bash
# Update pricing
llm costs update-pricing --from-api

# Export detailed report
llm costs report --month 2024-11 --detailed --export report.csv

# Compare with provider bill line-by-line
```

### Budget Alerts Not Working

**Problem:** Exceeded budget but got no warning.

**Solutions:**
```bash
# Check alert configuration
llm costs config --show-alerts

# Test alerts
llm costs test-alert

# Verify email settings (if using email alerts)
llm costs set-alerts --method email --email your@email.com --test
```

### Inaccurate Cost Estimates

**Problem:** Estimates say $0.05 but actual cost is $0.15.

**Cause:** Token estimation is approximate, especially for complex prompts.

**Solution:** Estimates are ±30% accurate. For critical budgeting, add 30% buffer:
```bash
# Your math
Estimate: $10
Add 30% buffer: $13
Set budget: $13
```

## Best Practices

1. **Set realistic budgets** - Start with a higher budget, then reduce based on actual usage
2. **Use project tags** - Tag all prompts for better tracking
3. **Regular reviews** - Check `llm costs` weekly
4. **Export monthly reports** - Keep records for accounting
5. **Use hard limits for production** - Prevent unexpected overspend
6. **Optimize model choice** - Use cheaper models when quality difference is minimal
7. **Monitor trends** - Watch for sudden increases in spending
8. **Update pricing regularly** - Providers change pricing

## Python API

For developers integrating cost tracking:

```python
from llm import get_model, get_costs, set_budget

# Get model and track costs
model = get_model("gpt-4o")
response = model.prompt("Explain quantum computing")

# Access cost info
print(f"Cost: ${response.cost:.4f}")
print(f"Input tokens: {response.input_tokens}")
print(f"Output tokens: {response.output_tokens}")

# Get cost summary
costs = get_costs(period="month")
print(f"Total this month: ${costs.total}")
print(f"By model: {costs.by_model}")

# Set budget programmatically
set_budget(monthly=50, alert_thresholds=[0.8, 0.9, 1.0])

# Estimate before running
estimate = model.estimate_cost(prompt="Long prompt here...")
print(f"Estimated cost: ${estimate.cost}")
if estimate.cost < 0.10:
    response = model.prompt("Long prompt here...")
```

## Conclusion

Cost tracking transforms LLM usage from a "black box" expense to a managed, predictable budget item. Benefits:
- **Prevent bill shock** - Know costs before they happen
- **Optimize spending** - Use the right model for each task
- **Enable accountability** - Track costs by person or project
- **Support budgeting** - Accurate forecasting for planning
- **Justify expenses** - Show ROI with detailed reports

Start tracking costs today to take control of your AI spending!
