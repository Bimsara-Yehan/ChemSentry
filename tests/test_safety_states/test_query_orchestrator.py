"""Tests for the LLM-based query orchestrator layer (M3 Phase 3)."""

from unittest.mock import MagicMock, patch

from agents.agent_b_analysis.query_orchestrator import OpenQueryOrchestrator


def test_orchestrator_fallback_on_no_client():
    """Verifies that orchestrator gracefully drops to fallback message if client is missing."""
    orchestrator = OpenQueryOrchestrator(api_key=None)
    result = orchestrator.handle_query("why did Zone B alert?")
    assert "FALLBACK: Unable to orchestrate query dynamically" in result


@patch("agents.agent_b_analysis.query_orchestrator.Mistral")
def test_orchestrator_no_tools_needed(mock_mistral_class):
    """Verifies handling when LLM returns direct response without calling any tools."""
    mock_client = MagicMock()
    mock_mistral_class.return_value = mock_client
    
    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = "This is a direct answer with no tools needed."
    mock_client.chat.complete.return_value.choices = [mock_choice]

    orchestrator = OpenQueryOrchestrator(api_key="fake-key")
    # Must register at least one dummy tool so it doesn't trigger fallback due to empty tools list
    orchestrator.register_tool("dummy", "description", {}, lambda: "ok")
    
    result = orchestrator.handle_query("General question")
    assert result == "This is a direct answer with no tools needed."


@patch("agents.agent_b_analysis.query_orchestrator.Mistral")
def test_orchestrator_calls_tool_successfully(mock_mistral_class):
    """Verifies that orchestrator identifies a tool call, executes it, and returns synthesized response."""
    mock_client = MagicMock()
    mock_mistral_class.return_value = mock_client

    # First turn: returns tool call
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call-1"
    mock_tool_call.function.name = "get_co_storage_rules"
    mock_tool_call.function.arguments = '{"chemical": "Toluene"}'
    
    mock_response_1 = MagicMock()
    mock_response_1.choices = [MagicMock(message=MagicMock(tool_calls=[mock_tool_call], content=None))]
    
    # Second turn: returns final answer
    mock_response_2 = MagicMock()
    mock_response_2.choices = [MagicMock(message=MagicMock(tool_calls=None, content="Based on co-storage rules, Toluene should not be stored with oxidizers."))]
    
    mock_client.chat.complete.side_effect = [mock_response_1, mock_response_2]

    orchestrator = OpenQueryOrchestrator(api_key="fake-key")
    
    mock_tool_func = MagicMock(return_value="Rule: Incompatible with nitric acid.")
    orchestrator.register_tool(
        name="get_co_storage_rules",
        description="Lookup co-storage rules",
        parameters={
            "type": "object",
            "properties": {
                "chemical": {"type": "string"}
            },
            "required": ["chemical"]
        },
        func=mock_tool_func
    )

    result = orchestrator.handle_query("Tell me rules for Toluene")
    
    mock_tool_func.assert_called_once_with(chemical="Toluene")
    assert result == "Based on co-storage rules, Toluene should not be stored with oxidizers."
