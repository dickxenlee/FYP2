import re
import json
from .gemini_service import GeminiService
from .text_preprocessor import TextPreprocessor

QA_ANALYSIS_PROMPT = """
You are a senior Software Quality Assurance Engineer performing a professional requirements review.

Analyze the software requirement below and return a single comprehensive JSON QA report.
Return ONLY the JSON object. No markdown fences, no extra text before or after.

Required JSON format:
{{
  "requirements": [
    {{
      "requirement_id": "REQ-001",
      "title": "<short name of this requirement, under 8 words>",
      "clarity_score": <integer 0-100 for THIS requirement>,
      "completeness_score": <integer 0-100 for THIS requirement>,
      "testability_score": <integer 0-100 for THIS requirement>,
      "actors": ["list of actors or users"],
      "actions": ["list of actions the system or actor performs"],
      "business_rules": ["list of business rules"],
      "constraints": ["list of constraints such as formats, limits"],
      "validation_rules": ["list of input validation rules"],
      "error_handling": ["list of error handling requirements"],
      "non_functional": ["list of non-functional requirements, e.g. performance, security"]
    }}
  ],
  "quality_assessment": {{
    "positive_aspects": ["what is well-defined across the requirements"],
    "warnings": ["what is ambiguous, missing, or hard to test"]
  }},
  "test_conditions": [
    {{
      "condition_id": "C01",
      "requirement_ref": "REQ-001",
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
- Identify EVERY distinct requirement in the input. If the input describes several
  separate features (e.g. login AND password reset), create one entry per requirement:
  REQ-001, REQ-002, REQ-003, ... Each requirement gets its own analysis block.
- If the input is a single feature with many details, return just ONE requirement (REQ-001).
- Every test_condition MUST set requirement_ref to the requirement it tests.
- Every test_scenario MUST set requirement_ref (its requirement) and condition_ref (its condition).
- Generate 3 to 6 test_conditions PER requirement, covering Positive, Negative, and Boundary.
- Generate 3 to 6 test_scenarios PER requirement — link each to its condition via condition_ref.
- Scenario descriptions must be concise — do NOT write step-by-step instructions
- Only include gaps that represent real issues — omit the array if the requirements are complete
- Give EACH requirement its own clarity_score, completeness_score, and testability_score (0-100).
- quality_assessment holds only the overall positive_aspects and warnings (document-level).
- Provide suggested_requirement if any requirement scores below 80 overall.

Example: input describing login AND password reset →
requirements = [REQ-001 "User Login", REQ-002 "Password Reset"]
test_conditions: C01 (ref REQ-001), C02 (ref REQ-001), C04 (ref REQ-002), ...
test_scenarios: TS-001 (ref REQ-001, cond C01), TS-004 (ref REQ-002, cond C04), ...

Requirement to analyze:
---
{requirements_text}
---
"""


class QAAnalyzer:
    """
    Single comprehensive LLM call that returns the full QA report:
    requirement extraction, quality scores, test conditions, gaps, and test scenarios.
    """

    def __init__(self):
        self.llm_client = GeminiService()
        self.preprocessor = TextPreprocessor()

    def analyze(self, requirements_text: str) -> dict:
        """
        Returns a dict with keys:
        requirements (list), quality_assessment, test_conditions, gaps,
        test_scenarios, suggested_requirement.
        """
        clean_text = self.preprocessor.clean(requirements_text)
        prompt = QA_ANALYSIS_PROMPT.format(requirements_text=clean_text)
        raw = self.llm_client.fetch_response(prompt)
        return self._parse(raw)

    def _parse(self, raw: str) -> dict:
        if not raw:
            return self._default_error()

        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group() if match else raw)

            # Support both the new list format and the old single-requirement format.
            raw_reqs = data.get('requirements')
            if not isinstance(raw_reqs, list) or not raw_reqs:
                single = data.get('requirement_info')
                raw_reqs = [single] if isinstance(single, dict) else []

            def clamp(v, default=50):
                try:
                    return max(0, min(100, int(v)))
                except (ValueError, TypeError):
                    return default

            def sev(score):
                return 'Low' if score >= 80 else 'Medium' if score >= 60 else 'High'

            requirements = []
            for i, r in enumerate(raw_reqs):
                if not isinstance(r, dict):
                    continue
                rc, rco, rt = clamp(r.get('clarity_score')), clamp(r.get('completeness_score')), clamp(r.get('testability_score'))
                rov = round((rc + rco + rt) / 3)
                requirements.append({
                    'requirement_id': str(r.get('requirement_id', f'REQ-{i+1:03d}')),
                    'title': str(r.get('title', '')),
                    'clarity_score': rc,
                    'completeness_score': rco,
                    'testability_score': rt,
                    'overall_score': rov,
                    'severity': sev(rov),
                    'actors': list(r.get('actors', [])),
                    'actions': list(r.get('actions', [])),
                    'business_rules': list(r.get('business_rules', [])),
                    'constraints': list(r.get('constraints', [])),
                    'validation_rules': list(r.get('validation_rules', [])),
                    'error_handling': list(r.get('error_handling', [])),
                    'non_functional': list(r.get('non_functional', [])),
                })
            if not requirements:
                requirements = [{'requirement_id': 'REQ-001', 'title': '',
                                 'clarity_score': 0, 'completeness_score': 0, 'testability_score': 0,
                                 'overall_score': 0, 'severity': 'High',
                                 'actors': [], 'actions': [], 'business_rules': [], 'constraints': [],
                                 'validation_rules': [], 'error_handling': [], 'non_functional': []}]

            qa = data.get('quality_assessment', {})

            # Document-level scores are the average of the per-requirement scores.
            n = len(requirements)
            clarity = round(sum(r['clarity_score'] for r in requirements) / n)
            completeness = round(sum(r['completeness_score'] for r in requirements) / n)
            testability = round(sum(r['testability_score'] for r in requirements) / n)
            overall = round(sum(r['overall_score'] for r in requirements) / n)
            severity = sev(overall)

            default_ref = requirements[0]['requirement_id']
            conditions = []
            for c in data.get('test_conditions', []):
                if isinstance(c, dict):
                    conditions.append({
                        'condition_id': str(c.get('condition_id', '')),
                        'requirement_ref': str(c.get('requirement_ref', default_ref)),
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
                    'requirement_ref': str(s.get('requirement_ref', default_ref)),
                    'condition_ref': str(s.get('condition_ref', '')),
                    'description': str(s.get('description', '')),
                    'preconditions': str(s.get('preconditions', '')),
                    'steps': [],
                    'expected_result': str(s.get('expected_result', '')),
                    'priority': str(s.get('priority', 'Medium')),
                    'type': t,
                })

            return {
                'requirements': requirements,
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
            'requirements': [{
                'requirement_id': 'REQ-001', 'title': '',
                'clarity_score': 0, 'completeness_score': 0, 'testability_score': 0,
                'overall_score': 0, 'severity': 'High',
                'actors': [], 'actions': [], 'business_rules': [],
                'constraints': [], 'validation_rules': [],
                'error_handling': [], 'non_functional': [],
            }],
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
