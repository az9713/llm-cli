# Feature 10: Scheduled Prompts and Automation

> **✅ IMPLEMENTED FEATURE**
>
> This feature is fully implemented and available in the LLM CLI.
> All commands documented here are ready to use.

---


## Motivation

Many tasks benefit from regular AI assistance:
- **Daily summaries** - News digests, market updates
- **Regular reports** - Weekly analytics, monthly summaries
- **Monitoring** - Check websites for changes
- **Reminders** - Daily standup prep, weekly reviews
- **Data processing** - Regular batch analysis

Currently, you must run these manually, which:
- Requires remembering
- Takes time
- Leads to inconsistency
- Limits automation potential

Scheduled prompts solve this by running automatically at specified times.

## Overview

The `llm schedule` command enables you to schedule prompts to run automatically at specific times or intervals.

**What you can do:**
- Schedule prompts to run daily, weekly, monthly
- Use cron-like syntax for complex schedules
- Chain multiple prompts together
- Send results via email or webhooks
- Create recurring workflows
- Monitor external sources
- Generate automated reports

## Installation Dependencies

### Basic Installation

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Scheduler Backend

The scheduler requires a background service. Choose one:

**Option 1: Built-in Scheduler (Recommended)**
```bash
pip install schedule
```

**Option 2: System Cron (Linux/Mac)**
Already installed on most systems.

**Option 3: Windows Task Scheduler**
Built into Windows.

### Optional Dependencies

For email notifications:
```bash
pip install sendmail
```

For webhook support:
```bash
pip install requests  # Already included
```

### Verification

```bash
llm --version
llm schedule --help

# Start scheduler daemon
llm schedule start
```

## Implementation Details

### Architecture

**Components:**

1. **Scheduler Daemon** (`llm/schedule/daemon.py`)
   - Background process
   - Monitors schedule
   - Triggers jobs

2. **Job Manager** (`llm/schedule/jobs.py`)
   - Creates and stores jobs
   - Handles execution
   - Manages retries

3. **Cron Parser** (`llm/schedule/cron.py`)
   - Parses cron syntax
   - Calculates next run
   - Validates schedules

4. **Notifier** (`llm/schedule/notify.py`)
   - Email delivery
   - Webhook posting
   - File output

### Scheduling Pipeline

```
Schedule Definition → Scheduler Daemon → Time Check → Execute Prompt → Handle Output
```

### Database Schema

**Table: `scheduled_jobs`**
```sql
CREATE TABLE scheduled_jobs (
    id TEXT PRIMARY KEY,
    name TEXT,
    prompt TEXT,
    system_prompt TEXT,
    schedule TEXT,  -- cron expression
    model TEXT,
    enabled BOOLEAN,
    last_run TEXT,
    next_run TEXT,
    run_count INTEGER,
    success_count INTEGER,
    failure_count INTEGER,
    notify_email TEXT,
    notify_webhook TEXT,
    output_file TEXT,
    created_at TEXT,
    metadata JSON
);
```

**Table: `job_runs`**
```sql
CREATE TABLE job_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    started_at TEXT,
    completed_at TEXT,
    status TEXT,  -- 'success', 'failed'
    output TEXT,
    error TEXT,
    cost REAL,
    FOREIGN KEY (job_id) REFERENCES scheduled_jobs(id)
);
```

## Usage Instructions

### For Complete Beginners

Think of scheduled prompts like setting an alarm clock or a recurring calendar event. Instead of an alarm sound, it runs an AI prompt at the scheduled time. Like setting your phone to remind you to take medicine at 8 AM daily, you can schedule AI to summarize news at 9 AM daily.

### Basic Usage

#### Schedule a Daily Prompt

```bash
llm schedule create morning-news \
  --prompt "Summarize today's tech news" \
  --daily "09:00" \
  --email your@email.com
```

This runs every day at 9 AM and emails you the results.

#### Schedule a Weekly Report

```bash
llm schedule create weekly-summary \
  --prompt "Analyze my git commits from the past week" \
  --weekly "Monday 10:00" \
  --output ~/reports/weekly-$(date +%Y-%m-%d).txt
```

Runs every Monday at 10 AM.

#### Schedule a Monthly Task

```bash
llm schedule create monthly-review \
  --prompt "Create a monthly review of my goals" \
  --monthly "1st 18:00" \
  --email me@example.com
```

Runs on the 1st of each month at 6 PM.

### Schedule Formats

#### Simple Schedules

```bash
# Every hour
llm schedule create hourly-check \
  --prompt "Check system status" \
  --interval "1 hour"

# Every day at specific time
llm schedule create daily-digest \
  --prompt "Daily summary" \
  --daily "08:00"

# Every week
llm schedule create weekly-report \
  --prompt "Weekly report" \
  --weekly "Friday 17:00"

# Every month
llm schedule create monthly-analysis \
  --prompt "Monthly analysis" \
  --monthly "1st 09:00"
```

#### Cron Syntax

For complex schedules, use cron:

```bash
# Every weekday at 9 AM
llm schedule create weekday-brief \
  --prompt "Morning briefing" \
  --cron "0 9 * * 1-5"

# Every 4 hours
llm schedule create check-updates \
  --prompt "Check for updates" \
  --cron "0 */4 * * *"

# First Monday of each month
llm schedule create monthly-meeting \
  --prompt "Prepare monthly meeting agenda" \
  --cron "0 9 1-7 * 1"
```

**Cron format:** `minute hour day month weekday`

Examples:
- `0 9 * * *` - Daily at 9 AM
- `0 9 * * 1` - Every Monday at 9 AM
- `0 */4 * * *` - Every 4 hours
- `30 8 1 * *` - 8:30 AM on the 1st of each month

### Dynamic Prompts

#### Use Current Data

```bash
llm schedule create daily-commits \
  --prompt "Summarize git commits from today" \
  --pre-command "git log --since='1 day ago' --pretty=format:'%h %s' > /tmp/commits.txt" \
  --prompt-file /tmp/commits.txt \
  --daily "18:00"
```

Process:
1. Runs pre-command (gets today's commits)
2. Sends result as input to prompt
3. Delivers AI analysis

#### Variables in Prompts

```bash
llm schedule create weather-briefing \
  --prompt "Analyze weather forecast for {{location}}" \
  --vars "location=London" \
  --daily "07:00"
```

#### Chained Jobs

```bash
# Job 1: Collect data
llm schedule create collect-data \
  --prompt "Extract key points from {{url}}" \
  --vars "url=https://news.example.com" \
  --output /tmp/extracted.txt \
  --daily "08:00"

# Job 2: Analyze (runs after Job 1)
llm schedule create analyze-data \
  --prompt "Analyze these points: {{data}}" \
  --input-from /tmp/extracted.txt \
  --after collect-data \
  --email me@example.com
```

### Managing Scheduled Jobs

#### List All Jobs

```bash
llm schedule list
```

Output:
```
Scheduled Jobs (5 active, 2 disabled)
═══════════════════════════════════════════════════════════════

Name: morning-news
  Schedule: Daily at 09:00
  Next run: 2024-11-17 09:00
  Status: ✓ Enabled
  Last run: Success (2 hours ago)

Name: weekly-summary
  Schedule: Weekly Monday at 10:00
  Next run: 2024-11-18 10:00
  Status: ✓ Enabled
  Last run: Success (6 days ago)

[...]
```

#### View Job Details

```bash
llm schedule show morning-news
```

Output:
```
Job Details: morning-news
═══════════════════════════════════════════════════════════════

Schedule: Daily at 09:00
Model: gpt-4o-mini
Status: Enabled

Prompt:
  Summarize today's tech news

Delivery:
  Email: your@email.com

Statistics:
  Created: 2024-11-01
  Total runs: 15
  Successful: 14 (93%)
  Failed: 1
  Avg cost: $0.003
  Total cost: $0.045

Recent Runs:
  2024-11-16 09:00 - Success - $0.003
  2024-11-15 09:00 - Success - $0.003
  2024-11-14 09:00 - Failed - Rate limit
  2024-11-13 09:00 - Success - $0.003
```

#### Edit Job

```bash
# Change schedule
llm schedule edit morning-news --daily "08:00"

# Change model
llm schedule edit morning-news --model gpt-4o

# Update prompt
llm schedule edit morning-news --prompt "Summarize tech and business news"
```

#### Enable/Disable

```bash
# Disable (pause)
llm schedule disable morning-news

# Enable (resume)
llm schedule enable morning-news
```

#### Delete Job

```bash
llm schedule delete morning-news
```

### Output Options

#### Email Results

```bash
llm schedule create daily-report \
  --prompt "Generate daily report" \
  --daily "17:00" \
  --email you@example.com \
  --email-subject "Daily AI Report"
```

#### Save to File

```bash
llm schedule create log-analyzer \
  --prompt "Analyze system logs" \
  --daily "23:00" \
  --output ~/reports/daily-$(date +%Y-%m-%d).txt
```

#### Post to Webhook

```bash
llm schedule create slack-digest \
  --prompt "Daily team digest" \
  --daily "09:00" \
  --webhook "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

#### Multiple Outputs

```bash
llm schedule create multi-output \
  --prompt "Important analysis" \
  --daily "10:00" \
  --email manager@company.com \
  --output ~/reports/report.txt \
  --webhook "https://api.company.com/reports"
```

### Real-World Examples

#### Example 1: Daily News Digest

```bash
llm schedule create news-digest \
  --prompt "Summarize today's top tech news in 5 bullet points. Focus on AI, programming, and startups." \
  --daily "08:00" \
  --model gpt-4o-mini \
  --email you@example.com \
  --email-subject "Tech News Digest - $(date +%Y-%m-%d)"
```

#### Example 2: GitHub Activity Summary

```bash
llm schedule create github-summary \
  --pre-command "gh api /users/YOUR_USERNAME/events | head -50 > /tmp/gh-events.json" \
  --prompt "Summarize my GitHub activity: {{events}}" \
  --input-from /tmp/gh-events.json \
  --daily "18:00" \
  --output ~/reports/github-daily.md
```

#### Example 3: Weekly Code Review Reminder

```bash
llm schedule create review-reminder \
  --prompt "Generate a checklist for conducting code reviews, focusing on security, performance, and best practices." \
  --weekly "Monday 09:00" \
  --email team@company.com \
  --email-subject "Weekly Code Review Checklist"
```

#### Example 4: Monthly Goal Review

```bash
llm schedule create goal-review \
  --prompt "Create a template for monthly goal review with questions about progress, challenges, and adjustments." \
  --monthly "1st 09:00" \
  --email you@example.com \
  --output ~/goals/review-$(date +%Y-%m).md
```

#### Example 5: Website Change Monitor

```bash
llm schedule create website-monitor \
  --pre-command "curl -s https://example.com/pricing > /tmp/pricing.html" \
  --prompt "Compare this with the previous version and highlight any changes: {{content}}" \
  --input-from /tmp/pricing.html \
  --interval "1 hour" \
  --webhook "https://hooks.slack.com/..." \
  --notify-on-change-only
```

#### Example 6: Standup Preparation

```bash
llm schedule create standup-prep \
  --pre-command "git log --author='$(git config user.name)' --since='1 day ago' --pretty=format:'%s' > /tmp/commits.txt" \
  --prompt "Based on these git commits, create a standup update covering: what I did, what I'm doing today, any blockers. Commits: {{commits}}" \
  --input-from /tmp/commits.txt \
  --weekly "Mon,Tue,Wed,Thu,Fri 08:45" \
  --email you@example.com
```

## Command Reference

### `llm schedule create`

Create a scheduled job.

```bash
llm schedule create NAME [OPTIONS]
```

**Arguments:**
- `NAME` - Unique job name

**Prompt:**
- `--prompt TEXT` - Prompt to run
- `--system TEXT` - System prompt
- `--template NAME` - Use saved template
- `--model TEXT` - Model to use

**Schedule:**
- `--cron EXPR` - Cron expression
- `--interval TIME` - Interval (e.g., "1 hour", "30 minutes")
- `--daily TIME` - Daily at time (e.g., "09:00")
- `--weekly "DAY TIME"` - Weekly (e.g., "Monday 10:00")
- `--monthly "DAY TIME"` - Monthly (e.g., "1st 09:00")

**Input:**
- `--input-from FILE` - Read input from file
- `--pre-command CMD` - Run command before prompt
- `--vars KEY=VALUE` - Template variables

**Output:**
- `--output FILE` - Save to file
- `--email ADDRESS` - Email results
- `--email-subject TEXT` - Email subject
- `--webhook URL` - POST to webhook
- `--notify-on-change-only` - Only notify if output changed

**Options:**
- `--enabled/--disabled` - Start enabled or disabled
- `--retry N` - Retry N times on failure
- `--timeout N` - Timeout in seconds

### `llm schedule list`

List scheduled jobs.

```bash
llm schedule list [OPTIONS]
```

**Options:**
- `--enabled` - Only enabled jobs
- `--disabled` - Only disabled jobs
- `--format FORMAT` - table, json, yaml

### `llm schedule show`

Show job details.

```bash
llm schedule show NAME
```

### `llm schedule edit`

Edit a scheduled job.

```bash
llm schedule edit NAME [OPTIONS]
```

Same options as `create`.

### `llm schedule delete`

Delete a job.

```bash
llm schedule delete NAME [--force]
```

### `llm schedule enable/disable`

Enable or disable a job.

```bash
llm schedule enable NAME
llm schedule disable NAME
```

### `llm schedule run`

Manually run a job now.

```bash
llm schedule run NAME [--no-save]
```

**Options:**
- `--no-save` - Don't save to job history

### `llm schedule logs`

View job execution logs.

```bash
llm schedule logs NAME [OPTIONS]
```

**Options:**
- `--limit N` - Show last N runs
- `--failed` - Only failed runs
- `--since DATE` - Since date

### `llm schedule start/stop`

Control scheduler daemon.

```bash
# Start daemon
llm schedule start

# Stop daemon
llm schedule stop

# Restart daemon
llm schedule restart

# Status
llm schedule status
```

## Configuration

`~/.llm/schedule-config.yaml`:

```yaml
scheduler:
  daemon: true  # Run as background daemon
  log_file: ~/.llm/scheduler.log
  pid_file: ~/.llm/scheduler.pid

defaults:
  model: gpt-4o-mini
  retry_on_failure: 3
  retry_delay: 300  # 5 minutes
  timeout: 120  # 2 minutes

notifications:
  email:
    smtp_server: smtp.gmail.com
    smtp_port: 587
    from_address: llm@yourdomain.com
    username: ${SMTP_USER}
    password: ${SMTP_PASSWORD}

  webhook:
    default_method: POST
    timeout: 30
    retry: 2

execution:
  max_concurrent_jobs: 3
  job_timeout: 600  # 10 minutes
  save_output: true
  output_dir: ~/.llm/scheduled-outputs/
```

## Scheduler Daemon

### Starting the Scheduler

```bash
# Start in background
llm schedule start

# Start in foreground (for debugging)
llm schedule start --foreground

# Start with custom config
llm schedule start --config custom-config.yaml
```

### Checking Status

```bash
llm schedule status
```

Output:
```
Scheduler Status
═══════════════════════════════════════════════════════════════

Status: Running
PID: 12345
Uptime: 5 days, 3 hours
Next job: morning-news in 2 hours

Active jobs: 7
Jobs executed today: 23
Success rate (24h): 95%
```

### Logs

```bash
# View scheduler logs
tail -f ~/.llm/scheduler.log

# View specific job logs
llm schedule logs morning-news --limit 10
```

## Best Practices

1. **Test before scheduling** - Run manually first: `llm schedule run NAME`
2. **Use appropriate models** - gpt-4o-mini for simple tasks
3. **Set retries** - Handle temporary failures: `--retry 3`
4. **Monitor costs** - Check `llm costs` regularly
5. **Use meaningful names** - Descriptive job names
6. **Handle timezones** - Scheduler uses system timezone
7. **Backup critical jobs** - Export configs regularly

## Troubleshooting

### Job Didn't Run

**Problem:** Scheduled job didn't execute.

**Check:**
```bash
# Is daemon running?
llm schedule status

# Is job enabled?
llm schedule show JOB_NAME

# Check logs
llm schedule logs JOB_NAME
```

**Solutions:**
```bash
# Start daemon
llm schedule start

# Enable job
llm schedule enable JOB_NAME

# Check schedule syntax
llm schedule show JOB_NAME
```

### Job Keeps Failing

**Problem:** Job runs but fails every time.

**Solutions:**
```bash
# Run manually to see error
llm schedule run JOB_NAME

# Check logs
llm schedule logs JOB_NAME --failed

# Test the prompt directly
llm "your prompt here"

# Increase timeout
llm schedule edit JOB_NAME --timeout 300
```

### Email Not Sending

**Problem:** Emails not being delivered.

**Check:**
```bash
# Verify email config
cat ~/.llm/schedule-config.yaml

# Test email
llm schedule run JOB_NAME --email test@example.com

# Check scheduler logs
tail ~/.llm/scheduler.log | grep email
```

## Security Considerations

### API Key Security

Scheduled jobs use your stored API keys:

```bash
# Keys are stored in
~/.llm/keys.json

# Ensure proper permissions
chmod 600 ~/.llm/keys.json
```

### Pre-Command Safety

Be careful with pre-commands:

```bash
# Good: Safe read-only command
--pre-command "git log --since='1 day ago'"

# Bad: Dangerous command
--pre-command "rm -rf /"  # DON'T DO THIS
```

### Webhook Security

Use HTTPS webhooks and verify receivers:

```bash
# Good: HTTPS with auth
--webhook "https://api.company.com/endpoint?token=SECRET"

# Bad: HTTP, no auth
--webhook "http://example.com/public"  # Insecure
```

## Python API

```python
from llm import schedule_prompt

# Create scheduled job
job = schedule_prompt(
    name="daily-summary",
    prompt="Summarize today's events",
    schedule="daily",
    time="09:00",
    email="you@example.com"
)

# Manage jobs
from llm.schedule import list_jobs, run_job, delete_job

jobs = list_jobs()
run_job("daily-summary")
delete_job("old-job")
```

## Integration Examples

### With GitHub Actions

```yaml
# .github/workflows/weekly-summary.yml
name: Weekly Summary
on:
  schedule:
    - cron: '0 9 * * 1'  # Monday 9 AM

jobs:
  summary:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install LLM
        run: pip install llm
      - name: Generate Summary
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          llm "Summarize commits from past week" < <(git log --since='1 week ago')
```

## Conclusion

Scheduled prompts enable:
- **Automation** - Run AI tasks automatically
- **Consistency** - Regular updates without manual work
- **Time savings** - Set once, run forever
- **Proactive insights** - Regular analysis and monitoring
- **Integration** - Combine AI with existing workflows

Start scheduling prompts to automate your AI workflows!
