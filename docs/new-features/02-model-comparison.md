# Feature 2: Model Comparison

## Motivation

Different AI models have different strengths and weaknesses. Sometimes you need to:
- **Compare quality** - Which model gives better answers for your specific task?
- **Choose the right model** - Is the expensive model worth the cost?
- **Verify consistency** - Do different models agree on important facts?
- **Evaluate trade-offs** - Balance speed, cost, and quality

Currently, you must run the same prompt multiple times manually and compare results yourself. Model comparison automates this process, running your prompt across multiple models simultaneously and presenting results side-by-side for easy evaluation.

## Overview

The `llm compare` command runs identical prompts across multiple AI models and displays the results in an organized, easy-to-compare format.

**What you can do:**
- Run the same prompt on 2-10 different models at once
- See responses side-by-side in your terminal
- Export comparisons to HTML, Markdown, or JSON
- Track which model is fastest, cheapest, or best quality
- Make data-driven decisions about which model to use
- Compare both cloud and local models

## Installation Dependencies

### Basic Installation

Model comparison is built into LLM and requires no extra packages:

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Optional Dependencies

For rich terminal output with colors and formatting:
```bash
pip install rich
```

For HTML export with styling:
```bash
pip install jinja2
```

For side-by-side diff visualization:
```bash
pip install difflib
```

### Model Access

You'll need API keys for models you want to compare:

```bash
# OpenAI models
llm keys set openai

# Anthropic Claude (requires plugin)
llm install llm-anthropic
llm keys set anthropic

# Google Gemini (requires plugin)
llm install llm-gemini
llm keys set gemini

# Local models via Ollama (requires plugin)
llm install llm-ollama
```

### Verification

```bash
# Check available models
llm models list

# Verify you have at least 2 models available
llm models list | wc -l
```

## Implementation Details

### Architecture

The model comparison feature consists of:

1. **Comparison Engine** (`llm/comparison_engine.py`)
   - Manages concurrent model execution
   - Normalizes responses from different model types
   - Tracks timing and token usage for each model
   - Handles errors gracefully (skips failed models)

2. **Response Formatter** (`llm/comparison_formatter.py`)
   - Renders side-by-side text comparison
   - Generates HTML output with syntax highlighting
   - Creates markdown tables
   - Exports JSON for programmatic analysis

3. **Evaluation Metrics** (`llm/comparison_metrics.py`)
   - Response time measurement
   - Token usage tracking
   - Cost calculation per model
   - Response length analysis
   - Optional similarity scoring

4. **CLI Integration** (`llm/cli.py`)
   - New `compare` command
   - Options for models, output format, evaluation criteria

### Data Flow

```
User Prompt → Comparison Engine → Parallel Model Execution
                                           ↓
                                   [Model 1, Model 2, ...]
                                           ↓
                                   Response Aggregator
                                           ↓
                               Formatter (terminal/HTML/JSON)
                                           ↓
                                   Display or Save
```

### Database Schema Addition

Store comparison runs for later analysis:

```sql
CREATE TABLE comparisons (
    id TEXT PRIMARY KEY,
    created_at TEXT,
    prompt TEXT,
    system_prompt TEXT,
    models TEXT,  -- JSON array of model IDs
    responses JSON,  -- Array of response objects
    metrics JSON,  -- Timing, tokens, costs
    winner TEXT,  -- Optional: user-selected best model
    notes TEXT
);
```

## Usage Instructions

### For Complete Beginners

Think of model comparison like asking the same question to multiple experts and comparing their answers. Instead of talking to each expert separately and trying to remember what they said, the tool does this automatically and shows you all answers together so you can easily see the differences.

### Basic Usage

#### Compare Two Models

The simplest comparison between two models:

```bash
llm compare -m gpt-4o -m gpt-4o-mini "Explain quantum computing in simple terms"
```

This runs your prompt on both models and shows results side-by-side.

#### Compare More Models

Add as many models as you want:

```bash
llm compare \
  -m gpt-4o \
  -m gpt-4o-mini \
  -m claude-opus \
  "What is the capital of France and why is it important?"
```

### Understanding the Output

**Terminal Output Example:**

```
╔══════════════════════════════════════════════════════════════╗
║                    MODEL COMPARISON                          ║
╠══════════════════════════════════════════════════════════════╣
║ Prompt: Explain quantum computing in simple terms           ║
║ Models: 3 | Time: 2024-11-16 10:30:45                      ║
╚══════════════════════════════════════════════════════════════╝

┌─────────────────────────────────────────────────────────────┐
│ MODEL: gpt-4o                                               │
│ Time: 1.2s | Tokens: 150 | Cost: $0.0023                  │
├─────────────────────────────────────────────────────────────┤
│ Quantum computing uses quantum mechanics principles like    │
│ superposition and entanglement to process information.      │
│ Unlike classical bits (0 or 1), quantum bits (qubits) can  │
│ exist in multiple states simultaneously...                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ MODEL: gpt-4o-mini                                          │
│ Time: 0.8s | Tokens: 120 | Cost: $0.0006                  │
├─────────────────────────────────────────────────────────────┤
│ Quantum computers are special computers that use quantum    │
│ physics to solve certain problems much faster than regular  │
│ computers. They use "qubits" instead of regular bits...     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ MODEL: claude-opus                                          │
│ Time: 1.5s | Tokens: 180 | Cost: $0.0045                  │
├─────────────────────────────────────────────────────────────┤
│ Think of quantum computing as a fundamentally different     │
│ approach to computation. While traditional computers use    │
│ bits that are either 0 or 1, quantum computers use qubits...│
└─────────────────────────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════╗
║                       SUMMARY                                ║
╠══════════════════════════════════════════════════════════════╣
║ Fastest: gpt-4o-mini (0.8s)                                 ║
║ Cheapest: gpt-4o-mini ($0.0006)                            ║
║ Longest response: claude-opus (180 tokens)                  ║
╚══════════════════════════════════════════════════════════════╝
```

### Saving Comparisons

#### Save as HTML

Generate a shareable HTML report:

```bash
llm compare -m gpt-4o -m claude-opus \
  "Write a haiku about programming" \
  --output comparison.html
```

Open `comparison.html` in your browser to see a formatted comparison with syntax highlighting.

#### Save as Markdown

```bash
llm compare -m gpt-4o -m gpt-4o-mini \
  "List 5 benefits of exercise" \
  --output comparison.md
```

#### Save as JSON

For programmatic analysis:

```bash
llm compare -m gpt-4o -m gpt-4o-mini \
  "Explain photosynthesis" \
  --output comparison.json
```

### Advanced Options

#### Use System Prompts

Apply the same system prompt to all models:

```bash
llm compare -m gpt-4o -m claude-opus \
  --system "You are a helpful teacher explaining to a 10-year-old" \
  "What is gravity?"
```

#### Compare with Attachments

Send images or files to multimodal models:

```bash
llm compare -m gpt-4o -m claude-opus \
  -a photo.jpg \
  "What's in this image?"
```

#### Use Templates

Compare models using saved templates:

```bash
llm compare -m gpt-4o -m gpt-4o-mini \
  --template summarize \
  "Long article text here..."
```

#### Show Diff Highlighting

Highlight differences between responses:

```bash
llm compare -m gpt-4o -m gpt-4o-mini \
  "Write a Python function to calculate factorial" \
  --diff
```

#### Rate Responses

Interactively rate which response is better:

```bash
llm compare -m gpt-4o -m claude-opus \
  "Write a creative story about a robot" \
  --rate
```

This prompts you to select the best response, which is saved for future reference.

### Batch Comparison

Compare models across multiple prompts:

```bash
llm compare -m gpt-4o -m gpt-4o-mini \
  --input prompts.txt \
  --output results.html
```

Where `prompts.txt` contains:
```
What is machine learning?
What is deep learning?
What is neural network?
```

## Command Reference

### `llm compare`

Compare responses from multiple models.

```bash
llm compare [OPTIONS] PROMPT
```

**Arguments:**
- `PROMPT` - The prompt to send to all models

**Options:**
- `-m, --model TEXT` - Model to include (repeat for each model)
- `-s, --system TEXT` - System prompt for all models
- `-a, --attachment PATH` - Attach file/image to prompts
- `--output PATH` - Save comparison to file (.html, .md, .json)
- `--diff` - Show highlighted differences
- `--rate` - Interactively rate responses
- `--template NAME` - Use a saved template
- `--input FILE` - Compare across multiple prompts from file
- `--format FORMAT` - Output format: table, json, html, markdown
- `--show-metrics` - Display detailed metrics (tokens, cost, time)
- `--parallel/--sequential` - Run models in parallel or one-by-one
- `--timeout SECONDS` - Timeout per model (default: 60)
- `--save` - Save comparison to database

**Examples:**

```bash
# Basic comparison
llm compare -m gpt-4o -m claude-opus "What is AI?"

# With system prompt
llm compare -m gpt-4o -m gpt-4o-mini \
  -s "Be concise" "Explain blockchain"

# Save to HTML
llm compare -m gpt-4o -m claude-opus \
  "Write a poem" --output poem_comparison.html

# Compare with image
llm compare -m gpt-4o -m claude-opus \
  -a diagram.png "Explain this diagram"

# Show differences
llm compare -m gpt-4o -m gpt-4o-mini \
  "Write Python code for Fibonacci" --diff
```

### `llm compare list`

View saved comparisons.

```bash
llm compare list [OPTIONS]
```

**Options:**
- `--limit N` - Show last N comparisons
- `--models TEXT` - Filter by models used

### `llm compare show`

Display a saved comparison.

```bash
llm compare show COMPARISON_ID [OPTIONS]
```

**Options:**
- `--format FORMAT` - Display format: table, html, markdown

## Configuration

### Default Comparison Models

Set your preferred models for quick comparisons in `~/.llm/compare-config.yaml`:

```yaml
default_models:
  - gpt-4o
  - gpt-4o-mini
  - claude-opus

display:
  format: table
  show_metrics: true
  diff_highlighting: true
  color_scheme: auto

shortcuts:
  quick: [gpt-4o-mini, claude-haiku]
  quality: [gpt-4o, claude-opus]
  local: [llama3.2:latest, mistral:latest]
```

Use shortcuts:

```bash
llm compare --preset quality "Complex analysis question"
```

### Cost Tracking

Enable cost tracking for comparisons:

```yaml
cost_tracking:
  enabled: true
  warn_threshold: 0.10  # Warn if comparison costs > $0.10
  monthly_budget: 50.00
```

## Real-World Examples

### Example 1: Choose Model for Content Generation

**Scenario:** You're building a blog post generator and need to choose between models.

```bash
llm compare \
  -m gpt-4o \
  -m gpt-4o-mini \
  -m claude-opus \
  --system "You are a professional content writer" \
  "Write a 100-word introduction about sustainable living" \
  --output blog_comparison.html \
  --rate
```

Review the HTML output, rate the responses, then use `gpt-4o-mini` for production since it's faster and cheaper with good quality.

### Example 2: Verify Factual Accuracy

**Scenario:** You need accurate historical information.

```bash
llm compare \
  -m gpt-4o \
  -m claude-opus \
  -m gemini-pro \
  "List the major events of World War II in chronological order" \
  --diff
```

Check if all models agree on facts. Disagreements might indicate potential errors.

### Example 3: Code Generation Quality

**Scenario:** Compare code quality across models.

```bash
llm compare \
  -m gpt-4o \
  -m claude-opus \
  -m gpt-4o-mini \
  "Write a Python function to find all prime numbers up to n" \
  --output code_comparison.html \
  --show-metrics
```

Test the generated code from each model to see which produces the best implementation.

### Example 4: Translation Quality

**Scenario:** Compare translation accuracy.

```bash
llm compare \
  -m gpt-4o \
  -m claude-opus \
  "Translate this to French: 'The quick brown fox jumps over the lazy dog'" \
  --diff
```

### Example 5: Creative Writing Styles

**Scenario:** Evaluate creative output diversity.

```bash
llm compare \
  -m gpt-4o \
  -m claude-opus \
  -m gpt-4o-mini \
  --system "Write in a creative, engaging style" \
  "Write the opening paragraph of a sci-fi novel" \
  --output creative_comparison.html
```

## Evaluation Criteria

### What to Look For

When comparing model outputs, consider:

1. **Accuracy** - Are facts correct?
2. **Relevance** - Does it answer the question?
3. **Clarity** - Is it easy to understand?
4. **Completeness** - Does it cover all aspects?
5. **Tone** - Is the tone appropriate?
6. **Cost** - Is the quality worth the price?
7. **Speed** - How long did it take?

### Metrics Automatically Tracked

- **Response Time** - Seconds from request to complete response
- **Token Count** - Input and output tokens
- **Cost** - Estimated API cost
- **Response Length** - Characters and words
- **Model Version** - Exact model ID used

## Integration with Other Features

### Compare with Templates

```bash
llm compare -m gpt-4o -m claude-opus \
  --template email-writer \
  --input customer_requests.txt
```

### Compare with Tools

Enable tool use for all models:

```bash
llm compare -m gpt-4o -m claude-opus \
  --tools python,fetch \
  "What's the current weather in Tokyo?"
```

### Compare Embeddings Quality

Compare embedding models by testing similarity search:

```bash
llm compare-embeddings \
  -m ada-002 \
  -m text-embedding-3-large \
  --query "machine learning" \
  --test-set tech_terms.txt
```

## Troubleshooting

### Models Have Different Capabilities

**Problem:** Some models support images, others don't.

**Solution:** Use `--skip-unsupported` to automatically skip models that can't handle your request:

```bash
llm compare -m gpt-4o -m gpt-3.5-turbo \
  -a image.png "Describe this" \
  --skip-unsupported
```

### Comparison Takes Too Long

**Problem:** Comparing many models sequentially is slow.

**Solution:** Enable parallel execution:

```bash
llm compare -m gpt-4o -m claude-opus -m gemini-pro \
  "Your prompt" --parallel
```

### Cost Concerns

**Problem:** Worried about API costs from multiple models.

**Solution:** Use `--estimate` to see costs before running:

```bash
llm compare -m gpt-4o -m claude-opus \
  "Long prompt..." --estimate
```

Output:
```
Estimated costs:
  gpt-4o: $0.0045
  claude-opus: $0.0052
  Total: $0.0097

Proceed? (y/n):
```

### One Model Fails

**Problem:** One model returns an error but others succeed.

**Solution:** Comparison continues with successful models. Failed models show error message:

```
┌─────────────────────────────────────────┐
│ MODEL: claude-opus                      │
│ ERROR: Rate limit exceeded              │
├─────────────────────────────────────────┤
│ Try again in a few minutes              │
└─────────────────────────────────────────┘
```

## Python API

For developers integrating comparison in code:

```python
from llm import compare_models

result = compare_models(
    prompt="Explain recursion",
    models=["gpt-4o", "claude-opus", "gpt-4o-mini"],
    system="You are a computer science teacher"
)

for model_result in result.responses:
    print(f"{model_result.model}: {model_result.text}")
    print(f"  Time: {model_result.time}s")
    print(f"  Cost: ${model_result.cost}")
    print()

# Get best by criteria
fastest = result.fastest()
cheapest = result.cheapest()
longest = result.longest()

print(f"Fastest: {fastest.model}")
print(f"Cheapest: {cheapest.model}")
```

## Export Formats

### HTML Output

Generates a beautiful, interactive comparison page with:
- Syntax highlighting for code
- Collapsible sections
- Copy buttons for each response
- Filtering and sorting
- Mobile-responsive design

### Markdown Output

Creates a clean markdown table:

```markdown
# Model Comparison

**Prompt:** Explain recursion

| Model | Response | Time | Cost | Tokens |
|-------|----------|------|------|--------|
| gpt-4o | Recursion is... | 1.2s | $0.002 | 150 |
| claude-opus | A recursive function... | 1.5s | $0.004 | 180 |
```

### JSON Output

```json
{
  "comparison_id": "cmp_abc123",
  "timestamp": "2024-11-16T10:30:45Z",
  "prompt": "Explain recursion",
  "system_prompt": null,
  "models": [
    {
      "model_id": "gpt-4o",
      "response": "Recursion is...",
      "time_seconds": 1.2,
      "tokens": {"input": 10, "output": 150},
      "cost": 0.002
    },
    {
      "model_id": "claude-opus",
      "response": "A recursive function...",
      "time_seconds": 1.5,
      "tokens": {"input": 10, "output": 180},
      "cost": 0.004
    }
  ]
}
```

## Best Practices

1. **Start with 2-3 models** - Too many makes comparison harder
2. **Use consistent prompts** - Small wording changes affect results
3. **Test multiple examples** - One prompt isn't enough to judge
4. **Consider cost vs. quality** - Expensive ≠ always better
5. **Save important comparisons** - Use `--save` for future reference
6. **Use system prompts** - Ensure fair comparison with same instructions
7. **Track your findings** - Note which models work best for which tasks

## Conclusion

Model comparison helps you make informed decisions about which AI model to use. Benefits include:
- Save money by finding the best cost/quality balance
- Improve accuracy by verifying facts across models
- Speed up development by choosing the fastest adequate model
- Build confidence in AI outputs through cross-validation

Start comparing models today to optimize your LLM workflows!
