"""LLM query orchestrator (M3 Phase 3).

This module routes complex safety queries by selecting from classical information
retrieval tools. The LLM only coordinates which tools to use; it does not decide safety.
"""

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from mistralai.client import Mistral

logger = logging.getLogger(__name__)


class OpenQueryOrchestrator:
    """Orchestrates open-ended safety officer queries using Mistral AI tool calling.

    The LLM dynamically selects tools registered to query classical indexes, lookup
    incidents, inspect co-storage rules, or retrieve deterministic safety evaluations.
    """

    def __init__(self, api_key: str | None = None):
        """Initializes orchestrator with client and tool mapping."""
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        self.model = "mistral-small-latest"
        self._tools: dict[str, Callable] = {}
        self._tool_definitions: list[dict[str, Any]] = []

        if not self.api_key:
            logger.warning("MISTRAL_API_KEY not found. Orchestrator will run in fallback mode.")
            self.client = None
        else:
            self.client = Mistral(api_key=self.api_key)

    def register_tool(self, name: str, description: str, parameters: dict[str, Any], func: Callable):
        """Registers a Python function as a tool the LLM can call.

        Args:
            name: Name of the tool.
            description: Tool description explaining when the LLM should choose it.
            parameters: JSON schema of parameters.
            func: The Python callable function.
        """
        self._tools[name] = func
        self._tool_definitions.append({
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        })

    def handle_query(self, query: str) -> str:
        """Processes query by dynamically invoking registered tools as selected by the LLM.

        Args:
            query: User's open-ended query.

        Returns:
            The final orchestrated answer synthesizing the tool outputs.
        """
        if not self.client or not self._tools:
            # Fallback when client is not initialized or no tools are registered
            return f"FALLBACK: Unable to orchestrate query dynamically. Received query: '{query}'."

        messages = [
            {"role": "system", "content": "You are ChemSentry's query orchestrator. Answer user queries by calling tools to retrieve real safety details. Never guess or fabricate rules. Present facts exactly as returned by tools."},
            {"role": "user", "content": query}
        ]

        try:
            # First turn: call the model with tools
            response = self.client.chat.complete(
                model=self.model,
                messages=messages,
                tools=self._tool_definitions,
                tool_choice="auto"
            )

            message = response.choices[0].message
            if message.tool_calls:
                messages.append(message)
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    if tool_name in self._tools:
                        tool_args = json.loads(tool_call.function.arguments)
                        # Call registered tool
                        try:
                            tool_result = self._tools[tool_name](**tool_args)
                        except Exception as inner:  # noqa: BLE001
                            tool_result = f"Error executing tool: {inner}"
                        
                        messages.append({
                             "role": "tool",
                             "name": tool_name,
                             "content": str(tool_result),
                             "tool_call_id": tool_call.id
                        })
                
                # Second turn: synthesize result
                final_response = self.client.chat.complete(
                    model=self.model,
                    messages=messages
                )
                return final_response.choices[0].message.content.strip()
            else:
                return message.content.strip()

        except Exception as e:  # noqa: BLE001
            logger.error(f"Error in orchestrator handling: {e}")
            return f"FALLBACK: Error handling query '{query}': {e}"
