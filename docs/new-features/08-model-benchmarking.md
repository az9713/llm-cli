# Feature 8: Model Benchmarking

> **⚠️ PROPOSED FEATURE - NOT YET IMPLEMENTED**
>
> This document describes a **proposed feature** for the LLM CLI that does not currently exist.
> The `llm benchmark` command and all related commands documented here are **not yet available**.
>
> **Attempting to run these commands will result in "Error: No such command"**
>
> This is a detailed specification for future implementation.

---


## Motivation

With dozens of AI models available, choosing the right one is challenging:
- **Performance varies** - Models excel at different tasks
- **Speed matters** - Some models are 10x faster than others
- **Cost differences** - Prices vary significantly
- **Quality trade-offs** - Faster/cheaper doesn't always mean worse

Without systematic testing, you might:
- Pay for expensive models when cheaper ones work equally well
- Use slow models when speed is critical
- Miss out on models perfect for your specific use case

Model benchmarking provides objective data to make informed decisions.

## Overview

The `llm benchmark` command runs standardized tests to compare models on speed, quality, cost, and task-specific performance.

**What you can do:**
- Run pre-built benchmark suites
- Test models on your specific tasks
- Compare speed, cost, and quality
- Generate comparison reports
- Find the best model for each use case
- Track model performance over time

## Installation Dependencies

### Basic Installation

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Optional Dependencies

For statistical analysis:
```bash
pip install numpy scipy pandas
```

For visualization:
```bash
pip install matplotlib plotext
```

For report generation:
```bash
pip install jinja2 markdown
```

### Verification

```bash
llm --version
llm benchmark --help
```

## Implementation Details

### Architecture

**Components:**

1. **Benchmark Suite Manager** (`llm/benchmark/suites.py`)
   - Pre-built test suites
   - Custom test creation
   - Task categories

2. **Test Runner** (`llm/benchmark/runner.py`)
   - Executes benchmarks
   - Handles multiple models
   - Tracks metrics

3. **Metrics Collector** (`llm/benchmark/metrics.py`)
   - Response time
   - Token usage
   - Cost calculation
   - Quality scoring

4. **Report Generator** (`llm/benchmark/reporter.py`)
   - Comparison tables
   - Charts and graphs
   - HTML reports

### Benchmark Pipeline

```
Select Models → Load Test Suite → Run Tests → Collect Metrics → Generate Report
```

### Database Schema

**Table: `benchmarks`**
```sql
CREATE TABLE benchmarks (
    id TEXT PRIMARY KEY,
    name TEXT,
    suite TEXT,
    created_at TEXT,
    models TEXT,  -- JSON array
    status TEXT,
    results JSON
);
```

**Table: `benchmark_results`**
```sql
CREATE TABLE benchmark_results (
    id TEXT PRIMARY KEY,
    benchmark_id TEXT,
    model TEXT,
    test_name TEXT,
    response_time REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost REAL,
    quality_score REAL,
    success BOOLEAN,
    FOREIGN KEY (benchmark_id) REFERENCES benchmarks(id)
);
```

## Usage Instructions

### For Complete Beginners

Think of benchmarking like testing different cars on the same race track. You measure which is fastest, which uses least fuel, which handles corners best. Model benchmarking does the same for AI models - testing them on identical tasks to see which performs best for your needs.

### Basic Usage

#### Quick Benchmark

Compare models with a standard test suite:

```bash
llm benchmark \
  --models gpt-4o,gpt-4o-mini,claude-opus \
  --suite general
```

This runs general-purpose tests and shows results:

```
Benchmark Results: general
══════════════════════════════════════════════════════════════

Model           Speed    Cost      Quality   Overall
────────────────────────────────────────────────────────────
gpt-4o          1.2s     $0.023    9.2/10    A
gpt-4o-mini     0.8s     $0.004    8.5/10    A-
claude-opus     1.5s     $0.045    9.4/10    A+

Recommendations:
  Best overall: claude-opus (highest quality)
  Best value: gpt-4o-mini (good quality, lowest cost)
  Fastest: gpt-4o-mini
```

#### Benchmark Specific Task

Test models on your specific use case:

```bash
llm benchmark \
  --models gpt-4o,gpt-4o-mini \
  --suite code-generation \
  --output code-benchmark.html
```

### Built-in Benchmark Suites

#### General Purpose

Tests overall capabilities:

```bash
llm benchmark --models gpt-4o,claude-opus --suite general
```

Tests:
- Factual question answering
- Creative writing
- Reasoning and logic
- Instruction following
- Common sense

#### Code Generation

Tests programming capabilities:

```bash
llm benchmark --models gpt-4o,gpt-4o-mini --suite code-generation
```

Tests:
- Write simple functions
- Debug code
- Explain code
- Refactoring
- Test generation

#### Writing & Content

Tests content creation:

```bash
llm benchmark --suite writing --models gpt-4o,claude-opus
```

Tests:
- Email writing
- Blog posts
- Summaries
- Marketing copy
- Technical documentation

#### Translation

Tests language translation:

```bash
llm benchmark --suite translation --models gpt-4o,gpt-4o-mini
```

Tests multiple language pairs:
- English ↔ Spanish
- English ↔ French
- English ↔ German
- Etc.

#### Analysis & Reasoning

Tests analytical capabilities:

```bash
llm benchmark --suite reasoning --models gpt-4o,claude-opus
```

Tests:
- Math problems
- Logic puzzles
- Data analysis
- Critical thinking

### Custom Benchmarks

#### Create Custom Test Suite

```bash
# Create test file
cat > my-tests.yaml << 'EOF'
name: Customer Support Tests
description: Test models for customer support tasks

tests:
  - name: Refund Request
    prompt: "Customer asks for refund. Write empathetic response."
    criteria:
      - empathy
      - clear policy explanation
      - solution offered

  - name: Technical Issue
    prompt: "Customer can't login. Provide troubleshooting steps."
    criteria:
      - clear instructions
      - multiple solutions
      - encouraging tone

  - name: Complaint Handling
    prompt: "Customer complains about slow delivery. Respond professionally."
    criteria:
      - acknowledgment of issue
      - explanation
      - compensation offered
EOF

# Run custom benchmark
llm benchmark \
  --models gpt-4o,gpt-4o-mini,claude-opus \
  --custom-suite my-tests.yaml \
  --output support-benchmark.html
```

#### Test on Your Own Data

```bash
# Use your actual prompts
llm benchmark \
  --models gpt-4o,gpt-4o-mini \
  --test-from prompts.txt \
  --evaluate-by similarity \
  --reference expected-outputs.txt
```

### Metrics Collected

#### Speed Metrics

- **Time to First Token (TTFT)** - How quickly response starts
- **Total Response Time** - Complete response duration
- **Tokens per Second** - Generation speed

#### Cost Metrics

- **Cost per Test** - Individual test cost
- **Average Cost** - Mean across all tests
- **Cost Efficiency** - Quality per dollar

#### Quality Metrics

- **Task Success Rate** - Percentage of correct responses
- **Output Quality** - Subjective quality score
- **Consistency** - Variation across runs
- **Format Compliance** - Follows instructions

### Benchmark Reports

#### Terminal Output

Simple comparison table:

```bash
llm benchmark --models gpt-4o,gpt-4o-mini --suite general
```

#### HTML Report

Detailed interactive report:

```bash
llm benchmark \
  --models gpt-4o,gpt-4o-mini,claude-opus \
  --suite code-generation \
  --output benchmark-report.html
```

Features:
- Sortable tables
- Interactive charts
- Detailed breakdowns
- Example outputs

#### JSON Export

For programmatic analysis:

```bash
llm benchmark \
  --models gpt-4o,gpt-4o-mini \
  --suite general \
  --export results.json
```

#### CSV Export

For spreadsheet analysis:

```bash
llm benchmark \
  --models gpt-4o,gpt-4o-mini \
  --suite general \
  --export results.csv
```

## Command Reference

### `llm benchmark`

Run model benchmarks.

```bash
llm benchmark [OPTIONS]
```

**Required:**
- `--models TEXT` - Comma-separated model names

**Test Selection:**
- `--suite NAME` - Built-in suite: general, code, writing, translation, reasoning
- `--custom-suite FILE` - Custom YAML test suite
- `--test-from FILE` - Test prompts from file
- `--categories TEXT` - Test categories to include

**Execution:**
- `--runs N` - Runs per test (default: 3)
- `--parallel` - Run models in parallel
- `--timeout N` - Timeout per test in seconds

**Evaluation:**
- `--evaluate-by METHOD` - Evaluation method
- `--reference FILE` - Reference outputs for comparison
- `--scorer FILE` - Custom scoring function

**Output:**
- `--output FILE` - Save report to file (.html, .json, .csv)
- `--format FORMAT` - Output format: table, html, json, csv
- `--verbose` - Show detailed progress
- `--save-name NAME` - Save benchmark for later reference

### `llm benchmark list`

List saved benchmarks.

```bash
llm benchmark list
```

### `llm benchmark show`

Show benchmark results.

```bash
llm benchmark show BENCHMARK_ID
```

### `llm benchmark compare`

Compare multiple benchmark runs.

```bash
llm benchmark compare BENCHMARK_ID1 BENCHMARK_ID2
```

### `llm benchmark suites`

List available test suites.

```bash
llm benchmark suites
```

## Real-World Examples

### Example 1: Choose Model for Production

```bash
# Benchmark top candidates
llm benchmark \
  --models gpt-4o,gpt-4o-mini,claude-opus \
  --suite general \
  --runs 5 \
  --output production-benchmark.html

# Review results
# Decision: gpt-4o-mini (95% quality of gpt-4o at 20% cost)
```

### Example 2: Code Assistant Selection

```bash
# Test code generation capabilities
llm benchmark \
  --models gpt-4o,claude-opus,gpt-4o-mini \
  --suite code-generation \
  --runs 3 \
  --output code-assistant-benchmark.html

# Result: claude-opus best for complex code, gpt-4o-mini for simple tasks
```

### Example 3: Translation Service

```bash
# Test translation quality
llm benchmark \
  --models gpt-4o,gpt-4o-mini \
  --suite translation \
  --evaluate-by similarity \
  --reference professional-translations.txt \
  --output translation-benchmark.html
```

### Example 4: Customer Support Bot

```bash
# Create custom support benchmark
cat > support-tests.yaml << 'EOF'
name: Support Bot Tests
tests:
  - name: Refund Request
    prompt: "Customer wants refund for late delivery"
  - name: Technical Issue
    prompt: "Password reset not working"
  - name: Product Question
    prompt: "What's the difference between Pro and Basic plans?"
EOF

llm benchmark \
  --models gpt-4o-mini,claude-haiku \
  --custom-suite support-tests.yaml \
  --runs 5
```

### Example 5: Cost Optimization

```bash
# Find cheapest acceptable model
llm benchmark \
  --models gpt-4o,gpt-4o-mini,claude-haiku \
  --suite general \
  --min-quality 8.0 \
  --optimize-for cost

# Output: Shows cheapest model that meets quality threshold
```

## Understanding Results

### Sample Report

```
Model Benchmark Report
══════════════════════════════════════════════════════════════

Suite: General Purpose
Date: 2024-11-16 15:30:00
Tests: 25 | Runs per test: 3

OVERALL RANKINGS:

1. claude-opus
   Quality: 9.4/10 (Excellent)
   Speed: 1.5s avg (Good)
   Cost: $0.045 avg (High)
   Grade: A+
   Best for: High-quality tasks, critical work

2. gpt-4o
   Quality: 9.2/10 (Excellent)
   Speed: 1.2s avg (Very Good)
   Cost: $0.023 avg (Medium)
   Grade: A
   Best for: Balanced quality and cost

3. gpt-4o-mini
   Quality: 8.5/10 (Very Good)
   Speed: 0.8s avg (Excellent)
   Cost: $0.004 avg (Very Low)
   Grade: A-
   Best for: High-volume, cost-sensitive tasks

DETAILED METRICS:

Category: Factual Q&A
  claude-opus:  9.7/10  |  $0.032
  gpt-4o:       9.5/10  |  $0.018
  gpt-4o-mini:  8.9/10  |  $0.003

Category: Creative Writing
  claude-opus:  9.6/10  |  $0.067
  gpt-4o:       9.3/10  |  $0.035
  gpt-4o-mini:  8.4/10  |  $0.006

[...]

RECOMMENDATIONS:

For maximum quality: claude-opus
For best value: gpt-4o-mini
For balanced needs: gpt-4o
For speed: gpt-4o-mini
```

### Interpreting Scores

- **9.0-10.0** - Excellent, production-ready
- **8.0-8.9** - Very good, suitable for most tasks
- **7.0-7.9** - Good, acceptable for non-critical work
- **6.0-6.9** - Fair, may need review
- **Below 6.0** - Poor, not recommended

## Configuration

`~/.llm/benchmark-config.yaml`:

```yaml
benchmarking:
  default_runs: 3
  parallel_execution: true
  timeout: 60
  save_results: true

scoring:
  quality_weight: 0.5
  speed_weight: 0.3
  cost_weight: 0.2

thresholds:
  min_quality: 7.0
  max_acceptable_cost: 0.10
  max_acceptable_time: 5.0

reporting:
  default_format: html
  include_examples: true
  show_raw_responses: false
  chart_style: modern
```

## Best Practices

1. **Run multiple times** - Account for variance (3-5 runs recommended)
2. **Test on real tasks** - Use prompts similar to production use
3. **Consider all metrics** - Quality, speed, and cost together
4. **Update regularly** - Models improve, re-benchmark quarterly
5. **Document decisions** - Save benchmarks to justify model choices
6. **Test incrementally** - Start with 2-3 models, expand if needed

## Troubleshooting

### Benchmark Takes Too Long

**Problem:** Testing many models is slow.

**Solutions:**
```bash
# Reduce runs
llm benchmark --runs 2

# Test fewer models initially
llm benchmark --models gpt-4o,gpt-4o-mini

# Enable parallel
llm benchmark --parallel

# Use shorter suite
llm benchmark --suite quick
```

### Inconsistent Results

**Problem:** Scores vary widely between runs.

**Solutions:**
```bash
# Increase runs for statistical significance
llm benchmark --runs 10

# Set temperature to 0 for consistency
llm benchmark --temperature 0

# Use larger test suite
llm benchmark --suite comprehensive
```

### Can't Compare Models

**Problem:** Don't have access to all models.

**Solution:**
```bash
# Benchmark available models only
llm models list
llm benchmark --models <available-models>

# Use community benchmark results
llm benchmark compare --community
```

## Python API

```python
from llm import run_benchmark

results = run_benchmark(
    models=["gpt-4o", "gpt-4o-mini", "claude-opus"],
    suite="general",
    runs=3
)

print(f"Winner: {results.winner()}")
print(f"Best value: {results.best_value()}")
print(f"Fastest: {results.fastest()}")

# Export
results.to_html("benchmark.html")
results.to_json("benchmark.json")
```

## Continuous Benchmarking

### Automated Weekly Benchmarks

```bash
#!/bin/bash
# weekly-benchmark.sh

MODELS="gpt-4o,gpt-4o-mini,claude-opus"
DATE=$(date +%Y-%m-%d)

llm benchmark \
  --models $MODELS \
  --suite general \
  --output ~/benchmarks/benchmark-$DATE.html \
  --export ~/benchmarks/benchmark-$DATE.json

echo "Benchmark complete: ~/benchmarks/benchmark-$DATE.html"
```

Schedule:
```bash
crontab -e
# Add: 0 0 * * 0 ~/weekly-benchmark.sh
```

## Conclusion

Model benchmarking enables:
- **Informed decisions** - Choose models based on data
- **Cost optimization** - Find best value models
- **Quality assurance** - Ensure models meet standards
- **Performance tracking** - Monitor changes over time
- **Risk reduction** - Avoid poor model choices

Start benchmarking to optimize your model selection!
