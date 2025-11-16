# Feature 4: Prompt Library

## Motivation

Writing effective prompts is an art and a science. Common challenges include:
- **Starting from scratch** - Spending time crafting prompts for common tasks
- **Inconsistency** - Different team members writing different prompts for the same task
- **Lost knowledge** - Great prompts get lost in chat histories
- **No sharing** - Can't easily share proven prompts with colleagues
- **Reinventing the wheel** - Everyone writes their own "summarize this" prompt

A prompt library solves these problems by:
- Saving your best prompts for reuse
- Organizing prompts by category and tags
- Sharing prompts with your team
- Discovering community-created prompts
- Building a knowledge base of effective prompting techniques

## Overview

The `llm prompts` command provides a comprehensive system for managing, organizing, and sharing reusable prompts.

**What you can do:**
- Save prompts to a personal library
- Organize prompts with tags and categories
- Search your prompt library
- Share prompts with team members
- Import community prompt collections
- Export prompts for backup or sharing
- Version control your prompts
- Track prompt performance and effectiveness

## Installation Dependencies

### Basic Installation

The prompt library is built into LLM:

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Optional Dependencies

For community prompt discovery:
```bash
pip install requests  # Already included with LLM
```

For Git-based prompt sharing:
```bash
# Install git (usually pre-installed on Mac/Linux)
# Windows: download from https://git-scm.com/
```

### Verification

```bash
# Verify LLM is installed
llm --version

# Initialize prompt library
llm prompts init

# Check status
llm prompts list
```

## Implementation Details

### Architecture

The prompt library consists of:

1. **Prompt Storage** (`llm/prompt_library.py`)
   - SQLite database for personal library
   - File-based storage option (YAML/JSON)
   - Git integration for version control

2. **Search Engine** (`llm/prompt_search.py`)
   - Full-text search across prompts
   - Tag-based filtering
   - Category organization
   - Fuzzy matching for typos

3. **Sharing System** (`llm/prompt_sharing.py`)
   - Export to shareable formats
   - Import from URLs or files
   - Team library synchronization
   - Community marketplace integration

4. **Analytics** (`llm/prompt_analytics.py`)
   - Track prompt usage
   - Measure effectiveness
   - Popular prompts ranking

### Data Flow

```
Create Prompt → Save to Library → Tag & Categorize
                        ↓
                  Search & Discover
                        ↓
                Use in Execution → Track Performance
```

### Database Schema

**Table: `prompt_library`**
```sql
CREATE TABLE prompt_library (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    prompt TEXT,
    system_prompt TEXT,
    description TEXT,
    category TEXT,
    tags TEXT,  -- JSON array
    author TEXT,
    created_at TEXT,
    updated_at TEXT,
    version INTEGER,
    model TEXT,  -- Preferred model
    parameters JSON,  -- temperature, max_tokens, etc.
    metadata JSON,  -- Custom fields
    usage_count INTEGER DEFAULT 0,
    success_rate REAL,  -- 0.0 to 1.0
    avg_cost REAL,
    source TEXT,  -- 'personal', 'team', 'community'
    parent_id TEXT  -- For versions
);
```

**Table: `prompt_usage`**
```sql
CREATE TABLE prompt_usage (
    id TEXT PRIMARY KEY,
    prompt_id TEXT,
    used_at TEXT,
    log_id TEXT,  -- References log table
    success BOOLEAN,
    cost REAL,
    rating INTEGER,  -- 1-5 stars
    FOREIGN KEY (prompt_id) REFERENCES prompt_library(id)
);
```

**Table: `prompt_collections`**
```sql
CREATE TABLE prompt_collections (
    id TEXT PRIMARY KEY,
    name TEXT,
    description TEXT,
    prompts TEXT,  -- JSON array of prompt IDs
    author TEXT,
    created_at TEXT,
    public BOOLEAN,
    url TEXT  -- For shared collections
);
```

## Usage Instructions

### For Complete Beginners

Think of the prompt library like a recipe book. Instead of figuring out how to make the same dish every time, you write down the recipe once and can follow it whenever you need it. A prompt library stores your best "recipes" for talking to AI, so you can reuse them without starting from scratch.

### Basic Usage

#### Save Your First Prompt

After running a good prompt, save it:

```bash
# Run a prompt
llm "Summarize this text in 3 bullet points: $(cat article.txt)"

# Save it to library
llm prompts save summarize-3 \
  --prompt "Summarize this text in 3 bullet points: {text}" \
  --description "Creates a concise 3-point summary" \
  --tags "summary,text,bullets"
```

#### List Your Prompts

See all saved prompts:

```bash
llm prompts list
```

Output:
```
Personal Prompt Library (15 prompts)

Name                Category        Tags
─────────────────────────────────────────────────────────
summarize-3         text           summary, text, bullets
translate-spanish   translation    translate, spanish
code-review         development    code, review, python
email-formal        writing        email, formal, business
explain-eli5        education      explain, simple, teaching
...
```

#### Use a Saved Prompt

```bash
# Use with variable substitution
llm prompts use summarize-3 --var text="$(cat long_article.txt)"

# Shorter syntax
llm -p summarize-3 --var text="$(cat long_article.txt)"
```

### Managing Prompts

#### Add Detailed Prompts

```bash
llm prompts add code-review \
  --prompt "Review this code for:\n1. Bugs\n2. Performance issues\n3. Security vulnerabilities\n4. Best practices\n\nCode:\n{code}" \
  --system "You are an expert code reviewer with 10 years of experience" \
  --description "Comprehensive code review" \
  --category "development" \
  --tags "code,review,quality" \
  --model "gpt-4o"
```

#### Edit a Prompt

```bash
llm prompts edit summarize-3 \
  --prompt "Summarize this text in exactly 3 concise bullet points: {text}"
```

#### Delete a Prompt

```bash
llm prompts delete old-prompt
```

#### View Prompt Details

```bash
llm prompts show summarize-3
```

Output:
```
Prompt: summarize-3
═══════════════════════════════════════════════

Description: Creates a concise 3-point summary
Category: text
Tags: summary, text, bullets
Author: you
Created: 2024-11-15 10:30:00
Used: 47 times
Success Rate: 96%
Avg Cost: $0.002

Prompt Template:
────────────────────────────────────────────────
Summarize this text in 3 bullet points: {text}

System Prompt:
────────────────────────────────────────────────
(none)

Variables:
  - text (required)

Example Usage:
────────────────────────────────────────────────
llm -p summarize-3 --var text="your text here"
```

### Organizing Prompts

#### Using Categories

Categories help organize prompts by purpose:

```bash
# Add prompts to categories
llm prompts add meeting-notes \
  --prompt "Extract action items from this meeting: {transcript}" \
  --category "productivity"

llm prompts add bug-report \
  --prompt "Create a detailed bug report for: {issue}" \
  --category "development"

# List by category
llm prompts list --category productivity
llm prompts list --category development
```

Common categories:
- `writing` - Content creation, emails, documents
- `development` - Code, debugging, reviews
- `analysis` - Data analysis, research
- `translation` - Language translation
- `education` - Teaching, explaining concepts
- `productivity` - Summaries, notes, tasks
- `creative` - Stories, poems, ideas

#### Using Tags

Tags provide flexible organization:

```bash
# Add with multiple tags
llm prompts add social-media-post \
  --prompt "Write an engaging social media post about: {topic}" \
  --tags "writing,marketing,social-media,short-form"

# Search by tag
llm prompts list --tag writing
llm prompts list --tag marketing

# Multiple tags (AND logic)
llm prompts list --tags "writing,marketing"
```

### Searching the Library

#### Text Search

Find prompts by name or description:

```bash
# Search by keyword
llm prompts search "email"

# Output:
# - email-formal
# - email-casual
# - email-apology
# - email-followup
```

#### Advanced Filters

```bash
# By author
llm prompts list --author alice

# By date
llm prompts list --after 2024-11-01

# By popularity
llm prompts list --sort usage

# Combine filters
llm prompts list --category writing --tag email --sort usage
```

### Sharing Prompts

#### Export a Prompt

```bash
# Export as YAML
llm prompts export summarize-3 > summarize.yaml

# Export as JSON
llm prompts export summarize-3 --format json > summarize.json
```

#### Import a Prompt

```bash
# From file
llm prompts import summarize.yaml

# From URL
llm prompts import https://example.com/prompts/translator.yaml

# Import collection
llm prompts import https://github.com/user/prompts/collection.yaml
```

#### Share a Collection

Create a collection of related prompts:

```bash
# Create collection
llm prompts collection create writing-toolkit \
  --prompts "email-formal,email-casual,blog-post,tweet" \
  --description "Essential writing prompts"

# Export collection
llm prompts collection export writing-toolkit > toolkit.yaml

# Share the file with team members
# They import with:
llm prompts collection import toolkit.yaml
```

### Community Prompts

#### Browse Community Library

```bash
# List available community collections
llm prompts community list

# Output:
# - marketing-essentials (by @user1, 15 prompts)
# - developer-toolkit (by @user2, 23 prompts)
# - academic-writing (by @user3, 18 prompts)
```

#### Install Community Collection

```bash
# Install a collection
llm prompts community install marketing-essentials

# List installed community prompts
llm prompts list --source community
```

#### Publish Your Collection

```bash
# Publish to community
llm prompts collection publish writing-toolkit \
  --public \
  --description "Essential writing prompts for professionals"
```

### Prompt Versioning

#### Create New Version

```bash
# Edit creates a new version
llm prompts edit summarize-3 \
  --prompt "Provide a 3-bullet summary with key insights: {text}" \
  --create-version

# View versions
llm prompts versions summarize-3
```

Output:
```
Versions of 'summarize-3':

v1 (2024-11-01):
  Summarize this text in 3 bullet points: {text}

v2 (2024-11-10):
  Summarize this text in exactly 3 concise bullet points: {text}

v3 (2024-11-15) [current]:
  Provide a 3-bullet summary with key insights: {text}
```

#### Use Specific Version

```bash
# Use version 2
llm -p summarize-3@v2 --var text="..."

# Rollback to previous version
llm prompts rollback summarize-3 --to v2
```

### Analytics and Insights

#### Prompt Performance

See which prompts perform best:

```bash
llm prompts stats summarize-3
```

Output:
```
Prompt Statistics: summarize-3
══════════════════════════════════════

Usage:
  Total uses: 47
  Last used: 2 hours ago
  Frequency: 3.2 times/day

Performance:
  Success rate: 96% (45/47)
  Avg response time: 1.2s
  Avg cost: $0.002

Cost Analysis:
  Total cost: $0.094
  Estimated monthly: $2.88

User Ratings:
  Average: 4.6/5 stars
  5 stars: 38
  4 stars: 7
  3 stars: 2
  1-2 stars: 0
```

#### Library Overview

```bash
llm prompts analytics
```

Output:
```
Prompt Library Analytics
══════════════════════════════════════

Library Size: 15 prompts
Total Uses: 342
Most Used: summarize-3 (47 uses)
Highest Rated: code-review (4.9/5)
Most Cost-Effective: email-casual ($0.001 avg)

Usage by Category:
  writing: 45%
  development: 30%
  productivity: 15%
  analysis: 10%

Trending (last 7 days):
  ↑ translate-spanish (+40%)
  ↑ meeting-notes (+25%)
  → summarize-3 (stable)
  ↓ old-template (-50%)
```

## Command Reference

### `llm prompts add`

Add a new prompt to library.

```bash
llm prompts add NAME [OPTIONS]
```

**Arguments:**
- `NAME` - Unique name for the prompt

**Options:**
- `--prompt TEXT` - Prompt template (use {variables})
- `--system TEXT` - System prompt
- `--description TEXT` - Brief description
- `--category TEXT` - Category name
- `--tags TEXT` - Comma-separated tags
- `--model TEXT` - Preferred model
- `--author TEXT` - Author name (default: your username)
- `--file PATH` - Load prompt from file

**Examples:**

```bash
# Simple prompt
llm prompts add explain-code \
  --prompt "Explain this code: {code}" \
  --tags "code,explain"

# With system prompt
llm prompts add formal-email \
  --prompt "Draft: {subject}" \
  --system "You are a professional business writer" \
  --category writing

# From file
llm prompts add research-summary \
  --file research-template.txt \
  --description "Academic research summarizer"
```

### `llm prompts save`

Save the last prompt you ran.

```bash
llm prompts save NAME [OPTIONS]
```

Saves your last executed prompt to the library.

### `llm prompts use` / `llm -p`

Use a saved prompt.

```bash
llm prompts use NAME [OPTIONS]
llm -p NAME [OPTIONS]  # Short form
```

**Options:**
- `--var KEY=VALUE` - Set template variable
- `--vars FILE` - Load variables from JSON/YAML
- `--model TEXT` - Override default model

**Examples:**

```bash
# Single variable
llm -p summarize-3 --var text="Long article..."

# Multiple variables
llm -p email-template \
  --var recipient="John" \
  --var subject="Meeting followup"

# From file
llm -p code-review --vars data.json
```

### `llm prompts list`

List saved prompts.

```bash
llm prompts list [OPTIONS]
```

**Options:**
- `--category TEXT` - Filter by category
- `--tag TEXT` - Filter by tag
- `--tags TEXT` - Multiple tags (comma-separated)
- `--author TEXT` - Filter by author
- `--source TEXT` - Filter by source: personal, team, community
- `--sort FIELD` - Sort by: name, created, updated, usage, rating
- `--limit N` - Show only N results
- `--format FORMAT` - Output format: table, json, yaml

### `llm prompts show`

Show prompt details.

```bash
llm prompts show NAME
```

### `llm prompts edit`

Edit an existing prompt.

```bash
llm prompts edit NAME [OPTIONS]
```

**Options:**
- `--prompt TEXT` - New prompt template
- `--system TEXT` - New system prompt
- `--description TEXT` - New description
- `--tags TEXT` - New tags
- `--create-version` - Create new version instead of overwriting

### `llm prompts delete`

Delete a prompt.

```bash
llm prompts delete NAME [--force]
```

### `llm prompts search`

Search prompts by text.

```bash
llm prompts search QUERY
```

### `llm prompts export`

Export a prompt.

```bash
llm prompts export NAME [OPTIONS]
```

**Options:**
- `--format FORMAT` - Format: yaml, json
- `--output FILE` - Save to file

### `llm prompts import`

Import a prompt.

```bash
llm prompts import SOURCE [OPTIONS]
```

**Arguments:**
- `SOURCE` - File path or URL

**Options:**
- `--overwrite` - Overwrite if exists
- `--rename TEXT` - Import with different name

### `llm prompts collection`

Manage prompt collections.

```bash
llm prompts collection COMMAND [OPTIONS]

Commands:
  create NAME            Create new collection
  add NAME PROMPT        Add prompt to collection
  remove NAME PROMPT     Remove prompt from collection
  list                   List collections
  show NAME              Show collection details
  export NAME            Export collection
  import FILE            Import collection
  publish NAME           Publish to community
```

### `llm prompts community`

Interact with community library.

```bash
llm prompts community COMMAND [OPTIONS]

Commands:
  list                   List available collections
  search QUERY           Search community prompts
  install NAME           Install collection
  uninstall NAME         Remove collection
  update                 Update installed collections
```

### `llm prompts stats`

View prompt statistics.

```bash
llm prompts stats NAME
```

### `llm prompts analytics`

View library analytics.

```bash
llm prompts analytics [OPTIONS]
```

**Options:**
- `--period DAYS` - Analysis period (default: 30)
- `--export FILE` - Export report

## Configuration

### Library Configuration

Create `~/.llm/prompts-config.yaml`:

```yaml
# Library settings
library:
  auto_save_successful: true  # Auto-save prompts with high ratings
  track_usage: true
  sync_enabled: false

# Organization
defaults:
  category: general
  author: ${USER}
  tags: []

# Display
display:
  list_format: table
  show_descriptions: true
  max_prompt_preview: 100  # chars

# Community
community:
  auto_update: false
  trusted_authors: []
  filter_nsfw: true

# Sharing
sharing:
  default_public: false
  include_analytics: false
  git_integration: false
  git_repo: null

# Search
search:
  fuzzy_matching: true
  search_content: true  # Search in prompt text
  max_results: 50
```

## Real-World Examples

### Example 1: Team Prompt Library

**Scenario:** Share prompts across your team.

```bash
# 1. Create team collection
llm prompts collection create customer-support \
  --description "Customer support response templates"

# 2. Add prompts
llm prompts add refund-response \
  --prompt "Draft a professional refund approval email for: {situation}" \
  --category customer-support

llm prompts add complaint-response \
  --prompt "Write an empathetic response to this complaint: {complaint}" \
  --category customer-support

# 3. Add to collection
llm prompts collection add customer-support refund-response
llm prompts collection add customer-support complaint-response

# 4. Export for team
llm prompts collection export customer-support > support-prompts.yaml

# 5. Team members import
llm prompts collection import support-prompts.yaml
```

### Example 2: Developer Toolkit

**Scenario:** Build a library of coding prompts.

```bash
# Code review
llm prompts add code-review \
  --prompt "Review this {language} code:\n{code}" \
  --system "Expert code reviewer" \
  --tags "code,review,quality"

# Documentation
llm prompts add write-docs \
  --prompt "Write documentation for:\n{code}" \
  --tags "code,docs,documentation"

# Unit tests
llm prompts add generate-tests \
  --prompt "Generate unit tests for:\n{code}" \
  --tags "code,testing,unittest"

# Bug fixing
llm prompts add fix-bug \
  --prompt "Fix this bug:\n{code}\nError: {error}" \
  --tags "code,debug,fix"

# Use them
llm -p code-review --var language=python --var code="$(cat script.py)"
```

### Example 3: Content Creation Workflow

**Scenario:** Streamline blog writing.

```bash
# Ideation
llm prompts add blog-ideas \
  --prompt "Generate 10 blog post ideas about: {topic}" \
  --category writing

# Outline
llm prompts add blog-outline \
  --prompt "Create an outline for: {title}" \
  --category writing

# Draft
llm prompts add blog-draft \
  --prompt "Write a 500-word blog post:\nTitle: {title}\nOutline: {outline}" \
  --category writing

# SEO
llm prompts add seo-optimize \
  --prompt "Optimize this for SEO:\n{content}\nKeyword: {keyword}" \
  --category writing

# Workflow
llm -p blog-ideas --var topic="AI" > ideas.txt
llm -p blog-outline --var title="Understanding GPT" > outline.txt
llm -p blog-draft --var title="Understanding GPT" --var outline="$(cat outline.txt)" > draft.txt
llm -p seo-optimize --var content="$(cat draft.txt)" --var keyword="GPT tutorial"
```

## Troubleshooting

### Prompt Not Found

**Problem:** `Error: Prompt 'my-prompt' not found`

**Solutions:**
```bash
# List all prompts
llm prompts list

# Search for similar names
llm prompts search "my"

# Check if it's in a collection
llm prompts collection list
```

### Variable Not Substituted

**Problem:** Prompt contains `{variable}` in output.

**Cause:** Forgot to provide variable value.

**Solution:**
```bash
# Correct usage
llm -p my-prompt --var variable="value"

# Check required variables
llm prompts show my-prompt
```

### Import Fails

**Problem:** Can't import prompt from file.

**Solutions:**
```bash
# Check file format (must be YAML or JSON)
cat prompt.yaml

# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('prompt.yaml'))"

# Try explicit format
llm prompts import prompt.yaml --format yaml
```

## Best Practices

1. **Use descriptive names** - `summarize-3-bullets` not `sum3`
2. **Add descriptions** - Help future you remember what it does
3. **Tag generously** - Makes searching easier
4. **Version important prompts** - Track improvements
5. **Share with team** - Build collective knowledge
6. **Review analytics** - Remove unused prompts
7. **Test before saving** - Ensure prompts work well
8. **Document variables** - Explain what each variable does

## Prompt Template Best Practices

### Good Template Structure

```
# Clear task description
{verb} this {subject} {adverb}

# Provide context
Context: {context}

# Specify format
Format: {format}

# Include examples if needed
Example: {example}
```

### Variable Naming

- Use descriptive names: `{customer_name}` not `{x}`
- Be consistent: `{input_text}` not sometimes `{text}` sometimes `{content}`
- Use snake_case: `{file_name}` not `{fileName}`

## Conclusion

A prompt library transforms LLM from a tool you use differently each time to a consistent, efficient system. Benefits:
- **Save time** - Reuse proven prompts
- **Ensure quality** - Use battle-tested templates
- **Enable sharing** - Build team knowledge base
- **Track performance** - Know what works
- **Continuous improvement** - Iterate on prompts

Start building your prompt library today and never write the same prompt twice!
