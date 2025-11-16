# Feature 5: Conversation Branching

> **⚠️ PROPOSED FEATURE - NOT YET IMPLEMENTED**
>
> This document describes a **proposed feature** for the LLM CLI that does not currently exist.
> The `llm branch` command and all related commands documented here are **not yet available**.
>
> **Attempting to run these commands will result in "Error: No such command"**
>
> This is a detailed specification for future implementation.

---


## Motivation

During interactive chats, you often want to explore different paths:
- **Try different approaches** - Ask the same question in different ways
- **Experiment without losing work** - Test ideas without polluting your main conversation
- **Compare responses** - See how different follow-ups affect the conversation
- **Undo mistakes** - Go back and take a different path
- **A/B testing** - Test different prompt strategies

Currently, once you send a message, you can't explore alternative paths without starting over. Conversation branching lets you create multiple timelines from any point in your chat, like a "choose your own adventure" book.

## Overview

The `llm branch` command allows you to fork conversations at any point, creating alternative timelines you can explore independently.

**What you can do:**
- Branch from any point in a conversation
- Switch between branches
- Merge insights from different branches
- Visualize your conversation tree
- Name and annotate branches
- Compare outcomes across branches

## Installation Dependencies

### Basic Installation

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Optional Dependencies

For tree visualization:
```bash
pip install asciitree
```

For interactive branch selection:
```bash
pip install prompt_toolkit
```

### Verification

```bash
llm --version
llm branch --help
```

## Implementation Details

### Architecture

**Components:**

1. **Branch Manager** (`llm/branch_manager.py`)
   - Creates and tracks branches
   - Manages branch switching
   - Maintains conversation tree structure

2. **Tree Navigator** (`llm/tree_navigator.py`)
   - Navigate conversation history
   - Find common ancestors
   - Calculate branch divergence

3. **Merge System** (`llm/branch_merge.py`)
   - Combine insights from branches
   - Resolve conflicts
   - Create summary of different paths

### Database Schema

**Table: `conversation_branches`**
```sql
CREATE TABLE conversation_branches (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    branch_name TEXT,
    parent_branch_id TEXT,
    branch_point_log_id TEXT,  -- Where branch diverged
    created_at TEXT,
    description TEXT,
    active BOOLEAN,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    FOREIGN KEY (parent_branch_id) REFERENCES conversation_branches(id)
);
```

**Table: `branch_messages`**
```sql
CREATE TABLE branch_messages (
    id TEXT PRIMARY KEY,
    branch_id TEXT,
    log_id TEXT,
    sequence INTEGER,
    FOREIGN KEY (branch_id) REFERENCES conversation_branches(id),
    FOREIGN KEY (log_id) REFERENCES log(id)
);
```

## Usage Instructions

### For Complete Beginners

Imagine you're writing a story and reach a crossroads. Instead of choosing one path and abandoning the others, you can explore each path separately. Conversation branching lets you do this with AI conversations - try different approaches without losing your original conversation.

### Basic Usage

#### Start a Conversation

```bash
llm chat -m gpt-4o
```

```
> Tell me about quantum computing
[AI explains quantum computing basics]

> How does it compare to classical computing?
[AI compares quantum vs classical]

> Can you explain superposition?
[AI explains superposition]
```

#### Create a Branch

At any point, create a branch to explore an alternative:

```bash
# While in chat, type:
!branch explain-differently

# Or use command:
llm branch create explain-differently --description "Try simpler explanation"
```

Now you're on the new branch. The original conversation is preserved.

#### Continue on the Branch

```
> Actually, explain superposition to a 10-year-old
[AI gives simpler explanation]

> Give me an analogy
[AI provides analogy]
```

#### Switch Between Branches

```bash
# In chat:
!branch switch main

# Or:
llm branch switch main
```

You're back to the original conversation state.

#### List All Branches

```bash
llm branch list
```

Output:
```
Branches for conversation conv_abc123:

* main (3 messages)
  └─ explain-differently (2 messages)
     "Try simpler explanation"

Current branch: main
```

### Advanced Branching

#### Branch from Specific Message

```bash
# Show conversation history
llm logs -c conv_abc123

# Branch from message 2
llm branch create technical-deep-dive --from-message 2
```

This creates a branch starting from message 2, discarding messages 3+ on this branch.

#### Name and Describe Branches

```bash
llm branch create alternative-approach \
  --description "Exploring mathematical formulation instead of conceptual" \
  --from-message 3
```

#### Visualize Conversation Tree

```bash
llm branch tree
```

Output:
```
Conversation Tree
═════════════════════════════════════════════════════════════

conv_abc123: "Quantum Computing Discussion"

main (5 messages)
├─ explain-differently (3 messages)
│  └─ even-simpler (2 messages)
│
└─ technical-deep-dive (4 messages)
   └─ mathematical (2 messages)

Total branches: 5
Total messages: 16
```

#### Compare Branches

```bash
llm branch compare main explain-differently
```

Output:
```
Branch Comparison
═════════════════════════════════════════════════════════════

Common ancestor: Message 2 "How does it compare..."

Main branch (from msg 3):
  - Can you explain superposition?
  - Tell me about entanglement
  - How is this used practically?

Explain-differently branch (from msg 3):
  - Actually, explain superposition to a 10-year-old
  - Give me an analogy
  - Now explain entanglement simply

Differences:
  - Main: More technical, theory-focused
  - Explain-differently: Simpler, analogy-based
```

### Merging Branches

#### Create Merge Summary

```bash
llm branch merge main explain-differently --summarize
```

Creates a summary combining insights from both branches.

#### Manual Merge

```bash
llm branch merge main explain-differently \
  --prompt "Combine the technical depth from main with the clear explanations from explain-differently"
```

### Branch Management

#### Rename Branch

```bash
llm branch rename explain-differently simple-explanations
```

#### Delete Branch

```bash
llm branch delete old-branch
```

#### Archive Branch

Keep branch for reference but hide from active list:

```bash
llm branch archive failed-approach
```

## Command Reference

### `llm branch create`

Create a new branch.

```bash
llm branch create NAME [OPTIONS]
```

**Arguments:**
- `NAME` - Branch name

**Options:**
- `--description TEXT` - Branch description
- `--from-message N` - Branch from message number
- `--conversation ID` - Conversation to branch (default: current)

### `llm branch list`

List all branches.

```bash
llm branch list [OPTIONS]
```

**Options:**
- `--conversation ID` - Specific conversation
- `--include-archived` - Show archived branches
- `--format FORMAT` - Output format: tree, list, json

### `llm branch switch`

Switch to a different branch.

```bash
llm branch switch NAME
```

### `llm branch tree`

Visualize conversation tree.

```bash
llm branch tree [OPTIONS]
```

**Options:**
- `--conversation ID` - Specific conversation
- `--format FORMAT` - ascii, json

### `llm branch compare`

Compare two branches.

```bash
llm branch compare BRANCH1 BRANCH2
```

### `llm branch merge`

Merge branches.

```bash
llm branch merge BRANCH1 BRANCH2 [OPTIONS]
```

**Options:**
- `--summarize` - Create AI summary of both branches
- `--prompt TEXT` - Custom merge instructions

### `llm branch rename`

Rename a branch.

```bash
llm branch rename OLD_NAME NEW_NAME
```

### `llm branch delete`

Delete a branch.

```bash
llm branch delete NAME [--force]
```

### `llm branch current`

Show current branch.

```bash
llm branch current
```

## Real-World Examples

### Example 1: Debugging Code

```bash
llm chat
> I have a bug in my Python code: [paste code]
[AI suggests solution A]

!branch try-different-approach
> Instead of that approach, what if we refactor the function?
[AI suggests solution B]

!branch switch main
> Can you explain why solution A works?
[AI explains]

!branch compare main try-different-approach
# See both solutions side-by-side, choose best one
```

### Example 2: Writing Assistance

```bash
llm chat
> Help me write an email to my boss about a delay
[AI writes formal email]

!branch casual-version
> Actually, make it more casual, we have a friendly relationship
[AI writes casual email]

!branch create brief-version --from-message 1
> Keep it very brief, just 2 sentences
[AI writes brief email]

!branch list
# Review all three versions, pick the best
```

### Example 3: Learning & Exploration

```bash
llm chat
> Explain machine learning
[AI explains]

> Tell me about neural networks
[AI explains neural networks]

!branch deep-learning-focus
> Focus more on deep learning specifically
[Explores deep learning branch]

!branch switch main
!branch supervised-learning
> Tell me about supervised learning instead
[Explores supervised learning branch]

!branch merge deep-learning-focus supervised-learning --summarize
# Get comprehensive overview of both topics
```

## Best Practices

1. **Name branches descriptively** - `alt-solution-1` not `test`
2. **Add descriptions** - Explain why you branched
3. **Don't branch too often** - Only when exploring significantly different paths
4. **Clean up old branches** - Delete or archive unused branches
5. **Use compare** - Review different approaches before deciding
6. **Merge insights** - Combine best ideas from multiple branches

## Troubleshooting

### Lost Track of Branches

**Problem:** Too many branches, confused about which is which.

**Solution:**
```bash
# Visualize tree
llm branch tree

# List with descriptions
llm branch list --detailed

# See where you are
llm branch current
```

### Can't Switch Branches

**Problem:** `Error: Cannot switch branches`

**Cause:** Unsaved changes in current branch.

**Solution:**
```bash
# Current message is saved automatically
# Try switch again
llm branch switch target-branch
```

## Configuration

`~/.llm/branch-config.yaml`:

```yaml
branching:
  auto_name: true  # Generate names like "branch-1", "branch-2"
  confirm_delete: true
  max_branches_per_conversation: 10

display:
  tree_style: ascii  # ascii, unicode
  show_message_count: true
  show_timestamps: false

cleanup:
  auto_archive_old: false
  days_until_archive: 30
```

## Conclusion

Conversation branching enables:
- **Exploration without fear** - Try ideas without losing your main thread
- **Better decisions** - Compare multiple approaches
- **Efficient experimentation** - Test different prompting strategies
- **Learning** - See how different questions lead to different insights

Start branching your conversations to unlock the full potential of interactive AI!
