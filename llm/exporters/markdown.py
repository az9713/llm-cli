"""Markdown export functionality."""

from typing import Dict, Any


class MarkdownExporter:
    """Export data to Markdown format."""

    def export_conversation(
        self,
        conversation: Dict[str, Any],
        include_system: bool = True
    ) -> str:
        """Export conversation to Markdown."""
        output = []

        # Header
        output.append(f"# {conversation.get('name', 'Conversation')}\n")
        output.append(f"**Model:** {conversation.get('model', 'Unknown')}  ")
        output.append(f"**ID:** {conversation.get('id', '')}  ")
        output.append("")

        # Messages
        for i, msg in enumerate(conversation.get("messages", []), 1):
            system = msg.get("system")
            prompt = msg.get("prompt", "")
            response = msg.get("response", "")
            timestamp = msg.get("datetime_utc", "")

            output.append("---\n")

            # System message
            if include_system and system:
                output.append("### 🔧 System\n")
                output.append(f"```\n{system}\n```\n")

            # User message
            if prompt:
                output.append(f"### 👤 User{' (' + timestamp + ')' if timestamp else ''}\n")
                output.append(f"{prompt}\n")

            # Assistant message
            if response:
                output.append("### 🤖 Assistant\n")
                output.append(f"{response}\n")

        return "\n".join(output)

    def export_comparison(self, comparison: Dict[str, Any]) -> str:
        """Export model comparison to Markdown."""
        output = []

        # Header
        output.append("# Model Comparison\n")
        output.append(f"**Prompt:** {comparison.get('prompt', '')}  ")
        output.append(f"**Models:** {', '.join(comparison.get('models', []))}  ")
        output.append(f"**Created:** {comparison.get('created_at', '')}  ")
        output.append("")

        # Responses
        for response in comparison.get("responses", []):
            output.append("---\n")
            output.append(f"## {response.get('model', 'Unknown Model')}\n")

            if response.get("success"):
                # Metrics
                time = response.get("time", 0)
                tokens = response.get("tokens", {}).get("total", 0)
                cost = response.get("cost", 0)

                output.append(f"**Time:** {time:.2f}s | **Tokens:** {tokens} | **Cost:** ${cost:.4f}\n")

                # Response text
                output.append(f"{response.get('text', '')}\n")
            else:
                output.append(f"**Error:** {response.get('error', 'Unknown error')}\n")

        # Summary
        successful = [r for r in comparison.get("responses", []) if r.get("success")]
        if successful:
            output.append("---\n")
            output.append("## Summary\n")

            fastest = min(successful, key=lambda r: r.get("time", float('inf')))
            cheapest = min(successful, key=lambda r: r.get("cost", float('inf')))

            output.append(f"- **Fastest:** {fastest['model']} ({fastest.get('time', 0):.2f}s)")
            output.append(f"- **Cheapest:** {cheapest['model']} (${cheapest.get('cost', 0):.4f})")

        return "\n".join(output)
