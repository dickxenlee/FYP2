import json
from django.db import transaction
from core.models import (
    AnalysisSession, FeedbackItem,
    TestCondition, RequirementGap,
    TestScenario, DetailedTestCase,
)


class TrainingDataManager:
    """
    Saves all QA analysis data to the database (HITL persistence layer).
    """

    # ── Phase 3: comprehensive QA session save ────────────────────────────

    def save_qa_session(self, user, requirements_text: str,
                        qa_result: dict) -> AnalysisSession:
        """
        Saves a complete Phase 3 QA session — all six sections.
        Returns the saved AnalysisSession object.
        """
        requirements = qa_result.get('requirements', [])
        first_req_id = requirements[0]['requirement_id'] if requirements else 'REQ-001'
        qa = qa_result.get('quality_assessment', {})

        first_line = requirements_text.strip().split('\n')[0]
        title = first_line[:80] if first_line else 'Analysis Session'

        session = AnalysisSession.objects.create(
            user=user,
            title=title,
            requirements_text=requirements_text,
            suggested_requirement=qa_result.get('suggested_requirement', ''),
            accuracy_score=qa.get('overall_score', 0),
            requirement_id=first_req_id,
            extracted_info=json.dumps({'requirements': requirements}),
            clarity_score=qa.get('clarity_score', 0),
            completeness_score=qa.get('completeness_score', 0),
            testability_score=qa.get('testability_score', 0),
            severity=qa.get('severity', 'Medium'),
        )

        # Save positive aspects and warnings as FeedbackItems (used in PDF export)
        for msg in qa.get('positive_aspects', []):
            FeedbackItem.objects.create(
                session=session, feedback_type='positive', message=msg
            )
        for msg in qa.get('warnings', []):
            FeedbackItem.objects.create(
                session=session, feedback_type='warning', message=msg
            )

        # Save test conditions (Section 2)
        for c in qa_result.get('test_conditions', []):
            TestCondition.objects.create(
                session=session,
                condition_id=c.get('condition_id', ''),
                requirement_ref=c.get('requirement_ref', ''),
                description=c.get('description', ''),
                condition_type=c.get('type', 'Positive'),
                priority=c.get('priority', 'Medium'),
            )

        # Save requirement gaps (Section 4)
        for g in qa_result.get('gaps', []):
            RequirementGap.objects.create(
                session=session,
                issue_id=g.get('issue_id', ''),
                issue_type=g.get('issue_type', ''),
                description=g.get('description', ''),
                suggested_clarification=g.get('suggested_clarification', ''),
            )

        # Save test scenarios (Section 5)
        for s in qa_result.get('test_scenarios', []):
            TestScenario.objects.create(
                session=session,
                scenario_id=s.get('id', ''),
                requirement_ref=s.get('requirement_ref', ''),
                condition_ref=s.get('condition_ref', ''),
                description=s.get('description', ''),
                preconditions=s.get('preconditions', ''),
                steps_json=json.dumps(s.get('steps', [])),
                expected_result=s.get('expected_result', ''),
                scenario_type=s.get('type', 'positive'),
                priority=s.get('priority', 'Medium'),
            )

        return session

    def save_detailed_cases(self, session_id: int,
                            detailed_cases: list) -> None:
        """
        Saves or updates expanded detailed test cases for Section 6.
        Matches each case to its TestScenario by scenario_id string.
        """
        for case in detailed_cases:
            sid_str = case.get('scenario_id', '')
            try:
                scenario = TestScenario.objects.get(
                    session_id=session_id, scenario_id=sid_str
                )
                DetailedTestCase.objects.update_or_create(
                    scenario=scenario,
                    defaults={
                        'test_data': case.get('test_data', ''),
                        'steps_json': json.dumps(case.get('steps', [])),
                        'steps_done': '[]',  # reset checkboxes when (re)generated
                        'expected_results': case.get('expected_results', ''),
                        'postconditions': case.get('postconditions', ''),
                    },
                )
            except TestScenario.DoesNotExist:
                continue

    def reanalyze_session(self, session, qa_result: dict):
        """
        Re-runs a fresh QA analysis on an existing session.
        Deletes all old related data and replaces it with the new results.
        """
        with transaction.atomic():
            return self._reanalyze_session_inner(session, qa_result)

    def _reanalyze_session_inner(self, session, qa_result: dict):
        qa = qa_result['quality_assessment']
        requirements = qa_result.get('requirements', [])
        first_req_id = requirements[0]['requirement_id'] if requirements else 'REQ-001'

        session.accuracy_score = qa['overall_score']
        session.suggested_requirement = qa_result.get('suggested_requirement', '')
        session.requirement_id = first_req_id
        session.extracted_info = json.dumps({'requirements': requirements})
        session.clarity_score = qa['clarity_score']
        session.completeness_score = qa['completeness_score']
        session.testability_score = qa['testability_score']
        session.severity = qa['severity']
        session.save()

        session.feedback_items.all().delete()
        session.test_conditions.all().delete()
        session.gaps.all().delete()
        session.test_scenarios.all().delete()

        for msg in qa.get('positive_aspects', []):
            FeedbackItem.objects.create(session=session, feedback_type='positive', message=msg)
        for msg in qa.get('warnings', []):
            FeedbackItem.objects.create(session=session, feedback_type='warning', message=msg)
        for c in qa_result.get('test_conditions', []):
            TestCondition.objects.create(
                session=session,
                condition_id=c.get('condition_id', ''),
                requirement_ref=c.get('requirement_ref', ''),
                description=c.get('description', ''),
                condition_type=c.get('type', 'Positive'),
                priority=c.get('priority', 'Medium'),
            )
        for g in qa_result.get('gaps', []):
            RequirementGap.objects.create(
                session=session,
                issue_id=g.get('issue_id', ''),
                issue_type=g.get('issue_type', ''),
                description=g.get('description', ''),
                suggested_clarification=g.get('suggested_clarification', ''),
            )
        for s in qa_result.get('test_scenarios', []):
            TestScenario.objects.create(
                session=session,
                scenario_id=s.get('id', ''),
                requirement_ref=s.get('requirement_ref', ''),
                condition_ref=s.get('condition_ref', ''),
                description=s.get('description', ''),
                preconditions=s.get('preconditions', ''),
                steps_json=json.dumps(s.get('steps', [])),
                expected_result=s.get('expected_result', ''),
                scenario_type=s.get('type', 'positive'),
                priority=s.get('priority', 'Medium'),
            )
        return session
