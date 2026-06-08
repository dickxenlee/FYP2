import re
import json
from .gemini_service import GeminiService

DETAILED_CASE_PROMPT = """
You are a senior Software QA Engineer. Expand each high-level test scenario into a full detailed test case.

Return ONLY a valid JSON object. No markdown, no code fences, no extra text.

JSON format:
{{
  "detailed_cases": [
    {{
      "scenario_id": "<same scenario_id from input>",
      "test_data": "<specific input values, usernames, file names, data used in this test>",
      "steps": [
        "Step 1: <precise action>",
        "Step 2: <precise action>",
        "Step 3: <precise action>"
      ],
      "expected_results": "<detailed expected outcome with specific values>",
      "postconditions": "<system or data state after the test completes>"
    }}
  ]
}}

Rules:
- Generate exactly one detailed_case per scenario in the input
- scenario_id in output must match scenario_id in input exactly
- steps must be specific and actionable (3 to 6 steps per scenario)
- test_data must include concrete values (e.g. username = "john@test.com", file = "photo.jpg 4.8MB")
- postconditions describe the system state after the test (e.g. "Profile picture updated in database")

Test Scenarios to expand:
---
{scenarios_text}
---
"""


class DetailedCaseGenerator:
    """
    Expands high-level test scenarios into full detailed test cases with
    test data, step-by-step instructions, expected results, and postconditions.
    Called only when the user clicks "Generate Detailed Test Cases" (Section 6).
    """

    def __init__(self):
        self.llm_client = GeminiService()

    def generate(self, scenarios: list) -> list:
        if not scenarios:
            return []

        lines = []
        for s in scenarios:
            sid = s.get('scenario_id', s.get('id', ''))
            lines.append(
                f"Scenario ID: {sid}\n"
                f"Description: {s.get('description', '')}\n"
                f"Preconditions: {s.get('preconditions', '')}\n"
                f"Expected Result: {s.get('expected_result', '')}"
            )

        prompt = DETAILED_CASE_PROMPT.format(scenarios_text='\n\n'.join(lines))
        raw = self.llm_client.fetch_response(prompt)
        return self._parse(raw)

    def _parse(self, raw: str) -> list:
        if not raw:
            return []
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group() if match else raw)

            cases = []
            for c in data.get('detailed_cases', []):
                if not isinstance(c, dict):
                    continue
                steps = c.get('steps', [])
                if isinstance(steps, str):
                    steps = [steps]
                cases.append({
                    'scenario_id': str(c.get('scenario_id', '')),
                    'test_data': str(c.get('test_data', '')),
                    'steps': [str(s) for s in steps],
                    'expected_results': str(c.get('expected_results', '')),
                    'postconditions': str(c.get('postconditions', '')),
                })
            return cases

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"[DetailedCaseGenerator] Parse error: {e}")
            return []
