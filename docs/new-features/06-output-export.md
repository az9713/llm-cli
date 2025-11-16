# Feature 6: Enhanced Output Export

> **⚠️ PROPOSED FEATURE - NOT YET IMPLEMENTED**
>
> This document describes a **proposed feature** for the LLM CLI that does not currently exist.
> The `llm export` command and all related commands documented here are **not yet available**.
>
> **Attempting to run these commands will result in "Error: No such command"**
>
> This is a detailed specification for future implementation.

---


## Motivation

LLM stores conversations in a SQLite database, but you often need to:
- **Share conversations** - Send to colleagues or clients
- **Create reports** - Document AI-assisted work for management
- **Archive important chats** - Save critical conversations in readable formats
- **Publish content** - Turn AI conversations into blog posts or documentation
- **Backup data** - Export for safekeeping
- **Analyze externally** - Use other tools for data analysis

The current logging system stores data well but doesn't make it easy to export in user-friendly formats. Enhanced export provides beautiful, shareable outputs in multiple formats.

## Overview

The `llm export` command exports conversations, prompts, and responses in various formats including Markdown, HTML, PDF, JSON, CSV, and more.

**What you can do:**
- Export single conversations or entire history
- Generate beautiful HTML reports with styling
- Create PDF documents for sharing
- Export to Markdown for documentation
- Convert to CSV/Excel for data analysis
- Customize export templates
- Filter and select specific content
- Include or exclude metadata

## Installation Dependencies

### Basic Installation

1. **Python 3.9 or higher**
2. **LLM CLI tool**:
   ```bash
   pip install llm
   ```

### Export Format Dependencies

Different formats require different packages:

**For HTML (basic):**
```bash
pip install jinja2 markdown
```

**For HTML (advanced with styling):**
```bash
pip install jinja2 markdown pygments
```

**For PDF:**
```bash
pip install weasyprint
# Or alternatively:
pip install reportlab
```

**For Word documents:**
```bash
pip install python-docx
```

**For Excel:**
```bash
pip install openpyxl xlsxwriter
```

**For presentations:**
```bash
pip install python-pptx
```

### Install All Export Formats

```bash
pip install llm[export-all]
```

Or manually:
```bash
pip install jinja2 markdown pygments weasyprint openpyxl python-docx
```

### Verification

```bash
# Check what export formats are available
llm export formats
```

Output:
```
Available Export Formats:
  ✓ markdown (.md)
  ✓ html (.html)
  ✓ pdf (.pdf)
  ✓ json (.json)
  ✓ csv (.csv)
  ✓ docx (.docx)
  ✓ xlsx (.xlsx)
  ✗ pptx (install python-pptx)

To enable all formats: pip install llm[export-all]
```

## Implementation Details

### Architecture

**Components:**

1. **Export Engine** (`llm/export_engine.py`)
   - Coordinates export process
   - Selects appropriate formatter
   - Handles filtering and options

2. **Format Handlers** (`llm/exporters/`)
   - `markdown_exporter.py` - Markdown format
   - `html_exporter.py` - HTML with templates
   - `pdf_exporter.py` - PDF generation
   - `json_exporter.py` - JSON structured data
   - `csv_exporter.py` - CSV tabular data
   - `docx_exporter.py` - Word documents
   - `xlsx_exporter.py` - Excel spreadsheets

3. **Template System** (`llm/export_templates/`)
   - Jinja2 templates for HTML/Markdown
   - Customizable themes
   - User-defined templates

4. **Data Selector** (`llm/export_selector.py`)
   - Query and filter conversations
   - Select date ranges
   - Filter by model, tags, etc.

### Export Pipeline

```
Database Query → Data Selection → Format Handler → Template Rendering → Output File
```

## Usage Instructions

### For Complete Beginners

Think of exporting like "Save As" in a word processor. You're taking your AI conversation and saving it in different file formats - like a PDF you can email, a Word document you can edit, or an HTML page you can view in your browser.

### Basic Usage

#### Export Last Conversation

```bash
# Export to Markdown (default)
llm export

# Outputs: conversation_2024-11-16.md
```

#### Export Specific Conversation

```bash
# By conversation ID
llm export -c conv_abc123

# By name/search
llm export --conversation "Python debugging session"
```

#### Choose Output Format

```bash
# HTML
llm export -c conv_abc123 --format html -o report.html

# PDF
llm export -c conv_abc123 --format pdf -o conversation.pdf

# Word document
llm export -c conv_abc123 --format docx -o chat.docx

# JSON
llm export -c conv_abc123 --format json -o data.json
```

### Export Options

#### Single Conversation

```bash
llm export \
  --conversation conv_abc123 \
  --format html \
  --output my-chat.html \
  --theme modern \
  --include-metadata
```

Creates a beautiful HTML page with:
- Formatted messages
- Syntax highlighting for code
- Timestamps
- Model information
- Token usage stats

#### Multiple Conversations

```bash
# Last 10 conversations
llm export --last 10 --format pdf -o recent-chats.pdf

# All conversations from this month
llm export --from 2024-11-01 --format html -o november-chats.html

# All conversations with specific model
llm export --model gpt-4o --format markdown -o gpt4o-history.md
```

#### Date Range Export

```bash
llm export \
  --from 2024-11-01 \
  --to 2024-11-30 \
  --format pdf \
  -o november-report.pdf
```

#### Filter by Tags/Project

```bash
# Export specific project
llm export --project customer-support --format xlsx -o support-logs.xlsx

# Export by tag
llm export --tag important --format pdf -o important-chats.pdf
```

### Export Formats

#### Markdown Export

Perfect for documentation and version control:

```bash
llm export -c conv_abc123 --format markdown -o chat.md
```

**Output (`chat.md`):**
```markdown
# Conversation: Python Debugging Help

**Date:** 2024-11-16 14:30:00
**Model:** gpt-4o
**Messages:** 12

---

## Message 1 (User)
*2024-11-16 14:30:15*

I'm getting a KeyError in my Python script:

\```python
data = {'name': 'Alice'}
print(data['age'])
\```

---

## Message 2 (Assistant)
*2024-11-16 14:30:22*

The error occurs because the dictionary doesn't have an 'age' key...

---

...
```

#### HTML Export

Beautiful, shareable web pages:

```bash
llm export -c conv_abc123 --format html --theme modern -o chat.html
```

Features:
- Responsive design (works on mobile)
- Syntax highlighting for code
- Collapsible sections
- Print-friendly CSS
- Search functionality
- Copy buttons for code blocks

**Themes:**
- `modern` - Clean, contemporary design
- `classic` - Traditional documentation style
- `dark` - Dark mode
- `minimal` - Simple, distraction-free
- `github` - GitHub-style rendering

#### PDF Export

Professional documents for sharing:

```bash
llm export -c conv_abc123 --format pdf -o report.pdf
```

Options:
```bash
llm export -c conv_abc123 --format pdf \
  --pdf-size a4 \
  --pdf-orientation portrait \
  --include-toc \
  --include-metadata \
  -o report.pdf
```

#### JSON Export

Structured data for programmatic access:

```bash
llm export -c conv_abc123 --format json -o data.json
```

**Output (`data.json`):**
```json
{
  "conversation_id": "conv_abc123",
  "created_at": "2024-11-16T14:30:00Z",
  "model": "gpt-4o",
  "message_count": 12,
  "messages": [
    {
      "id": "msg_001",
      "role": "user",
      "content": "I'm getting a KeyError...",
      "timestamp": "2024-11-16T14:30:15Z"
    },
    {
      "id": "msg_002",
      "role": "assistant",
      "content": "The error occurs because...",
      "timestamp": "2024-11-16T14:30:22Z",
      "model": "gpt-4o",
      "tokens": {
        "input": 45,
        "output": 120
      },
      "cost": 0.0023
    }
  ],
  "metadata": {
    "total_cost": 0.0145,
    "total_tokens": 1823
  }
}
```

#### CSV Export

Tabular data for Excel analysis:

```bash
llm export --from 2024-11-01 --format csv -o november.csv
```

**Output (`november.csv`):**
```csv
timestamp,conversation_id,role,model,message,tokens_in,tokens_out,cost
2024-11-16 14:30:15,conv_abc123,user,,I'm getting a KeyError...,,,
2024-11-16 14:30:22,conv_abc123,assistant,gpt-4o,The error occurs because...,45,120,0.0023
```

#### Excel Export

Multiple sheets with analysis:

```bash
llm export --month 2024-11 --format xlsx -o november-report.xlsx
```

Creates workbook with sheets:
- **Messages** - All messages
- **Summary** - Statistics and metrics
- **By Model** - Breakdown by model
- **Costs** - Cost analysis
- **Timeline** - Daily usage

#### Word Document Export

Editable documents:

```bash
llm export -c conv_abc123 --format docx -o conversation.docx
```

Includes:
- Professional formatting
- Table of contents
- Syntax highlighted code
- Metadata header
- Page numbers

### Advanced Features

#### Custom Templates

Create your own export templates:

```bash
# Create template
mkdir -p ~/.llm/export-templates/
nano ~/.llm/export-templates/my-template.html.jinja
```

**Template (`my-template.html.jinja`):**
```html
<!DOCTYPE html>
<html>
<head>
    <title>{{ conversation.title }}</title>
    <style>
        /* Your custom CSS */
    </style>
</head>
<body>
    <h1>{{ conversation.title }}</h1>
    <p>Date: {{ conversation.created_at }}</p>

    {% for message in messages %}
    <div class="message {{ message.role }}">
        <strong>{{ message.role }}:</strong>
        {{ message.content | markdown }}
    </div>
    {% endfor %}
</body>
</html>
```

Use it:
```bash
llm export -c conv_abc123 --template my-template -o output.html
```

#### Batch Export

Export all conversations:

```bash
# Export each conversation to separate file
llm export --all --format markdown --output-dir ./exports/

# Creates:
# ./exports/conv_abc123.md
# ./exports/conv_def456.md
# ...
```

#### Selective Content Export

```bash
# Only user messages
llm export -c conv_abc123 --role user -o user-messages.md

# Only assistant messages
llm export -c conv_abc123 --role assistant -o ai-responses.md

# Messages containing code
llm export -c conv_abc123 --with-code -o code-snippets.md

# Messages with attachments
llm export -c conv_abc123 --with-attachments -o with-images.html
```

#### Include/Exclude Metadata

```bash
# Minimal export (content only)
llm export -c conv_abc123 --no-metadata --no-timestamps -o clean.md

# Full export (everything)
llm export -c conv_abc123 \
  --include-metadata \
  --include-timestamps \
  --include-costs \
  --include-tokens \
  -o detailed.html
```

## Command Reference

### `llm export`

Export conversations to various formats.

```bash
llm export [OPTIONS]
```

**Options:**

**Selection:**
- `-c, --conversation ID` - Specific conversation
- `--last N` - Last N conversations
- `--all` - All conversations
- `--from DATE` - Start date
- `--to DATE` - End date
- `--month YYYY-MM` - Specific month
- `--year YYYY` - Specific year
- `--model TEXT` - Filter by model
- `--project TEXT` - Filter by project
- `--tag TEXT` - Filter by tag

**Format:**
- `--format FORMAT` - Output format: markdown, html, pdf, json, csv, docx, xlsx
- `-o, --output PATH` - Output file path
- `--output-dir PATH` - Output directory (for batch export)

**Content:**
- `--role ROLE` - Filter by role: user, assistant
- `--with-code` - Only messages with code blocks
- `--with-attachments` - Only messages with attachments
- `--include-metadata` - Include metadata
- `--include-timestamps` - Include timestamps
- `--include-costs` - Include cost information
- `--include-tokens` - Include token counts
- `--no-metadata` - Exclude metadata

**Styling (HTML/PDF):**
- `--theme THEME` - Visual theme
- `--template NAME` - Custom template
- `--css FILE` - Custom CSS file
- `--pdf-size SIZE` - PDF page size (a4, letter, legal)
- `--pdf-orientation ORIENTATION` - portrait or landscape
- `--include-toc` - Include table of contents

### `llm export formats`

List available export formats.

```bash
llm export formats
```

### `llm export templates`

List available templates.

```bash
llm export templates [--format FORMAT]
```

### `llm export preview`

Preview export without saving.

```bash
llm export preview -c conv_abc123 --format html
```

Opens in browser.

## Configuration

`~/.llm/export-config.yaml`:

```yaml
# Default settings
defaults:
  format: html
  theme: modern
  include_metadata: true
  include_timestamps: true

# Format-specific settings
html:
  theme: modern
  syntax_highlighting: true
  responsive: true
  include_search: true

pdf:
  page_size: a4
  orientation: portrait
  include_toc: true
  font: "Helvetica"

markdown:
  include_metadata: true
  code_blocks_language: true
  toc: true

# Paths
paths:
  templates: ~/.llm/export-templates/
  output_default: ~/llm-exports/

# Batch export
batch:
  naming: "{date}_{model}_{id}"
  organize_by: date  # date, model, project
```

## Real-World Examples

### Example 1: Weekly Team Report

```bash
# Export week's conversations as HTML
llm export \
  --from $(date -d '7 days ago' +%Y-%m-%d) \
  --to $(date +%Y-%m-%d) \
  --project "customer-support" \
  --format html \
  --theme modern \
  --include-metadata \
  -o weekly-support-report.html

# Send to team
mail -s "Weekly Support AI Usage" team@company.com < weekly-support-report.html
```

### Example 2: Code Review Documentation

```bash
# Export code review conversation
llm export \
  --conversation "Code review for PR #123" \
  --format docx \
  --with-code \
  --include-timestamps \
  -o code-review-pr123.docx

# Share with team
```

### Example 3: Research Archive

```bash
# Export research conversations to organized structure
llm export \
  --tag research \
  --format markdown \
  --output-dir ~/research-archive/ \
  --all

# Creates organized markdown files for version control
git add ~/research-archive/
git commit -m "Archive AI research conversations"
```

### Example 4: Cost Analysis Report

```bash
# Export monthly usage as Excel
llm export \
  --month 2024-11 \
  --format xlsx \
  --include-costs \
  --include-tokens \
  -o november-analysis.xlsx

# Open in Excel to analyze costs, usage patterns
```

### Example 5: Blog Post Creation

```bash
# Export interesting conversation as Markdown
llm export \
  --conversation "AI Ethics Discussion" \
  --format markdown \
  --no-metadata \
  -o blog-draft.md

# Edit and publish as blog post
```

## Troubleshooting

### PDF Generation Fails

**Problem:** `Error: PDF export failed`

**Common causes:**
1. WeasyPrint not installed
2. Missing system dependencies (on Linux)

**Solutions:**
```bash
# Install WeasyPrint
pip install weasyprint

# On Ubuntu/Debian, install system deps:
sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0

# Alternative: use ReportLab
pip install reportlab
llm export --format pdf --pdf-engine reportlab
```

### HTML Shows No Styling

**Problem:** Exported HTML has no styling.

**Solution:**
```bash
# Ensure Jinja2 is installed
pip install jinja2

# Use a theme
llm export --format html --theme modern
```

### Excel Export Empty

**Problem:** Excel file created but has no data.

**Solution:**
```bash
# Check conversation exists
llm logs -c conv_abc123

# Try CSV first to debug
llm export -c conv_abc123 --format csv
```

## Best Practices

1. **Use appropriate formats** - PDF for sharing, JSON for processing
2. **Include metadata** - Helps understand context later
3. **Regular backups** - Export monthly to archive
4. **Custom templates** - Create branded exports for client delivery
5. **Filter carefully** - Export only what you need
6. **Test locally first** - Preview before final export

## Integration Examples

### Automate Monthly Archives

```bash
#!/bin/bash
# monthly-archive.sh

MONTH=$(date -d 'last month' +%Y-%m)
OUTPUT_DIR=~/llm-archives/$MONTH

mkdir -p $OUTPUT_DIR

# Export as multiple formats
llm export --month $MONTH --format html -o $OUTPUT_DIR/conversations.html
llm export --month $MONTH --format json -o $OUTPUT_DIR/data.json
llm export --month $MONTH --format xlsx -o $OUTPUT_DIR/analysis.xlsx

# Compress
tar -czf ~/llm-archives/$MONTH.tar.gz $OUTPUT_DIR/

echo "Archived $MONTH to ~/llm-archives/$MONTH.tar.gz"
```

Run monthly:
```bash
crontab -e
# Add: 0 0 1 * * ~/monthly-archive.sh
```

### Export to Git

```bash
#!/bin/bash
# export-to-git.sh

llm export --all --format markdown --output-dir ./conversations/

cd ./conversations/
git add .
git commit -m "Update conversations $(date +%Y-%m-%d)"
git push
```

## Conclusion

Enhanced export transforms LLM from a personal tool to a shareable, documentable system:
- **Share knowledge** - Export for teams and clients
- **Create documentation** - Turn conversations into docs
- **Archive safely** - Multiple format backups
- **Analyze data** - Export to Excel/CSV for analysis
- **Professional output** - Beautiful PDFs and HTML

Start exporting your conversations to unlock their full value!
