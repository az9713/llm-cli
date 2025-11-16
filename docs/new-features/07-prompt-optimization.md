# Feature 7: Prompt Optimization

## Motivation

Writing effective prompts is critical for getting good AI responses, but it's challenging:
- **Trial and error** - Testing different phrasings manually is time-consuming
- **Unclear what works** - Hard to know why one prompt works better than another
- **Inconsistent results** - Same prompt can give different quality responses
- **No systematic improvement** - No way to methodically improve prompts

Prompt optimization solves this by:
- Automatically testing prompt variations
- Measuring response quality objectively
- Finding the best-performing version
- Learning what makes prompts effective
- Iteratively improving prompts

## Overview

The `llm optimize` command systematically tests prompt variations to find the most effective phrasing.

**What you can do:**
- Test multiple prompt variations automatically
- Define success criteria for evaluating responses
- A/B test different approaches
- Track which prompt elements improve results
- Generate optimized prompts automatically
- Learn prompt engineering best practices

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
pip install numpy scipy
```

For visualization:
```bash
pip install matplotlib plotext
```

### Verification

```bash
llm --version
llm optimize --help
```

## Implementation Details

### Architecture

**Components:**

1. **Variation Generator** (`llm/optimize/variations.py`)
   - Creates prompt variations
   - Systematic modifications
   - Template substitutions

2. **Test Runner** (`llm/optimize/runner.py`)
   - Executes test cases
   - Manages concurrent testing
   - Collects results

3. **Evaluator** (`llm/optimize/evaluator.py`)
   - Scores responses
   - Custom scoring functions
   - Statistical analysis

4. **Optimizer** (`llm/optimize/optimizer.py`)
   - Finds best-performing variations
   - Iterative improvement
   - Hyperparameter tuning

### Optimization Pipeline

```
Base Prompt → Generate Variations → Test All → Evaluate Results → Select Winner
                                                      ↓
                                              (Iterate if needed)
```

### Database Schema

**Table: `prompt_experiments`**
```sql
CREATE TABLE prompt_experiments (
    id TEXT PRIMARY KEY,
    name TEXT,
    base_prompt TEXT,
    created_at TEXT,
    goal TEXT,
    success_criteria TEXT,  -- JSON
    best_prompt TEXT,
    best_score REAL,
    status TEXT  -- 'running', 'completed'
);
```

**Table: `prompt_variations`**
```sql
CREATE TABLE prompt_variations (
    id TEXT PRIMARY KEY,
    experiment_id TEXT,
    variation_text TEXT,
    variation_type TEXT,
    test_count INTEGER,
    avg_score REAL,
    metadata JSON,
    FOREIGN KEY (experiment_id) REFERENCES prompt_experiments(id)
);
```

## Usage Instructions

### For Complete Beginners

Think of prompt optimization like recipe testing. Instead of guessing which ingredients work best, you try different combinations systematically and measure which tastes best. Prompt optimization does the same for AI prompts - it tries different wordings and measures which gets the best responses.

### Basic Usage

#### Simple Optimization

Test different ways to phrase your prompt:

```bash
llm optimize \
  --base "Summarize this article" \
  --goal "Create concise, accurate summaries" \
  --test-input article.txt
```

This:
1. Creates variations like:
   - "Summarize this article concisely"
   - "Provide a brief summary of this article"
   - "Create a summary of the following article"
2. Tests each variation
3. Scores the results
4. Recommends the best version

#### Define Success Criteria

```bash
llm optimize \
  --base "Translate to Spanish: {text}" \
  --criteria "accurate,natural-sounding,preserves-meaning" \
  --test-cases translations-test.json
```

**Test cases file (`translations-test.json`):**
```json
[
  {
    "input": {"text": "Hello, how are you?"},
    "expected": "Hola, ¿cómo estás?"
  },
  {
    "input": {"text": "Thank you very much"},
    "expected": "Muchas gracias"
  }
]
```

### Optimization Strategies

#### Strategy 1: Template Variations

Test different structural approaches:

```bash
llm optimize \
  --base "Explain {concept}" \
  --variations templates \
  --templates "Explain {concept} in simple terms" \
             "What is {concept}? Explain clearly" \
             "Define {concept} and give examples"
```

#### Strategy 2: Tone Variations

Find the best tone:

```bash
llm optimize \
  --base "Write an email about {topic}" \
  --vary tone \
  --tones formal,casual,friendly,professional
```

Generates:
- "Write a formal email about {topic}"
- "Write a casual email about {topic}"
- "Write a friendly email about {topic}"
- "Write a professional email about {topic}"

#### Strategy 3: Detail Level

Optimize level of specificity:

```bash
llm optimize \
  --base "Summarize {text}" \
  --vary detail-level \
  --levels brief,moderate,detailed
```

Generates:
- "Summarize {text} briefly"
- "Provide a moderate summary of {text}"
- "Create a detailed summary of {text}"

#### Strategy 4: Instruction Style

Test different instruction approaches:

```bash
llm optimize \
  --base "Review this code: {code}" \
  --vary instruction-style \
  --styles imperative,question,directive
```

Generates:
- "Review this code: {code}" (imperative)
- "Can you review this code: {code}?" (question)
- "You should review this code: {code}" (directive)

### Advanced Optimization

#### Multi-Dimensional Optimization

Optimize multiple aspects simultaneously:

```bash
llm optimize \
  --base "Process {input}" \
  --vary tone,detail-level,format \
  --test-cases test-set.json \
  --iterations 3
```

This tests combinations like:
- formal + brief + bullet-points
- casual + detailed + paragraphs
- professional + moderate + numbered-list

#### With System Prompts

Optimize system prompts too:

```bash
llm optimize \
  --base "Explain {topic}" \
  --system "You are a helpful teacher" \
  --optimize-system \
  --system-variations "You are an expert educator" \
                      "You are a patient tutor" \
                      "You are a knowledgeable instructor"
```

#### Custom Scoring Function

Define how to evaluate responses:

```bash
llm optimize \
  --base "Generate product description for {product}" \
  --score-function score.py \
  --test-cases products.json
```

**Scoring function (`score.py`):**
```python
def score_response(prompt, response, test_case):
    """
    Return score from 0.0 to 1.0
    """
    score = 0.0

    # Length check (50-150 words ideal)
    word_count = len(response.text().split())
    if 50 <= word_count <= 150:
        score += 0.3

    # Contains key features
    if test_case.get('features'):
        mentioned = sum(1 for f in test_case['features']
                       if f.lower() in response.text().lower())
        score += (mentioned / len(test_case['features'])) * 0.4

    # Engaging (has marketing words)
    marketing_words = ['amazing', 'innovative', 'premium', 'quality']
    if any(w in response.text().lower() for w in marketing_words):
        score += 0.3

    return score
```

#### Iterative Optimization

Run multiple rounds:

```bash
llm optimize \
  --base "Write code to {task}" \
  --iterations 5 \
  --test-cases coding-tasks.json
```

Each iteration:
1. Tests current variations
2. Selects best performers
3. Generates new variations based on winners
4. Repeats

### Evaluation Methods

#### Automatic Evaluation

**By Length:**
```bash
llm optimize --evaluate-by length --target 100
```

**By Keywords:**
```bash
llm optimize --evaluate-by keywords --keywords "key,terms,required"
```

**By Format:**
```bash
llm optimize --evaluate-by format --expected-format "bullet-list"
```

**By Similarity:**
```bash
llm optimize --evaluate-by similarity --reference reference.txt
```

#### Manual Evaluation

Review and rate responses yourself:

```bash
llm optimize --manual-rating --base "Write creative story about {topic}"
```

Shows each variation's response and asks for rating 1-5.

#### Hybrid Evaluation

Combine automatic and manual:

```bash
llm optimize \
  --auto-score length,format \
  --manual-review top-3 \
  --test-cases stories.json
```

## Command Reference

### `llm optimize`

Optimize a prompt through systematic testing.

```bash
llm optimize [OPTIONS]
```

**Required:**
- `--base TEXT` - Base prompt to optimize
- `--test-input FILE` or `--test-cases FILE` - Test data

**Variation Generation:**
- `--variations TYPE` - Variation type: templates, tone, detail, style
- `--templates TEXT...` - Specific template variations
- `--vary ASPECTS` - Aspects to vary (comma-separated)
- `--tones TEXT` - Tones to test
- `--levels TEXT` - Detail levels
- `--styles TEXT` - Instruction styles

**Optimization:**
- `--iterations N` - Number of optimization rounds (default: 1)
- `--optimize-system` - Also optimize system prompt
- `--system TEXT` - Base system prompt
- `--system-variations TEXT...` - System prompt variations

**Evaluation:**
- `--criteria TEXT` - Success criteria (comma-separated)
- `--evaluate-by METHOD` - Evaluation method: length, keywords, format, similarity
- `--score-function FILE` - Custom scoring function
- `--manual-rating` - Manual rating mode
- `--target VALUE` - Target value for evaluation
- `--expected-format FORMAT` - Expected output format

**Execution:**
- `--model TEXT` - Model to use (default: your default)
- `--test-count N` - Tests per variation (default: 3)
- `--parallel` - Run tests in parallel

**Output:**
- `--output FILE` - Save results to file
- `--save-best NAME` - Save best prompt to library
- `--verbose` - Show detailed progress

### `llm optimize list`

List optimization experiments.

```bash
llm optimize list
```

### `llm optimize show`

Show experiment results.

```bash
llm optimize show EXPERIMENT_ID
```

### `llm optimize resume`

Resume a stopped experiment.

```bash
llm optimize resume EXPERIMENT_ID
```

## Real-World Examples

### Example 1: Optimize Email Template

```bash
# Create test cases
cat > email-tests.json << 'EOF'
[
  {
    "input": {"topic": "project delay", "recipient": "client"},
    "criteria": "professional, empathetic, clear next steps"
  },
  {
    "input": {"topic": "price increase", "recipient": "customers"},
    "criteria": "diplomatic, justified, maintains trust"
  }
]
EOF

# Optimize
llm optimize \
  --base "Write an email to {recipient} about {topic}" \
  --vary tone,structure \
  --tones professional,friendly,formal \
  --test-cases email-tests.json \
  --save-best email-template
```

Results show: "Write a professional email to {recipient} regarding {topic}, including clear next steps" performs best.

### Example 2: Code Generation Optimization

```bash
cat > code-tasks.json << 'EOF'
[
  {
    "input": {"task": "sort a list"},
    "language": "python"
  },
  {
    "input": {"task": "reverse a string"},
    "language": "python"
  }
]
EOF

llm optimize \
  --base "Write Python code to {task}" \
  --variations templates \
  --templates \
    "Write Python code to {task}" \
    "Create a Python function that {task}" \
    "Implement {task} in Python with type hints and docstring" \
  --score-function code-scorer.py \
  --test-cases code-tasks.json
```

### Example 3: Content Summarization

```bash
llm optimize \
  --base "Summarize: {text}" \
  --vary detail-level,format \
  --levels brief,moderate,comprehensive \
  --test-input articles/*.txt \
  --evaluate-by length \
  --target 150 \
  --iterations 3
```

### Example 4: Translation Quality

```bash
llm optimize \
  --base "Translate to {language}: {text}" \
  --test-cases translations.json \
  --evaluate-by similarity \
  --manual-review top-5 \
  --save-best translate-optimized
```

## Understanding Results

### Results Report

```
Optimization Results: email-template
══════════════════════════════════════════════════════════════

Base Prompt:
  Write an email to {recipient} about {topic}

Tests Run: 24 (8 variations × 3 tests each)
Duration: 45 seconds

TOP 3 VARIATIONS:

1. WINNER (Score: 0.87)
   Write a professional email to {recipient} regarding {topic},
   including clear next steps

   Average scores:
     Professional tone: 0.95
     Clarity: 0.88
     Actionability: 0.78

2. Runner-up (Score: 0.82)
   Draft a clear email to {recipient} about {topic}

3. Third (Score: 0.78)
   Compose a formal email to {recipient} concerning {topic}

INSIGHTS:
  ✓ "Professional" consistently outperformed "formal" or "friendly"
  ✓ Including "clear next steps" improved actionability by 35%
  ✓ "Regarding" slightly better than "about"

RECOMMENDATION:
  Use variation #1 as your default email template.
  Saved to library as: email-template
```

## Configuration

`~/.llm/optimize-config.yaml`:

```yaml
optimization:
  default_iterations: 3
  default_test_count: 3
  parallel_execution: true
  max_variations_per_round: 10

evaluation:
  default_method: auto
  confidence_threshold: 0.8
  min_score_difference: 0.05  # Minimum meaningful difference

variation_generation:
  creative_variations: true
  systematic_variations: true
  max_variations: 50

output:
  save_all_results: true
  verbose: false
  show_examples: true
```

## Best Practices

1. **Start simple** - Optimize one aspect at a time
2. **Use good test cases** - Representative of real usage
3. **Define clear criteria** - Be specific about success
4. **Test multiple times** - Account for randomness
5. **Iterate** - Run multiple optimization rounds
6. **Save winners** - Add best prompts to library
7. **Document findings** - Note what worked and why

## Troubleshooting

### All Variations Score Similarly

**Problem:** All variations get nearly same scores.

**Causes:**
1. Variations too similar
2. Evaluation criteria too broad
3. Test cases too easy

**Solutions:**
```bash
# More diverse variations
llm optimize --vary tone,structure,detail-level

# Stricter evaluation
llm optimize --score-function strict-scorer.py

# Harder test cases
llm optimize --test-cases challenging-tests.json
```

### Optimization Takes Too Long

**Problem:** Testing many variations is slow.

**Solutions:**
```bash
# Reduce test count
llm optimize --test-count 2

# Use faster model
llm optimize --model gpt-4o-mini

# Enable parallel execution
llm optimize --parallel

# Limit variations
llm optimize --max-variations 10
```

## Python API

```python
from llm import optimize_prompt

result = optimize_prompt(
    base="Summarize: {text}",
    variations=[
        "Summarize: {text}",
        "Provide a summary: {text}",
        "Create a brief summary: {text}"
    ],
    test_cases=[
        {"input": {"text": "Long article..."}, "expected": "Short summary"},
    ],
    scorer=lambda response, expected: similarity(response, expected)
)

print(f"Best prompt: {result.best_prompt}")
print(f"Score: {result.best_score}")
```

## Conclusion

Prompt optimization enables:
- **Data-driven decisions** - Know objectively what works
- **Time savings** - Automated testing vs. manual trial-and-error
- **Better results** - Systematically find best prompts
- **Learning** - Understand what makes prompts effective
- **Consistency** - Reliable, repeatable results

Start optimizing your prompts to unlock better AI outputs!
