import re
import json
from .gemini_service import GeminiService

GENERATION_PROMPT_TEMPLATE = """
You are a software test scenario generator for an educational tool.
Based on the software requirements below, generate comprehensive test scenarios.
Include positive (happy path), negative (error/invalid input), and edge case scenarios.

Return your response ONLY as a valid JSON object. Do not include any text before or after the JSON.

The JSON must follow this exact format:
{{
  "scenarios": [
    {{
      "id": "TS_01",
      "description": "<short scenario title>",
      "preconditions": "<what must be true before the test>",
      "steps": [
        "Step 1: <action>",
        "Step 2: <action>",
        "Step 3: <action>"
      ],
      "expected_result": "<what should happen after the steps>",
      "type": "positive"
    }},
    {{
      "id": "TS_02",
      "description": "<short scenario title>",
      "preconditions": "<what must be true before the test>",
      "steps": [
        "Step 1: <action>",
        "Step 2: <action>"
      ],
      "expected_result": "<what should happen after the steps>",
      "type": "negative"
    }}
  ]
}}

Rules:
- Generate between 4 and 8 test scenarios.
- Each "id" must be unique and follow the format TS_01, TS_02, etc.
- "type" must be exactly "positive", "negative", or "edge".
- "steps" must be a JSON array of strings.
- Cover boundary conditions and error scenarios.

Requirements:
---
{requirements_text}
---
"""


class TestScenarioGenerator:
    """
    Constructs the generation prompt and calls the LLM to produce test scenarios.
    Corresponds to the TestScenarioGenerator class in the system class diagram.
    """

    def __init__(self):
        self.llm_client = GeminiService()

    def construct_prompt(self, requirements_text: str) -> str:
        return GENERATION_PROMPT_TEMPLATE.format(requirements_text=requirements_text.strip())

    def generate_scenarios(self, requirements_text: str) -> list:
        """
        Returns a list of scenario dicts, each with:
        id, description, preconditions, steps (list), expected_result, type
        """
        prompt = self.construct_prompt(requirements_text)
        raw_response = self.llm_client.fetch_response(prompt)
        return self._parse_json(raw_response)

    def _parse_json(self, raw_response: str) -> list:
        """
        Extract and parse the JSON array of scenarios from the LLM response.
        Returns an empty list if parsing fails.
        """
        if not raw_response:
            return []

        try:
            json_match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(raw_response)

            scenarios = data.get('scenarios', [])
            validated = []
            for i, s in enumerate(scenarios):
                if not isinstance(s, dict):
                    continue

                steps = s.get('steps', [])
                if isinstance(steps, str):
                    steps = [steps]

                scenario_type = s.get('type', 'positive').lower()
                if scenario_type not in ('positive', 'negative', 'edge'):
                    scenario_type = 'positive'

                validated.append({
                    'id': s.get('id', f'TS_{i+1:02d}'),
                    'description': str(s.get('description', '')),
                    'preconditions': str(s.get('preconditions', '')),
                    'steps': steps,
                    'expected_result': str(s.get('expected_result', '')),
                    'type': scenario_type,
                })

            return validated

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[TestScenarioGenerator] Failed to parse response: {e}")
            return []
