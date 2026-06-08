import re
import json
from .gemini_service import GeminiService

ANALYSIS_PROMPT_TEMPLATE = """
You are a software requirements quality analyzer for an educational tool.
Analyze the following software requirements and evaluate their quality.

Return your response ONLY as a valid JSON object. Do not include any text before or after the JSON.

The JSON must follow this exact format:
{{
  "score": <an integer between 0 and 100>,
  "feedback": [
    {{"type": "positive", "message": "<what is good about these requirements>"}},
    {{"type": "warning", "message": "<what is unclear, ambiguous, or missing>"}}
  ],
  "suggested_requirement": "<if score is below 80, provide a professionally rewritten version of the requirement that removes all ambiguity, adds specific measurable criteria, and is clearly testable. Write it using 'The system shall...' format. If score is 80 or above, set this to an empty string.>"
}}

Scoring guide:
- 80 to 100: Requirements are clear, complete, specific, and testable.
- 60 to 79: Requirements are mostly clear but have some vague or missing details.
- 0 to 59: Requirements are vague, ambiguous, or missing key information.

Rules for suggested_requirement:
- Only provide a non-empty suggested_requirement when the score is below 80.
- The suggestion must directly fix every ambiguity listed in the feedback warnings.
- Use professional software requirements language with specific, measurable conditions.

Requirements to analyze:
---
{requirements_text}
---
"""


class RequirementAnalyzer:
    """
    Sends requirements to the LLM and retrieves a quality score, feedback,
    and a suggested improved requirement when quality is low.
    """

    def __init__(self):
        self.llm_client = GeminiService()

    def _run_nlp_preprocessing(self, text: str) -> str:
        text = text.strip()
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        return text

    def get_llm_quality_score(self, requirements_text: str) -> dict:
        """
        Calls the LLM to get a quality score, feedback, and suggested requirement.
        Returns a dict with 'score', 'feedback', and 'suggested_requirement'.
        """
        cleaned_text = self._run_nlp_preprocessing(requirements_text)
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(requirements_text=cleaned_text)
        raw_response = self.llm_client.fetch_response(prompt)
        return self._parse_analysis_response(raw_response)

    def _parse_analysis_response(self, raw_response: str) -> dict:
        if not raw_response:
            return self._default_error_response()

        try:
            json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(raw_response)

            score = int(data.get('score', 50))
            score = max(0, min(100, score))

            feedback = data.get('feedback', [])
            validated_feedback = []
            for item in feedback:
                if isinstance(item, dict) and 'type' in item and 'message' in item:
                    validated_feedback.append({
                        'type': item['type'],
                        'message': str(item['message'])
                    })

            suggested_requirement = str(data.get('suggested_requirement', ''))

            return {
                'score': score,
                'feedback': validated_feedback,
                'suggested_requirement': suggested_requirement,
            }

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[RequirementAnalyzer] Failed to parse response: {e}")
            return self._default_error_response()

    def _default_error_response(self) -> dict:
        return {
            'score': 0,
            'feedback': [
                {
                    'type': 'warning',
                    'message': 'Could not analyze requirements. Please check your API key and try again.'
                }
            ],
            'suggested_requirement': '',
        }
