"""LLM-based explanation and translation layer (M3 Phase 3).

This module uses Mistral AI to summarize, explain, and translate deterministic safety states.
Following the central project safety constraint: the LLM never decides safety; it only
explains or translates deterministic decisions made by the core safety state machine.
"""

import logging
import os

from mistralai.client import Mistral

from agents.protocols.schemas import SafetyEvaluationResult

logger = logging.getLogger(__name__)


class SafetyCardNarrator:
    """Explains and translates safety cards and alerts using Mistral AI.

    Technique: Prompts Mistral AI with pre-determined safety states, ensuring
    the LLM never makes the safety decision itself but instead adds value via
    natural language phrasing, summaries, and multilingual translations.
    """

    def __init__(self, api_key: str | None = None):
        """Initializes the narrator, loading the key from the environment if not provided."""
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY")
        self.model = "mistral-small-latest"
        
        if not self.api_key:
            logger.warning("MISTRAL_API_KEY not found. Narrator will run in fallback mode.")
            self.client = None
        else:
            self.client = Mistral(api_key=self.api_key)

    def explain_alert(self, result: SafetyEvaluationResult) -> str:
        """Generates a natural language explanation of a deterministic safety result.

        Args:
            result: The completed SafetyEvaluationResult.

        Returns:
            A string explaining the safety state and the evidence.
        """
        if not self.client:
            return f"FALLBACK: The safety state is {result.state.value}. {result.reasoning}"

        # Build prompt that forces adherence to the deterministic verdict
        system_prompt = (
            "You are ChemSentry's safety communication assistant. "
            "Your job is to explain the safety evaluation result to a factory worker. "
            "CRITICAL: You MUST NOT change or decide the safety state. The state has already "
            f"been determined as: {result.state.value}. "
            "Do not contradict this status. Explain the details using the threshold and current readings provided."
        )

        user_content = (
            f"Chemical: {result.chemical_name}\n"
            f"Zone: {result.zone_id}\n"
            f"Metric: {result.metric_name}\n"
            f"Current Value: {result.current_value} {result.unit}\n"
            f"Retrieved Threshold: {result.threshold_value} {result.unit if result.threshold_value is not None else ''}\n"
            f"Deterministic Reasoning: {result.reasoning}\n"
            f"Source Citation: {result.provenance.citation if result.provenance else 'N/A'}"
        )

        try:
            response = self.client.chat.complete(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Mistral API call failed: {e}")
            return f"FALLBACK: The safety state is {result.state.value}. {result.reasoning}"

    def translate_safety_card(self, result: SafetyEvaluationResult, language: str) -> dict[str, str]:
        """Translates safety card contents into Sinhala ('si') or Tamil ('ta').

        Args:
            result: The SafetyEvaluationResult to translate.
            language: The target language code ('si' or 'ta').

        Returns:
            A dictionary containing translated fields.
        """
        target_lang = "Sinhala" if language.lower() == "si" else "Tamil"
        
        fallback_data = {
            "chemical_name": result.chemical_name,
            "state": result.state.value,
            "reasoning": f"[Translation Unavailable] {result.reasoning}",
            "citation": result.provenance.citation if result.provenance else "N/A"
        }

        if not self.client:
            return fallback_data

        system_prompt = (
            f"You are a professional chemical safety translator translating to {target_lang}. "
            "Translate the safety card information accurately. Keep chemical names in standard english spelling "
            "or transliterated if appropriate, but translate the safety verdict, warnings, and reasoning text. "
            "Format the response as a valid JSON with keys: chemical_name, state, reasoning, and citation."
        )

        user_content = (
            f"Chemical: {result.chemical_name}\n"
            f"Safety State: {result.state.value}\n"
            f"Reasoning: {result.reasoning}\n"
            f"Citation: {result.provenance.citation if result.provenance else 'N/A'}"
        )

        try:
            response = self.client.chat.complete(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ]
            )
            import json
            content = response.choices[0].message.content.strip()
            return json.loads(content)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Mistral translation call failed: {e}")
            return fallback_data
