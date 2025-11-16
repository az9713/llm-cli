# Feature 9: Smart Context Management

> **✅ IMPLEMENTED FEATURE**
>
> This feature is fully implemented and available in the LLM CLI.
> All commands documented here are ready to use.

---


## Motivation

AI models have token limits that restrict how much text they can process:
- **GPT-4o**: 128,000 tokens (~96,000 words)
- **Claude Opus**: 200,000 tokens (~150,000 words)
- **GPT-4o-mini**: 128,000 tokens (~96,000 words)

Common challenges:
- **Context overflow** - Trying to send too much text
- **Wasted tokens** - Including irrelevant information
- **Lost context** - Important details get truncated
- **High costs** - Paying for unnecessary tokens
- **Manual management** - Having to decide what to include

Smart context management solves these problems by:
- Automatically managing context windows
- Prioritizing important information
- Summarizing old messages
- Truncating intelligently
- Optimizing token usage

## Overview

The `llm context` command provides intelligent context window management, ensuring you maximize information while staying within limits.

**What you can do:**
- Auto-truncate long inputs intelligently
- Summarize conversation history
- Prioritize recent or important messages
- Compress repetitive content
- Track context usage
- Set context budgets
- Use rolling summarization

## Installation Dependencies

### Basic Installation

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Optional Dependencies

For advanced summarization:
```bash
pip install tiktoken  # Accurate token counting
```

For semantic chunking:
```bash
pip install sentence-transformers
```

### Verification

```bash
llm --version
llm context --help
```

## Implementation Details

### Architecture

**Components:**

1. **Token Counter** (`llm/context/token_counter.py`)
   - Accurate token counting
   - Model-specific tokenizers
   - Estimation for unknown models

2. **Context Optimizer** (`llm/context/optimizer.py`)
   - Intelligent truncation
   - Priority-based selection
   - Semantic chunking

3. **Summarizer** (`llm/context/summarizer.py`)
   - Rolling summarization
   - Conversation compression
   - Key point extraction

4. **Context Manager** (`llm/context/manager.py`)
   - Manages conversation context
   - Applies strategies
   - Tracks usage

### Context Management Pipeline

```
Input → Token Count → Check Limit → Apply Strategy → Optimized Context → Model
```

Strategies:
- **Truncate** - Remove oldest messages
- **Summarize** - Compress old messages
- **Chunk** - Split into manageable pieces
- **Prioritize** - Keep important messages

### Database Schema

**Table: `context_configs`**
```sql
CREATE TABLE context_configs (
    id TEXT PRIMARY KEY,
    name TEXT,
    strategy TEXT,  -- 'truncate', 'summarize', 'chunk', 'hybrid'
    max_tokens INTEGER,
    priority_rules JSON,
    created_at TEXT
);
```

**Table: `context_usage`**
```sql
CREATE TABLE context_usage (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    timestamp TEXT,
    tokens_before INTEGER,
    tokens_after INTEGER,
    strategy_used TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
```

## Usage Instructions

### For Complete Beginners

Think of context management like packing a suitcase. You have limited space (token limit), lots of items (messages/text), and need to decide what to pack. Context management automatically chooses the most important items, compresses some, and leaves out unnecessary ones to fit everything.

### Basic Usage

#### Check Context Size

See how many tokens your text uses:

```bash
# From file
llm context count < document.txt

# From string
echo "Your text here" | llm context count

# Result:
# Tokens: 1,234
# Characters: 5,678
# Model: gpt-4o (128,000 token limit)
# Usage: 0.96%
```

#### Auto-Truncate Long Input

```bash
# Will automatically truncate if too long
llm "Summarize this" < very-long-document.txt --auto-truncate

# Or explicitly
cat huge-file.txt | llm context truncate --max-tokens 8000 | llm "Summarize"
```

#### Summarize to Fit

Instead of truncating, summarize:

```bash
cat long-conversation.txt | llm context summarize --max-tokens 4000 | llm "What are the key points?"
```

### Context Strategies

#### Strategy 1: Simple Truncation

Remove oldest messages:

```bash
llm chat --context-strategy truncate --max-context-tokens 50000
```

In long conversations:
- Keeps system prompt
- Keeps recent messages
- Removes oldest messages when limit reached

#### Strategy 2: Rolling Summarization

Summarize old messages:

```bash
llm chat --context-strategy summarize --summarize-after 20
```

After 20 messages:
- Messages 1-15 → Summarized into 1-2 messages
- Messages 16-20 → Kept verbatim
- New messages → Added normally

#### Strategy 3: Priority-Based

Keep important messages:

```bash
llm chat --context-strategy priority --priority-keywords "important,critical,key"
```

Messages containing keywords are preserved longer.

#### Strategy 4: Hybrid

Combine strategies:

```bash
llm chat --context-strategy hybrid \
  --summarize-after 15 \
  --max-context-tokens 80000 \
  --priority-keywords "important"
```

Process:
1. Identify priority messages
2. Summarize old non-priority messages
3. Truncate if still over limit
4. Always keep priority messages

### Context Configuration

#### Set Default Strategy

```bash
llm context set-default \
  --strategy summarize \
  --max-tokens 100000 \
  --summarize-after 20
```

#### Per-Conversation Strategy

```bash
llm chat \
  --context-strategy summarize \
  --summarize-after 10
```

#### Named Configurations

```bash
# Create configuration
llm context config create long-research \
  --strategy hybrid \
  --max-tokens 120000 \
  --summarize-after 30 \
  --priority-keywords "finding,result,conclusion,important"

# Use it
llm chat --context-config long-research
```

### Context Analysis

#### View Context Usage

```bash
llm context usage --conversation conv_abc123
```

Output:
```
Context Usage: conv_abc123
══════════════════════════════════════════════════════════════

Current State:
  Messages: 45
  Total tokens: 87,234
  Context limit: 128,000
  Usage: 68%

Strategy: Rolling Summarization
  Summaries: 2 (covering 30 messages)
  Verbatim: 15 (most recent)

Token Distribution:
  System prompt:     500 tokens (0.6%)
  Summaries:      12,000 tokens (14%)
  Recent messages: 74,734 tokens (86%)

Recommendations:
  ✓ Context usage healthy
  - Consider summarizing at 60 messages
  - Priority keywords could help preserve key info
```

#### Context Timeline

See how context evolved:

```bash
llm context timeline --conversation conv_abc123
```

```
Message  Tokens  Cumulative  Action
───────────────────────────────────────────
1        450     450         Added
2        320     770         Added
3        280     1,050       Added
...
15       340     23,450      Added
16-25    ---     28,900      Summarized → 1,200
26       380     29,280      Added
...
40       420     87,234      Added (current)
```

### Advanced Features

#### Semantic Chunking

Split by meaning, not arbitrary lengths:

```bash
cat long-article.txt | llm context chunk --semantic --chunk-size 2000
```

Outputs multiple semantically coherent chunks.

#### Context Compression

Compress without losing information:

```bash
cat verbose-text.txt | llm context compress --ratio 0.5
```

Reduces tokens by 50% while preserving key information.

#### Priority Rules

Define what to keep:

```bash
llm context config create research \
  --priority-rules rules.yaml

# rules.yaml:
# priorities:
#   - type: keyword
#     values: [important, critical, key finding]
#     weight: 1.0
#   - type: role
#     values: [system]
#     weight: 1.0
#   - type: recency
#     messages: 10
#     weight: 0.8
#   - type: code_blocks
#     weight: 0.9
```

#### Context Budget

Allocate tokens:

```bash
llm chat --context-budget system:10%,history:60%,current:30%
```

- System prompt: 10% of tokens
- Conversation history: 60%
- Current prompt: 30%

### Integration with Chat

#### Long Conversations

Start a chat with smart context management:

```bash
llm chat --context-strategy summarize
```

```
> Tell me about quantum computing
[AI explains]

> Go deeper into superposition
[AI explains]

... [18 more messages] ...

[Context Manager]: Summarized messages 1-15 to save tokens
Tokens saved: 8,450
Current usage: 34,567 / 128,000 (27%)

> Continue with entanglement
[AI continues with full context]
```

#### Large Document Analysis

Analyze documents larger than context window:

```bash
# Automatic chunking and summarization
llm "Analyze the themes in this book" < large-book.txt --smart-context

# Process:
# 1. Splits book into chunks
# 2. Analyzes each chunk
# 3. Synthesizes results
# 4. Provides comprehensive answer
```

## Command Reference

### `llm context count`

Count tokens in text.

```bash
llm context count [OPTIONS] < input.txt
```

**Options:**
- `--model TEXT` - Count for specific model
- `--verbose` - Show detailed breakdown

### `llm context truncate`

Truncate text to fit limit.

```bash
llm context truncate [OPTIONS] < input.txt
```

**Options:**
- `--max-tokens N` - Maximum tokens
- `--strategy STRATEGY` - start, end, middle
- `--preserve-sentences` - Don't break sentences

### `llm context summarize`

Summarize to reduce tokens.

```bash
llm context summarize [OPTIONS] < input.txt
```

**Options:**
- `--max-tokens N` - Target token count
- `--ratio RATIO` - Compression ratio (0.0-1.0)
- `--model TEXT` - Model to use for summarization

### `llm context chunk`

Split into chunks.

```bash
llm context chunk [OPTIONS] < input.txt
```

**Options:**
- `--chunk-size N` - Tokens per chunk
- `--semantic` - Semantic boundaries
- `--overlap N` - Overlap between chunks

### `llm context compress`

Compress text.

```bash
llm context compress [OPTIONS] < input.txt
```

**Options:**
- `--ratio RATIO` - Compression ratio
- `--method METHOD` - extractive, abstractive

### `llm context usage`

Show context usage for conversation.

```bash
llm context usage --conversation ID
```

### `llm context timeline`

Show context evolution.

```bash
llm context timeline --conversation ID
```

### `llm context config`

Manage context configurations.

```bash
llm context config COMMAND [OPTIONS]

Commands:
  create NAME       Create configuration
  list              List configurations
  show NAME         Show configuration
  delete NAME       Delete configuration
  set-default NAME  Set as default
```

## Real-World Examples

### Example 1: Long Research Session

```bash
# Start research chat with smart context
llm chat \
  --context-strategy hybrid \
  --max-context-tokens 100000 \
  --summarize-after 25 \
  --priority-keywords "finding,conclusion,important,hypothesis"

# Chat for hours without context overflow
# Old messages automatically summarized
# Important findings always preserved
```

### Example 2: Large Document Q&A

```bash
# Load entire book
cat large-textbook.txt | llm context chunk --semantic --chunk-size 10000 > chunks/

# Query with context management
for chunk in chunks/*.txt; do
  llm "Extract key concepts" < $chunk --save-summary
done

llm "Based on all chunks, what are the main themes?" --use-summaries
```

### Example 3: Code Review

```bash
# Review large codebase
cat large-file.py | llm context compress --ratio 0.7 | llm "Review this code"

# Preserves structure, removes verbosity
# Fits in context window
```

### Example 4: Meeting Notes

```bash
# Long meeting transcript
llm "Summarize action items" < 3-hour-meeting.txt --smart-context

# Automatically:
# 1. Checks token count
# 2. Chunks if needed
# 3. Processes each chunk
# 4. Synthesizes final answer
```

## Configuration

`~/.llm/context-config.yaml`:

```yaml
# Default settings
defaults:
  strategy: hybrid
  max_tokens: 100000
  auto_manage: true

# Strategy configs
truncate:
  preserve: recent
  buffer: 1000  # Leave buffer

summarize:
  trigger_after: 20  # messages
  compression_ratio: 0.3
  summarize_model: gpt-4o-mini  # Cheaper for summaries

hybrid:
  summarize_after: 25
  max_tokens: 120000
  priority_keywords:
    - important
    - critical
    - key
    - finding
    - conclusion

# Token budgets
budgets:
  system_prompt: 0.05    # 5%
  history: 0.70          # 70%
  current_message: 0.25  # 25%

# Alerts
alerts:
  warn_at: 0.80  # 80% of limit
  error_at: 0.95  # 95% of limit
```

## Best Practices

1. **Set limits proactively** - Don't wait for overflow
2. **Use summarization** - Better than truncation
3. **Prioritize important info** - Mark key messages
4. **Monitor usage** - Check `llm context usage` regularly
5. **Choose right strategy** - Different tasks need different approaches
6. **Budget tokens** - Allocate for system, history, current
7. **Compress early** - Before hitting limits

## Troubleshooting

### Context Limit Error

**Problem:** `Error: Context length exceeded`

**Solution:**
```bash
# Enable auto-management
llm chat --auto-truncate

# Or use summarization
llm chat --context-strategy summarize

# Or check current usage
llm context usage --conversation current
```

### Lost Important Information

**Problem:** Key details were truncated.

**Solution:**
```bash
# Use priority keywords
llm chat --priority-keywords "important,key,critical"

# Or use hybrid strategy
llm chat --context-strategy hybrid

# Or increase limit
llm chat --max-context-tokens 120000
```

### Summaries Too Lossy

**Problem:** Summarization loses too much detail.

**Solution:**
```bash
# Reduce compression
llm chat --summarize-after 40  # Summarize less frequently

# Or use better model for summaries
llm context config create detailed-summary \
  --summarize-model gpt-4o

# Or use hybrid with higher verbatim count
llm chat --context-strategy hybrid --keep-verbatim 30
```

## Python API

```python
from llm import get_model, context_manager

model = get_model("gpt-4o")

# Automatic context management
with context_manager(
    strategy="summarize",
    max_tokens=100000,
    summarize_after=20
) as ctx:
    conversation = model.conversation()
    for message in long_conversation:
        response = conversation.prompt(message)
        # Context automatically managed

# Manual context ops
from llm.context import count_tokens, summarize, truncate

tokens = count_tokens("Your text", model="gpt-4o")
summarized = summarize("Long text", max_tokens=1000)
truncated = truncate("Long text", max_tokens=500)
```

## Performance Impact

### Token Savings

**Without context management:**
- 100-message conversation: 250,000 tokens
- Result: ERROR (exceeds 128k limit)

**With rolling summarization:**
- Same conversation: 87,000 tokens
- Result: SUCCESS
- Savings: 163,000 tokens (65%)

### Cost Savings

**Example scenario:** Long research chat (50 messages)

- Without management: Can't complete (exceeds limit)
- With truncation: Loses 30 messages of context
- With summarization: Keeps all information in compressed form
  - Additional summarization cost: $0.05
  - Main conversation cost: $0.45
  - Total: $0.50
  - vs. multiple separate chats: $2.00+
  - **Savings: $1.50 (75%)**

## Conclusion

Smart context management enables:
- **Unlimited conversations** - Never hit context limits
- **Cost optimization** - Pay only for useful tokens
- **Information preservation** - Keep what matters
- **Better responses** - Model has optimal context
- **Automatic handling** - No manual management needed

Start using context management for longer, more effective conversations!
