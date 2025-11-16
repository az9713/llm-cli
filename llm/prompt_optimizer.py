"""
Prompt optimization functionality for LLM CLI.

Optimize prompts for better results using AI-powered improvements.
"""

import json
import time
from typing import Optional, List, Dict, Any

from llm import get_model


class PromptOptimizer:
    """Optimizes prompts using AI."""

    def optimize(
        self,
        prompt: str,
        strategy: str = "auto",
        model: str = "gpt-4o"
    ) -> Dict[str, Any]:
        """Optimize a prompt using specified strategy."""

        if strategy == "auto":
            # Automatically determine best optimization
            strategy = self._determine_strategy(prompt)

        optimizer_prompts = {
            "expand": "Expand this prompt to be more detailed and specific:\n\n{prompt}",
            "simplify": "Simplify this prompt to be more concise and clear:\n\n{prompt}",
            "clarify": "Clarify this prompt to remove ambiguity:\n\n{prompt}"
        }

        optimizer_prompt = optimizer_prompts.get(strategy, optimizer_prompts["clarify"])

        # Use model to optimize
        try:
            llm = get_model(model)
            response = llm.prompt(
                optimizer_prompt.format(prompt=prompt),
                system="You are an expert at writing effective prompts for AI models. Provide only the improved prompt, without explanations."
            )

            optimized = response.text().strip()

            # Test both versions
            original_result = self._test_prompt(prompt, model)
            optimized_result = self._test_prompt(optimized, model)

            return {
                "original": prompt,
                "optimized": optimized,
                "strategy": strategy,
                "original_result": original_result,
                "optimized_result": optimized_result,
                "improvement": self._calculate_improvement(original_result, optimized_result)
            }

        except Exception as e:
            return {
                "error": str(e),
                "original": prompt
            }

    def test_variants(
        self,
        prompt: str,
        num_variants: int = 3,
        model: str = "gpt-4o"
    ) -> List[Dict[str, Any]]:
        """Generate and test multiple prompt variants."""
        variants = []

        # Generate variants
        for i in range(num_variants):
            variant_prompt = f"Create variant #{i+1} of this prompt (make it effective in a different way):\n\n{prompt}"

            try:
                llm = get_model(model)
                response = llm.prompt(
                    variant_prompt,
                    system="You are an expert at writing effective prompts. Provide only the variant prompt."
                )

                variant = response.text().strip()
                result = self._test_prompt(variant, model)

                variants.append({
                    "variant": variant,
                    "number": i + 1,
                    "result": result
                })

            except Exception as e:
                variants.append({
                    "variant": None,
                    "number": i + 1,
                    "error": str(e)
                })

        return variants

    def compare_variants(
        self,
        prompt1: str,
        prompt2: str,
        test_input: Optional[str] = None,
        model: str = "gpt-4o"
    ) -> Dict[str, Any]:
        """Compare two prompt variants."""
        result1 = self._test_prompt(prompt1, model, test_input)
        result2 = self._test_prompt(prompt2, model, test_input)

        return {
            "prompt1": {
                "text": prompt1,
                "result": result1
            },
            "prompt2": {
                "text": prompt2,
                "result": result2
            },
            "comparison": self._compare_results(result1, result2)
        }

    def _determine_strategy(self, prompt: str) -> str:
        """Determine best optimization strategy for a prompt."""
        if len(prompt.split()) < 10:
            return "expand"
        elif len(prompt.split()) > 100:
            return "simplify"
        else:
            return "clarify"

    def _test_prompt(
        self,
        prompt: str,
        model: str,
        test_input: Optional[str] = None
    ) -> Dict[str, Any]:
        """Test a prompt and collect metrics."""
        try:
            llm = get_model(model)
            test_text = test_input or "Test this prompt with a sample query"

            start_time = time.time()
            response = llm.prompt(test_text.format(prompt=prompt) if "{prompt}" in test_text else prompt)
            end_time = time.time()

            response_text = response.text()

            return {
                "response": response_text,
                "time": end_time - start_time,
                "length": len(response_text),
                "tokens": getattr(response, "input_tokens", 0) + getattr(response, "output_tokens", 0)
            }

        except Exception as e:
            return {"error": str(e)}

    def _calculate_improvement(self, original: Dict, optimized: Dict) -> str:
        """Calculate improvement between original and optimized."""
        if "error" in original or "error" in optimized:
            return "Unable to calculate"

        # Simple heuristic - longer responses often indicate more detailed answers
        length_ratio = optimized.get("length", 0) / max(original.get("length", 1), 1)

        if length_ratio > 1.2:
            return "Significant improvement (more detailed)"
        elif length_ratio > 1.05:
            return "Moderate improvement"
        else:
            return "Similar quality"

    def _compare_results(self, result1: Dict, result2: Dict) -> Dict[str, Any]:
        """Compare two results."""
        return {
            "length_diff": result2.get("length", 0) - result1.get("length", 0),
            "time_diff": result2.get("time", 0) - result1.get("time", 0),
            "recommendation": "Prompt 2" if result2.get("length", 0) > result1.get("length", 0) else "Prompt 1"
        }
