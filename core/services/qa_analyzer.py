import re
import json
from concurrent.futures import ThreadPoolExecutor
from .gemini_service import GeminiService
from .text_preprocessor import TextPreprocessor

# Stage 1: extract and score the requirements (small, fast call).
EXTRACT_PROMPT = """
You are a senior Software Quality Assurance Engineer performing a professional requirements review.

Analyze the software requirement below and return a single JSON QA report.
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
  "gaps": [
    {{
      "issue_id": "G01",
      "issue_type": "<Ambiguity | Missing Rule | Incomplete | Contradiction | Non-Testable>",
      "description": "<what is missing or unclear>",
      "suggested_clarification": "<how the requirement writer should fix it>"
    }}
  ],
  "suggested_requirement": "<if overall_score < 80, rewrite the requirement so it fixes EVERY warning and gap listed above. Use 'The system shall...' format, replace vague words (fast, user-friendly, quickly) with measurable criteria, and state validation rules, error handling and boundaries explicitly. The rewrite must be complete enough to score at least 85 in clarity, completeness and testability if analysed again. If overall_score >= 80, return an empty string.>"
}}

Generation rules:
- Identify EVERY distinct requirement in the input. If the input describes several
  separate features (e.g. login AND password reset), create one entry per requirement:
  REQ-001, REQ-002, REQ-003, ... Each requirement gets its own analysis block.
- If the input is a single feature with many details, return just ONE requirement (REQ-001).
- Only include gaps that represent real issues — omit the array if the requirements are complete
- Give EACH requirement its own clarity_score, completeness_score, and testability_score (0-100).
- quality_assessment holds only the overall positive_aspects and warnings (document-level).
- Provide suggested_requirement if any requirement scores below 80 overall. The
  rewrite must directly resolve every gap and warning you reported, add the missing
  validation rules, error handling and measurable limits, and be self-contained so
  that re-analysing it would yield clarity, completeness and testability of 85+.
  Keep it focused on ONE coherent requirement: state the actor, the trigger/action,
  the exact system response, input validation, error handling, and one measurable
  acceptance criterion. Do NOT invent several unrelated features or expand scope —
  a single, precisely specified requirement scores higher than a broad vague one.

Requirement to analyze:
---
{requirements_text}
---
"""

# Stage 2: test conditions + scenarios for ONE requirement.
# Called once per requirement, in parallel, so big inputs stay fast.
SCENARIO_PROMPT = """
You are a senior Software Quality Assurance Engineer designing tests.

The full requirements document is shown below. Generate test conditions and
test scenarios for ONE requirement only: {req_id} ("{title}").

Return ONLY this JSON object. No markdown fences, no extra text.
{{
  "test_conditions": [
    {{
      "condition_id": "C01",
      "requirement_ref": "{req_id}",
      "description": "<concise testable condition, one sentence>",
      "type": "<Positive | Negative | Boundary | Security | Performance>",
      "priority": "<High | Medium | Low>"
    }}
  ],
  "test_scenarios": [
    {{
      "scenario_id": "TS-001",
      "requirement_ref": "{req_id}",
      "condition_ref": "C01",
      "description": "<concise scenario title — under 10 words>",
      "preconditions": "<system state required before test — one sentence>",
      "expected_result": "<expected outcome — one sentence>",
      "priority": "<High | Medium | Low>",
      "type": "<positive | negative | edge>"
    }}
  ]
}}

Rules:
- Generate 3 to 4 test_conditions covering Positive, Negative, and Boundary.
- Generate 3 to 4 test_scenarios — link each to its condition via condition_ref.
- Scenario descriptions must be concise — do NOT write step-by-step instructions.
- Cover ONLY {req_id}. Ignore the other requirements in the document.

Requirements document:
---
{requirements_text}
---
"""


class QAAnalyzer:
    """
    Two-stage QA analysis.
    Stage 1 (one small call): extract requirements, score them, find gaps,
    and suggest a rewrite if the input is weak.
    Stage 2 (one call per requirement, run in parallel): generate test
    conditions and test scenarios.
    Weak input stops after stage 1 — the user first chooses between their
    original text and the suggested rewrite, so no tokens are wasted
    generating scenarios that would be thrown away.
    """

    def __init__(self):
        self.llm_client = GeminiService()
        self.preprocessor = TextPreprocessor()

    def analyze(self, requirements_text: str, force_full: bool = False) -> dict:
        """
        Returns a dict with keys:
        requirements (list), quality_assessment, test_conditions, gaps,
        test_scenarios, suggested_requirement.
        If the input is weak (a rewrite was suggested) and force_full is
        False, test_conditions and test_scenarios are returned empty.
        """
        clean_text = self.preprocessor.clean(requirements_text)
        raw = self.llm_client.fetch_response(
            EXTRACT_PROMPT.format(requirements_text=clean_text)
        )
        result = self._parse(raw)

        # Weak input: stop here, let the user decide before spending tokens.
        if result['suggested_requirement'] and not force_full:
            return result

        # Stage 2 in parallel — one scenario call per requirement.
        with ThreadPoolExecutor(max_workers=4) as pool:
            parts = list(pool.map(
                lambda req: self._generate_for_requirement(clean_text, req),
                result['requirements'],
            ))

        # Merge the parts, renumbering ids so they stay unique across requirements.
        for part_conditions, part_scenarios in parts:
            id_map = {}
            for c in part_conditions:
                new_id = 'C{:02d}'.format(len(result['test_conditions']) + 1)
                id_map[c['condition_id']] = new_id
                c['condition_id'] = new_id
                result['test_conditions'].append(c)
            for s in part_scenarios:
                s['id'] = 'TS-{:03d}'.format(len(result['test_scenarios']) + 1)
                s['condition_ref'] = id_map.get(s['condition_ref'], s['condition_ref'])
                result['test_scenarios'].append(s)
        return result

    def _generate_for_requirement(self, clean_text: str, req: dict):
        """One stage-2 call: conditions + scenarios for a single requirement."""
        req_id = req['requirement_id']
        prompt = SCENARIO_PROMPT.format(
            req_id=req_id, title=req['title'], requirements_text=clean_text
        )
        raw = self.llm_client.fetch_response(prompt)
        try:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            data = json.loads(match.group() if match else raw)
        except (json.JSONDecodeError, TypeError, AttributeError):
            return [], []
        conditions = self._condition_list(data, req_id)
        scenarios = self._scenario_list(data, req_id)
        for c in conditions:
            c['requirement_ref'] = req_id
        for s in scenarios:
            s['requirement_ref'] = req_id
        return conditions, scenarios

    def _condition_list(self, data: dict, default_ref: str) -> list:
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
        return conditions

    def _scenario_list(self, data: dict, default_ref: str) -> list:
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
        return scenarios

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

            gaps = []
            for g in data.get('gaps', []):
                if isinstance(g, dict):
                    gaps.append({
                        'issue_id': str(g.get('issue_id', '')),
                        'issue_type': str(g.get('issue_type', '')),
                        'description': str(g.get('description', '')),
                        'suggested_clarification': str(g.get('suggested_clarification', '')),
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
                'test_conditions': self._condition_list(data, default_ref),
                'gaps': gaps,
                'test_scenarios': self._scenario_list(data, default_ref),
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
