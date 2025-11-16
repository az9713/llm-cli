# Feature 1: Batch Processing

## Motivation

Many users need to process multiple prompts at once for tasks like:
- Analyzing hundreds of customer reviews
- Translating multiple documents
- Generating descriptions for product catalogs
- Running the same question across different datasets

Currently, users must run prompts one at a time, which is time-consuming and inefficient. Batch processing allows you to submit many prompts at once and process them efficiently, saving time and enabling bulk data analysis.

## Overview

The `llm batch` command processes multiple prompts from structured data files (CSV, JSON, or text files). It runs each prompt through your chosen language model and saves the results in an organized format.

**What you can do:**
- Process 100s or 1000s of prompts automatically
- Read prompts from CSV files with multiple columns
- Save results to files for further analysis
- Track progress with a visual progress bar
- Resume failed batches automatically
- Control rate limits to avoid API throttling

## Installation Dependencies

### Basic Installation

If you already have LLM installed, batch processing requires no additional Python packages. However, you'll need:

1. **Python 3.9 or higher** - The programming language that runs LLM
2. **LLM CLI tool** - Install with:
   ```bash
   pip install llm
   ```

### Optional Dependencies

For better progress visualization:
```bash
pip install tqdm
```

For Excel file support (`.xlsx`):
```bash
pip install openpyxl
```

### Verification

Check that everything is installed:
```bash
# Check Python version (should be 3.9+)
python --version

# Check LLM is installed
llm --version

# Check tqdm (optional)
python -c "import tqdm; print('tqdm installed')"
```

## Implementation Details

### Architecture

The batch processing feature consists of:

1. **Input Parser** (`llm/batch_parser.py`)
   - Reads CSV, JSON, JSONL, or text files
   - Validates data structure
   - Supports variable substitution in templates

2. **Batch Executor** (`llm/batch_executor.py`)
   - Manages parallel/sequential execution
   - Handles rate limiting
   - Implements retry logic for failed prompts
   - Tracks progress and saves checkpoints

3. **Output Writer** (`llm/batch_writer.py`)
   - Formats results as CSV, JSON, or JSONL
   - Appends results to SQLite logs database
   - Generates summary reports

4. **CLI Integration** (`llm/cli.py`)
   - New `batch` command group
   - Options for concurrency, rate limits, output format

### Data Flow

```
Input File → Parser → Queue → Executor (with rate limiting) → Writer → Output File
                                    ↓
                              SQLite Logs (optional)
```

### Database Schema Addition

A new table `batch_runs` tracks batch processing jobs:

```sql
CREATE TABLE batch_runs (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    input_file TEXT,
    output_file TEXT,
    model TEXT,
    total_prompts INTEGER,
    completed_prompts INTEGER,
    failed_prompts INTEGER,
    status TEXT,  -- 'running', 'completed', 'failed', 'paused'
    config JSON   -- rate limits, options
);
```

## Usage Instructions

### For Complete Beginners

Think of batch processing like a factory assembly line for questions. Instead of asking a question, waiting for an answer, then asking another question, you write down all your questions in a file, and the system processes them all automatically.

### Basic Usage

#### Step 1: Create Your Input File

Create a simple text file called `questions.txt` with one prompt per line:

```
What is the capital of France?
What is the capital of Germany?
What is the capital of Italy?
```

#### Step 2: Run the Batch Command

```bash
llm batch questions.txt
```

This will:
1. Read each line from your file
2. Send it to the AI model
3. Display results on screen
4. Save all results to the logs database

#### Step 3: View Results

Results are automatically saved in your logs:

```bash
llm logs -n 10
```

### Using CSV Files

CSV files let you organize data in columns (like a spreadsheet).

#### Example CSV (`products.csv`):

```csv
product_name,description
Laptop,"A portable computer"
Phone,"A mobile communication device"
Tablet,"A touchscreen computing device"
```

#### Using Templates with CSV Data

```bash
llm batch products.csv \
  --template "Write a 50-word marketing description for a {product_name}. Context: {description}" \
  --output results.csv
```

This takes each row and replaces `{product_name}` and `{description}` with values from your CSV.

### JSON Input Files

JSON is a structured data format (like organized notes).

#### Example JSON (`reviews.json`):

```json
[
  {"review": "Great product, very satisfied!", "rating": 5},
  {"review": "Decent but overpriced", "rating": 3},
  {"review": "Terrible quality", "rating": 1}
]
```

#### Process JSON Data

```bash
llm batch reviews.json \
  --template "Analyze this review sentiment: {review}" \
  --output analysis.json
```

### Advanced Options

#### Control Processing Speed

Limit to 10 prompts per minute to avoid hitting API rate limits:

```bash
llm batch questions.txt --rate-limit 10
```

#### Process Multiple Prompts Simultaneously

Run 5 prompts at the same time (faster but uses more API quota):

```bash
llm batch questions.txt --concurrency 5
```

#### Use a Specific Model

```bash
llm batch questions.txt --model gpt-4o
```

#### Save to a Specific Output File

```bash
llm batch questions.txt --output my_results.csv
```

#### Resume a Failed Batch

If batch processing fails midway:

```bash
llm batch questions.txt --resume
```

This continues from where it stopped.

### Complete Example Workflow

**Scenario:** You have 100 customer reviews and want to analyze sentiment.

1. **Create CSV file** (`reviews.csv`):
   ```csv
   customer_id,review_text
   1001,"Amazing product! Highly recommend."
   1002,"Not worth the money."
   1003,"Good quality, fast shipping."
   ```

2. **Run batch analysis**:
   ```bash
   llm batch reviews.csv \
     --template "Analyze sentiment (positive/negative/neutral): {review_text}" \
     --output sentiment_results.csv \
     --model gpt-4o-mini \
     --rate-limit 20 \
     --concurrency 3
   ```

3. **Check results** in `sentiment_results.csv`:
   ```csv
   customer_id,review_text,response
   1001,"Amazing product! Highly recommend.","Sentiment: Positive"
   1002,"Not worth the money.","Sentiment: Negative"
   1003,"Good quality, fast shipping.","Sentiment: Positive"
   ```

## Command Reference

### `llm batch`

Process multiple prompts from a file.

```bash
llm batch INPUT_FILE [OPTIONS]
```

**Arguments:**
- `INPUT_FILE` - Path to input file (`.txt`, `.csv`, `.json`, `.jsonl`)

**Options:**
- `--template TEXT` - Prompt template with {variable} placeholders
- `--output PATH` - Save results to this file
- `--model NAME` - Model to use (default: your default model)
- `--system TEXT` - System prompt for all requests
- `--rate-limit N` - Maximum prompts per minute
- `--concurrency N` - Number of parallel requests (default: 1)
- `--resume` - Resume a previously failed batch
- `--batch-id TEXT` - Custom ID for this batch run
- `--stop-on-error` - Stop processing if any prompt fails
- `--format FORMAT` - Output format: csv, json, jsonl (auto-detected)
- `--no-log` - Don't save to logs database

**Examples:**

```bash
# Simple text file
llm batch prompts.txt

# CSV with template
llm batch data.csv --template "Summarize: {text}"

# JSON with rate limiting
llm batch items.json --rate-limit 30 --concurrency 2

# Specific model and output
llm batch reviews.csv --model claude-opus --output analysis.json
```

### `llm batch list`

View all batch processing runs.

```bash
llm batch list [OPTIONS]
```

**Options:**
- `--status STATUS` - Filter by status: running, completed, failed
- `--limit N` - Show last N batches (default: 20)

### `llm batch status`

Check status of a specific batch run.

```bash
llm batch status BATCH_ID
```

Shows:
- Total prompts
- Completed prompts
- Failed prompts
- Estimated time remaining
- Current rate

### `llm batch cancel`

Stop a running batch.

```bash
llm batch cancel BATCH_ID
```

## Configuration

### Setting Default Batch Options

Create or edit `~/.llm/batch-config.yaml`:

```yaml
defaults:
  concurrency: 3
  rate_limit: 20
  model: gpt-4o-mini
  resume_on_failure: true

rate_limits:
  gpt-4o: 30
  gpt-4o-mini: 60
  claude-opus: 10

output:
  format: json
  save_to_logs: true
```

## Error Handling

### Common Errors

**Error: "Rate limit exceeded"**
```
Solution: Reduce --rate-limit value or wait a few minutes
```

**Error: "Template variable not found: {name}"**
```
Solution: Check your CSV/JSON has a column/field named "name"
```

**Error: "Invalid API key"**
```
Solution: Set your API key: llm keys set openai
```

**Error: "Input file not found"**
```
Solution: Check file path is correct and file exists
```

### Resume After Failure

If batch processing stops:

1. **Check what failed:**
   ```bash
   llm batch status <batch-id>
   ```

2. **Resume processing:**
   ```bash
   llm batch questions.txt --resume --batch-id <batch-id>
   ```

## Performance Tips

1. **Use concurrency for large batches:**
   ```bash
   llm batch large_file.csv --concurrency 5
   ```

2. **Choose the right model:**
   - `gpt-4o-mini` - Fastest and cheapest for simple tasks
   - `gpt-4o` - Better quality for complex analysis

3. **Set appropriate rate limits:**
   - Free tier: `--rate-limit 3`
   - Pay-as-you-go: `--rate-limit 60`

4. **Save output to files for large batches:**
   ```bash
   llm batch huge_file.csv --output results.json
   ```

## Troubleshooting

### Batch Runs Very Slowly

**Problem:** Processing 100 prompts takes hours.

**Solutions:**
- Increase concurrency: `--concurrency 10`
- Use a faster model: `--model gpt-4o-mini`
- Check your internet connection

### Results Are Empty

**Problem:** Output file is created but has no content.

**Solutions:**
- Check your template is correct
- Verify API key is set: `llm keys path openai`
- Look at error messages in: `llm batch status <id>`

### Out of Memory Errors

**Problem:** Program crashes with large files.

**Solutions:**
- Use JSONL instead of JSON format
- Process in smaller chunks
- Reduce concurrency: `--concurrency 1`

## Real-World Examples

### Example 1: Translate Product Descriptions

**Input:** `products.csv`
```csv
id,english_description
P001,"High quality leather wallet"
P002,"Stainless steel water bottle"
P003,"Wireless bluetooth headphones"
```

**Command:**
```bash
llm batch products.csv \
  --template "Translate to Spanish: {english_description}" \
  --output products_spanish.csv \
  --model gpt-4o-mini
```

### Example 2: Classify Support Tickets

**Input:** `tickets.json`
```json
[
  {"ticket_id": "T-100", "message": "My order hasn't arrived"},
  {"ticket_id": "T-101", "message": "How do I reset my password?"},
  {"ticket_id": "T-102", "message": "Billing charge error"}
]
```

**Command:**
```bash
llm batch tickets.json \
  --template "Classify this support ticket into: Shipping, Account, Billing, or Other. Ticket: {message}" \
  --output classified_tickets.json \
  --rate-limit 30
```

### Example 3: Generate Social Media Posts

**Input:** `blog_posts.csv`
```csv
title,summary
"10 Tips for Better Sleep","Learn proven strategies to improve sleep quality"
"Healthy Meal Prep Ideas","Quick and nutritious meal prep for busy professionals"
```

**Command:**
```bash
llm batch blog_posts.csv \
  --template "Write an engaging Twitter post (max 280 chars) for this blog: {title}. Summary: {summary}" \
  --output tweets.csv \
  --model gpt-4o
```

## Integration with Other LLM Features

### Using Batch with Fragments

Reference saved fragments in your templates:

```bash
llm batch data.csv \
  --template "!fragment company-voice Summarize: {text}" \
  --output results.csv
```

### Using Batch with Tools

Enable tools for batch processing:

```bash
llm batch questions.csv \
  --template "Answer: {question}" \
  --tools python \
  --output answers.csv
```

### Logging Batch Results

All batch results are logged to SQLite database by default:

```bash
# View batch results in logs
llm logs --model gpt-4o-mini -n 50

# Search batch results
llm logs --search "sentiment analysis"
```

## API and Python Integration

For developers who want to use batch processing in Python code:

```python
from llm import get_model, batch_process

model = get_model("gpt-4o-mini")

# From Python list
prompts = [
    "What is Python?",
    "What is JavaScript?",
    "What is Rust?"
]

results = batch_process(
    model,
    prompts,
    concurrency=3,
    rate_limit=20
)

for prompt, response in results:
    print(f"Q: {prompt}")
    print(f"A: {response.text()}\n")
```

From CSV:

```python
from llm import get_model, batch_from_csv

model = get_model("gpt-4o")

results = batch_from_csv(
    model,
    "data.csv",
    template="Analyze: {text}",
    output="results.csv",
    rate_limit=30
)
```

## Cost Estimation

Before running large batches, estimate costs:

```bash
llm batch data.csv --estimate-cost
```

Output:
```
Estimated tokens: 45,000 input, 15,000 output
Estimated cost (gpt-4o-mini): $0.68
Estimated time: 3 minutes
Proceed? (y/n):
```

## Conclusion

Batch processing transforms LLM from a one-at-a-time tool to a powerful data processing engine. Use it for:
- Bulk data analysis
- Automated content generation
- Large-scale classification tasks
- Research and experimentation

Start small with a few prompts, then scale up as you get comfortable with the workflow.
