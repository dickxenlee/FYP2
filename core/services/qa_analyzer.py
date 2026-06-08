import re
import json
from .gemini_service import GeminiService

QA_ANALYSIS_PROMPT = """
You are a senior Software Quality Assurance Engineer performing a professional requirements review.

Analyze the software requirement below and return a single comprehensive JSON QA report.
Return ONLY the JSON object. No markdown fences, no extra text before or after.

Required JSON format:
{{
  "requirement_info": {{
    "requirement_id": "REQ-001",
    "actors": ["list of actors or users"],
    "actions": ["list of actions the system or actor performs"],
    "business_rules": ["list of business rules"],
    "constraints": ["list of constraints such as formats, limits"],
    "validation_rules": ["list of input validation rules"],
    "error_handling": ["list of error handling requirements"],
    "non_functional": ["list of non-functional requirements, e.g. performance, security"]
  }},
  "quality_assessment": {{
    "clarity_score": <integer 0-100>,
    "completeness_score": <integer 0-100>,
    "testability_score": <integer 0-100>,
    "overall_score": <integer — weighted average of the three scores>,
    "severity": "<High if overall < 60 | Medium if 60-79 | Low if >= 80>",
    "positive_aspects": ["what is well-defined"],
    "warnings": ["what is ambiguous, missing, or hard to test"]
  }},
  "test_conditions": [
    {{
      "condition_id": "C01",
      "description": "<concise testable condition, one sentence>",
      "type": "<Positive | Negative | Boundary | Security | Performance>",
      "priority": "<High | Medium | Low>"
    }}
  ],
  "gaps": [
    {{
      "issue_id": "G01",
      "issue_type": "<Ambiguity | Missing Rule | Incomplete | Contradiction | Non-Testable>",
      "description": "<what is missing or unclear>",
      "suggested_clarification": "<how the requirement writer should fix it>"
    }}
  ],
  "test_scenarios": [
    {{
      "scenario_id": "TS-001",
      "requirement_ref": "REQ-001",
      "condition_ref": "C01",
      "description": "<concise scenario title — under 10 words>",
      "preconditions": "<system state required before test — one sentence>",
      "expected_result": "<expected outcome — one sentence>",
      "priority": "<High | Medium | Low>",
      "type": "<positive | negative | edge>"
    }}
  ],
  "suggested_requirement": "<if overall_score < 80, provide a professionally rewritten version using 'The system shall...' format. If overall_score >= 80, return an empty string.>"
}}

Generation rules:
- Generate 4 to 8 test_conditions covering Positive, Negative, and Boundary types at minimum
- Generate 4 to 8 test_scenarios — link each to its condition via condition_ref
- Scenario descriptions must be concise — do NOT write step-by-step instructions
- Only include gaps that represent real issues — omit the array if the requirement is complete
- severity = High when overall < 60, Medium when 60–79, Low when >= 80

Example output for "The system shall allow registered users to upload a profile picture":

requirement_id = "REQ-001"
test_conditions include: C01 Upload valid JPG under 5MB (Positive, High), C02 Upload PNG exactly 5MB (Boundary, High), C03 Upload file over 5MB (Negative, High)
test_scenarios include: TS-001 linked to C01, TS-002 linked to C02, etc.
gaps might include: G01 Ambiguity — file size limit not specified

Requirement to analyze:
---
{requirements_text}
---
"""


class QAAnalyzer:
    """
    Single comprehensive LLM call that returns the full QA report:
    requirement extraction, quality scores, test conditions, gaps, and test scenarios.
    Replaces the separate RequirementAnalyzer + TestScenarioGenerator for the main flow.
    """

    def __init__(self):
        self.llm_client = GeminiService()

    def analyze(self, requirements_text: str) -> dict:
        """
        Returns a dict with keys:
        requirement_info, quality_assessment, test_conditions, gaps,
        test_scenarios, suggested_requirement.
        """
        prompt = QA_ANALYSIS_PROMPT.format(requirements_text=requirements_text.strip())
        raw = self.llm_client.fetch_response(prompt)
        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        if not raw:
            return self._default_error()

        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group() if match else raw)

            req_info = data.get('requirement_info', {})
            qa = data.get('quality_assessment', {})

            clarity = max(0, min(100, int(qa.get('clarity_score', 50))))
            completeness = max(0, min(100, int(qa.get('completeness_score', 50))))
            testability = max(0, min(100, int(qa.get('testability_score', 50))))
            overall = max(0, min(100, int(qa.get('overall_score', 50))))

            if overall >= 80:
                severity = 'Low'
            elif overall >= 60:
                severity = 'Medium'
            else:
                severity = 'High'

            conditions = []
            for c in data.get('test_conditions', []):
                if isinstance(c, dict):
                    conditions.append({
                        'condition_id': str(c.get('condition_id', '')),
                        'description': str(c.get('description', '')),
                        'type': str(c.get('type', 'Positive')),
                        'priority': str(c.get('priority', 'Medium')),
                    })

            gaps = []
            for g in data.get('gaps', []):
                if isinstance(g, dict):
                    gaps.append({
                        'issue_id': str(g.get('issue_id', '')),
                        'issue_type': str(g.get('issue_type', '')),
                        'description': str(g.get('description', '')),
                        'suggested_clarification': str(g.get('suggested_clarification', '')),
                    })

            scenarios = []
            for s in data.get('test_scenarios', []):
                if not isinstance(s, dict):
                    continue
                t = str(s.get('type', 'positive')).lower()
                if t not in ('positive', 'negative', 'edge'):
                    t = 'positive'
                scenarios.append({
                    'id': str(s.get('scenario_id', '')),
                    'requirement_ref': str(s.get('requirement_ref', 'REQ-001')),
                    'condition_ref': str(s.get('condition_ref', '')),
                    'description': str(s.get('description', '')),
                    'preconditions': str(s.get('preconditions', '')),
                    'steps': [],
                    'expected_result': str(s.get('expected_result', '')),
                    'priority': str(s.get('priority', 'Medium')),
                    'type': t,
                })

            return {
                'requirement_info': {
                    'requirement_id': str(req_info.get('requirement_id', 'REQ-001')),
                    'actors': list(req_info.get('actors', [])),
                    'actions': list(req_info.get('actions', [])),
                    'business_rules': list(req_info.get('business_rules', [])),
                    'constraints': list(req_info.get('constraints', [])),
                    'validation_rules': list(req_info.get('validation_rules', [])),
                    'error_handling': list(req_info.get('error_handling', [])),
                    'non_functional': list(req_info.get('non_functional', [])),
                },
                'quality_assessment': {
                    'clarity_score': clarity,
                    'completeness_score': completeness,
                    'testability_score': testability,
                    'overall_score': overall,
                    'severity': severity,
                    'positive_aspects': list(qa.get('positive_aspects', [])),
                    'warnings': list(qa.get('warnings', [])),
                },
                'test_conditions': conditions,
                'gaps': gaps,
                'test_scenarios': scenarios,
                'suggested_requirement': str(data.get('suggested_requirement', '')),
            }

        except (json.JSONDecodeError, KeyError, ValueError, AttributeError) as e:
            print(f"[QAAnalyzer] Parse error: {e}")
            return self._default_error()

    def _default_error(self) -> dict:
        return {
            'requirement_info': {
                'requirement_id': 'REQ-001',
                'actors': [], 'actions': [], 'business_rules': [],
                'constraints': [], 'validation_rules': [],
                'error_handling': [], 'non_functional': [],
            },
            'quality_assessment': {
                'clarity_score': 0, 'completeness_score': 0,
                'testability_score': 0, 'overall_score': 0,
                'severity': 'High', 'positive_aspects': [],
                'warnings': ['Could not analyze requirements. Please check your API key and try again.'],
            },
            'test_conditions': [],
            'gaps': [],
            'test_scenarios': [],
            'suggested_requirement': '',
        }
