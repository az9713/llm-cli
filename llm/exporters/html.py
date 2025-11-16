"""HTML export functionality."""

from typing import Dict, Any, Optional
from datetime import datetime


DEFAULT_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        h1 {{
            margin: 0 0 10px 0;
            color: #333;
        }}
        .meta {{
            color: #666;
            font-size: 0.9em;
        }}
        .message {{
            margin-bottom: 30px;
            padding: 20px;
            border-radius: 8px;
        }}
        .system-message {{
            background: #fff9e6;
            border-left: 4px solid #ffcc00;
        }}
        .user-message {{
            background: #e3f2fd;
            border-left: 4px solid #2196f3;
        }}
        .assistant-message {{
            background: #f3e5f5;
            border-left: 4px solid #9c27b0;
        }}
        .role {{
            font-weight: bold;
            text-transform: uppercase;
            font-size: 0.85em;
            margin-bottom: 10px;
            color: #555;
        }}
        .content {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .timestamp {{
            color: #999;
            font-size: 0.85em;
            margin-top: 10px;
        }}
        .comparison {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .model-response {{
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
        }}
        .model-name {{
            font-weight: bold;
            font-size: 1.1em;
            margin-bottom: 10px;
            color: #333;
        }}
        .metrics {{
            background: #f5f5f5;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 10px;
            font-size: 0.9em;
        }}
        .metric {{
            display: inline-block;
            margin-right: 15px;
        }}
        .summary {{
            background: #e8f5e9;
            border: 1px solid #4caf50;
            border-radius: 8px;
            padding: 15px;
            margin-top: 30px;
        }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""


class HTMLExporter:
    """Export data to HTML format."""

    def __init__(self, template: Optional[str] = None):
        self.template = template or DEFAULT_TEMPLATE

    def export_conversation(
        self,
        conversation: Dict[str, Any],
        include_system: bool = True
    ) -> str:
        """Export conversation to HTML."""
        content_parts = []

        # Header
        content_parts.append('<div class="header">')
        content_parts.append(f'<h1>{self._escape_html(conversation.get("name", "Conversation"))}</h1>')
        content_parts.append(f'<div class="meta">Model: {self._escape_html(conversation.get("model", "Unknown"))}</div>')
        content_parts.append(f'<div class="meta">ID: {self._escape_html(conversation.get("id", ""))}</div>')
        content_parts.append('</div>')

        # Messages
        for msg in conversation.get("messages", []):
            system = msg.get("system")
            prompt = msg.get("prompt", "")
            response = msg.get("response", "")
            timestamp = msg.get("datetime_utc", "")

            # System message
            if include_system and system:
                content_parts.append('<div class="message system-message">')
                content_parts.append('<div class="role">System</div>')
                content_parts.append(f'<div class="content">{self._escape_html(system)}</div>')
                content_parts.append('</div>')

            # User message
            if prompt:
                content_parts.append('<div class="message user-message">')
                content_parts.append('<div class="role">User</div>')
                content_parts.append(f'<div class="content">{self._escape_html(prompt)}</div>')
                if timestamp:
                    content_parts.append(f'<div class="timestamp">{self._escape_html(timestamp)}</div>')
                content_parts.append('</div>')

            # Assistant message
            if response:
                content_parts.append('<div class="message assistant-message">')
                content_parts.append('<div class="role">Assistant</div>')
                content_parts.append(f'<div class="content">{self._escape_html(response)}</div>')
                content_parts.append('</div>')

        content = '\n'.join(content_parts)
        title = conversation.get("name", "Conversation")

        return self.template.format(title=self._escape_html(title), content=content)

    def export_comparison(self, comparison: Dict[str, Any]) -> str:
        """Export model comparison to HTML."""
        content_parts = []

        # Header
        content_parts.append('<div class="header">')
        content_parts.append('<h1>Model Comparison</h1>')
        content_parts.append(f'<div class="meta">Prompt: {self._escape_html(comparison.get("prompt", ""))}</div>')
        content_parts.append(f'<div class="meta">Models: {", ".join(comparison.get("models", []))}</div>')
        content_parts.append(f'<div class="meta">Created: {self._escape_html(comparison.get("created_at", ""))}</div>')
        content_parts.append('</div>')

        # Responses
        content_parts.append('<div class="comparison">')
        for response in comparison.get("responses", []):
            content_parts.append('<div class="model-response">')
            content_parts.append(f'<div class="model-name">{self._escape_html(response.get("model", ""))}</div>')

            if response.get("success"):
                # Metrics
                content_parts.append('<div class="metrics">')
                content_parts.append(f'<span class="metric">Time: {response.get("time", 0):.2f}s</span>')
                content_parts.append(f'<span class="metric">Tokens: {response.get("tokens", {}).get("total", 0)}</span>')
                content_parts.append(f'<span class="metric">Cost: ${response.get("cost", 0):.4f}</span>')
                content_parts.append('</div>')

                # Response text
                content_parts.append(f'<div class="content">{self._escape_html(response.get("text", ""))}</div>')
            else:
                content_parts.append(f'<div class="content" style="color: #d32f2f;">Error: {self._escape_html(response.get("error", "Unknown error"))}</div>')

            content_parts.append('</div>')
        content_parts.append('</div>')

        # Summary
        successful = [r for r in comparison.get("responses", []) if r.get("success")]
        if successful:
            fastest = min(successful, key=lambda r: r.get("time", float('inf')))
            cheapest = min(successful, key=lambda r: r.get("cost", float('inf')))

            content_parts.append('<div class="summary">')
            content_parts.append('<h2>Summary</h2>')
            content_parts.append(f'<div>Fastest: {fastest["model"]} ({fastest.get("time", 0):.2f}s)</div>')
            content_parts.append(f'<div>Cheapest: {cheapest["model"]} (${cheapest.get("cost", 0):.4f})</div>')
            content_parts.append('</div>')

        content = '\n'.join(content_parts)

        return self.template.format(title="Model Comparison", content=content)

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        if not isinstance(text, str):
            text = str(text)
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))
