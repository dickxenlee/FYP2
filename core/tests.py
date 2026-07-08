import json
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase
from django.contrib.auth.models import User

from .services.qa_analyzer import QAAnalyzer
from .services.text_preprocessor import TextPreprocessor
from .models import (
    Workspace, WorkspaceMembership, AnalysisSession, TestScenario,
    DetailedTestCase, WorkspaceDraftInput,
)


class WorkspaceMembershipTests(TestCase):
    """Any member can rename, add/remove members, and delete; outsiders are blocked."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', '', 'pw')
        self.member = User.objects.create_user('member', '', 'pw')
        self.outsider = User.objects.create_user('outsider', '', 'pw')

        self.ws = Workspace.objects.create(name='Team', owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.owner, role='owner')
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.member, role='member')

    def post(self, url, payload):
        return self.client.post(url, json.dumps(payload), content_type='application/json')

    # ── rename ───────────────────────────────────────────────
    def test_owner_can_rename(self):
        self.client.force_login(self.owner)
        r = self.post('/rename_workspace/', {'workspace_id': self.ws.workspace_id, 'name': 'New'})
        self.assertEqual(r.status_code, 200)
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.name, 'New')

    def test_member_can_rename(self):
        self.client.force_login(self.member)
        r = self.post('/rename_workspace/', {'workspace_id': self.ws.workspace_id, 'name': 'New name'})
        self.assertEqual(r.status_code, 200)
        self.ws.refresh_from_db()
        self.assertEqual(self.ws.name, 'New name')

    def test_outsider_cannot_rename(self):
        self.client.force_login(self.outsider)
        r = self.post('/rename_workspace/', {'workspace_id': self.ws.workspace_id, 'name': 'Hack'})
        self.assertEqual(r.status_code, 403)

    # ── add member ───────────────────────────────────────────
    def test_owner_adds_member_case_insensitive(self):
        self.client.force_login(self.owner)
        r = self.post('/add_member/', {'workspace_id': self.ws.workspace_id, 'username': 'OUTSIDER'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(WorkspaceMembership.objects.filter(workspace=self.ws, user=self.outsider).exists())

    def test_add_unknown_user_404(self):
        self.client.force_login(self.owner)
        r = self.post('/add_member/', {'workspace_id': self.ws.workspace_id, 'username': 'ghost'})
        self.assertEqual(r.status_code, 404)

    def test_add_existing_member_400(self):
        self.client.force_login(self.owner)
        r = self.post('/add_member/', {'workspace_id': self.ws.workspace_id, 'username': 'member'})
        self.assertEqual(r.status_code, 400)

    def test_member_can_add(self):
        self.client.force_login(self.member)
        r = self.post('/add_member/', {'workspace_id': self.ws.workspace_id, 'username': 'outsider'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(WorkspaceMembership.objects.filter(workspace=self.ws, user=self.outsider).exists())

    def test_outsider_cannot_add(self):
        stranger = User.objects.create_user('stranger', '', 'pw')
        self.client.force_login(stranger)
        r = self.post('/add_member/', {'workspace_id': self.ws.workspace_id, 'username': 'outsider'})
        self.assertEqual(r.status_code, 403)

    # ── remove member ────────────────────────────────────────
    def test_owner_removes_member(self):
        self.client.force_login(self.owner)
        r = self.post('/remove_member/', {'workspace_id': self.ws.workspace_id, 'username': 'member'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(WorkspaceMembership.objects.filter(workspace=self.ws, user=self.member).exists())

    def test_cannot_remove_owner(self):
        self.client.force_login(self.owner)
        r = self.post('/remove_member/', {'workspace_id': self.ws.workspace_id, 'username': 'owner'})
        self.assertEqual(r.status_code, 400)

    # ── leave ────────────────────────────────────────────────
    def test_member_can_leave(self):
        self.client.force_login(self.member)
        r = self.post('/leave_workspace/', {'workspace_id': self.ws.workspace_id})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(WorkspaceMembership.objects.filter(workspace=self.ws, user=self.member).exists())

    # ── delete workspace (cascade) ───────────────────────────
    def test_owner_deletes_workspace_and_chats(self):
        session = AnalysisSession.objects.create(
            user=self.member, workspace=self.ws, title='c', requirements_text='r'
        )
        TestScenario.objects.create(
            session=session, scenario_id='TS1', description='d',
            preconditions='p', steps_json='[]', expected_result='e',
        )
        self.client.force_login(self.owner)
        r = self.post('/delete_workspace/', {'workspace_id': self.ws.workspace_id})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Workspace.objects.filter(pk=self.ws.pk).exists())
        self.assertFalse(AnalysisSession.objects.filter(pk=session.pk).exists())
        self.assertFalse(TestScenario.objects.filter(session_id=session.pk).exists())

    def test_member_can_delete_workspace(self):
        self.client.force_login(self.member)
        r = self.post('/delete_workspace/', {'workspace_id': self.ws.workspace_id})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Workspace.objects.filter(pk=self.ws.pk).exists())

    def test_outsider_cannot_delete_workspace(self):
        self.client.force_login(self.outsider)
        r = self.post('/delete_workspace/', {'workspace_id': self.ws.workspace_id})
        self.assertEqual(r.status_code, 403)


class AuthTests(TestCase):
    """Email-or-username login and strong-password enforcement."""

    def setUp(self):
        self.user = User.objects.create_user('alice', 'alice@example.com', 'Str0ng!Pass99')

    def test_login_with_username(self):
        r = self.client.post('/login/', {'username': 'alice', 'password': 'Str0ng!Pass99'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, '/workspace/')

    def test_login_with_email(self):
        r = self.client.post('/login/', {'username': 'alice@example.com', 'password': 'Str0ng!Pass99'})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.url, '/workspace/')

    def test_login_wrong_password_fails(self):
        r = self.client.post('/login/', {'username': 'alice', 'password': 'nope'})
        self.assertEqual(r.status_code, 200)  # re-rendered form, not redirected

    def test_register_rejects_weak_password(self):
        r = self.client.post('/register/', {'username': 'bob', 'email': 'bob@example.com', 'password': '1'})
        self.assertEqual(r.status_code, 200)  # form errors, no redirect
        self.assertFalse(User.objects.filter(username='bob').exists())

    def test_register_accepts_strong_password(self):
        r = self.client.post('/register/', {'username': 'carol', 'email': 'carol@example.com',
                                            'password': 'Str0ng!Pass99', 'confirm_password': 'Str0ng!Pass99'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username='carol').exists())


class TeamChatDeleteTests(TestCase):
    """Only the workspace owner can delete a team chat."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', '', 'pw')
        self.member = User.objects.create_user('member', '', 'pw')
        self.ws = Workspace.objects.create(name='Team', owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.owner, role='owner')
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.member, role='member')
        self.session = AnalysisSession.objects.create(
            user=self.member, workspace=self.ws, title='c', requirements_text='r'
        )

    def post(self, url, payload):
        return self.client.post(url, json.dumps(payload), content_type='application/json')

    def test_member_cannot_delete_team_chat(self):
        self.client.force_login(self.member)
        r = self.post('/delete_current_chat/', {'session_id': self.session.id})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(AnalysisSession.objects.filter(pk=self.session.pk).exists())

    def test_owner_can_delete_team_chat(self):
        self.client.force_login(self.owner)
        r = self.post('/delete_current_chat/', {'session_id': self.session.id})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(AnalysisSession.objects.filter(pk=self.session.pk).exists())

    def test_deleting_missing_chat_returns_json_success(self):
        # Deleting an already-gone chat must return JSON (not an HTML 404 page)
        # so the browser never hits "Unexpected token '<'".
        self.client.force_login(self.owner)
        r = self.post('/delete_current_chat/', {'session_id': 999999})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/json')
        self.assertEqual(r.json()['system_action'], 'chat_deleted')


class StepDoneTests(TestCase):
    """Per-step 'done' checkbox on detailed test cases (saved & shared)."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', '', 'pw')
        self.member = User.objects.create_user('member', '', 'pw')
        self.outsider = User.objects.create_user('outsider', '', 'pw')
        self.ws = Workspace.objects.create(name='Team', owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.owner, role='owner')
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.member, role='member')
        self.session = AnalysisSession.objects.create(
            user=self.owner, workspace=self.ws, title='c', requirements_text='r'
        )
        self.scenario = TestScenario.objects.create(
            session=self.session, scenario_id='TS1', description='d',
            preconditions='p', steps_json='[]', expected_result='e',
        )
        self.case = DetailedTestCase.objects.create(
            scenario=self.scenario, steps_json='["a", "b", "c"]', steps_done='[]'
        )

    def post(self, payload):
        import json as _json
        self.client.force_login(self._actor)
        return self.client.post('/toggle_step_done/', _json.dumps(payload),
                                content_type='application/json')

    def test_member_can_toggle_and_it_persists(self):
        self._actor = self.member
        r = self.post({'case_id': self.case.id, 'step_index': 1})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['steps_done'], [False, True, False])
        self.assertEqual(body['done_count'], 1)
        self.case.refresh_from_db()
        self.assertEqual(self.case.get_steps_done(), [False, True, False])

    def test_toggle_off_again(self):
        self._actor = self.owner
        self.post({'case_id': self.case.id, 'step_index': 0})
        r = self.post({'case_id': self.case.id, 'step_index': 0})
        self.assertEqual(r.json()['steps_done'], [False, False, False])

    def test_out_of_range_rejected(self):
        self._actor = self.owner
        r = self.post({'case_id': self.case.id, 'step_index': 9})
        self.assertEqual(r.status_code, 400)

    def test_outsider_denied(self):
        self._actor = self.outsider
        r = self.post({'case_id': self.case.id, 'step_index': 0})
        self.assertEqual(r.status_code, 403)

    def test_scenario_done_toggle_persists(self):
        import json as _json
        self.client.force_login(self.member)
        r = self.client.post('/toggle_scenario_done/', _json.dumps({'db_id': self.scenario.id}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['is_done'])
        self.scenario.refresh_from_db()
        self.assertTrue(self.scenario.is_done)

    def test_scenario_done_outsider_denied(self):
        import json as _json
        self.client.force_login(self.outsider)
        r = self.client.post('/toggle_scenario_done/', _json.dumps({'db_id': self.scenario.id}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 403)


class TeamDraftTests(TestCase):
    """Members contribute input; only the owner generates; inputs kept after."""

    def setUp(self):
        self.owner = User.objects.create_user('owner', '', 'pw')
        self.member = User.objects.create_user('member', '', 'pw')
        self.outsider = User.objects.create_user('outsider', '', 'pw')
        self.ws = Workspace.objects.create(name='Team', owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.owner, role='owner')
        WorkspaceMembership.objects.create(workspace=self.ws, user=self.member, role='member')
        self.wid = self.ws.workspace_id

    def post(self, url, payload):
        import json as _json
        return self.client.post(url, _json.dumps(payload), content_type='application/json')

    def test_member_saves_draft_and_list_shows_it(self):
        self.client.force_login(self.member)
        r = self.post(f'/workspace/{self.wid}/draft/save/', {'text': 'login feature'})
        self.assertEqual(r.status_code, 200)
        r = self.client.get(f'/workspace/{self.wid}/draft/')
        data = r.json()
        self.assertFalse(data['is_owner'])
        self.assertEqual([i['text'] for i in data['inputs'] if i['is_me']], ['login feature'])

    def test_outsider_cannot_see_draft(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(f'/workspace/{self.wid}/draft/').status_code, 404)

    def test_member_can_generate_but_empty_rejected(self):
        # A member is allowed (not 403); empty input is rejected with 400.
        self.client.force_login(self.member)
        r = self.post(f'/workspace/{self.wid}/draft/generate/', {})
        self.assertEqual(r.status_code, 400)

    def test_outsider_cannot_generate(self):
        self.client.force_login(self.outsider)
        r = self.post(f'/workspace/{self.wid}/draft/generate/', {})
        self.assertEqual(r.status_code, 404)

    def test_generate_empty_rejected(self):
        self.client.force_login(self.owner)
        r = self.post(f'/workspace/{self.wid}/draft/generate/', {})
        self.assertEqual(r.status_code, 400)

    def test_member_can_edit_another_members_input(self):
        WorkspaceDraftInput.objects.create(workspace=self.ws, user=self.owner, text='orig')
        self.client.force_login(self.member)
        r = self.post(f'/workspace/{self.wid}/draft/save/', {'username': 'owner', 'text': 'edited by member'})
        self.assertEqual(r.status_code, 200)
        d = WorkspaceDraftInput.objects.get(workspace=self.ws, user=self.owner)
        self.assertEqual(d.text, 'edited by member')

    def test_cannot_edit_nonmember_draft(self):
        self.client.force_login(self.member)
        r = self.post(f'/workspace/{self.wid}/draft/save/', {'username': 'outsider', 'text': 'x'})
        self.assertEqual(r.status_code, 404)


class QAParserTests(SimpleTestCase):
    """The QAAnalyzer JSON parser — the riskiest code if Gemini's output drifts.
    These run without the database or any network call."""

    def parse(self, payload):
        return QAAnalyzer()._parse(json.dumps(payload))

    def test_multi_requirement_scores_and_average(self):
        result = self.parse({
            'requirements': [
                {'requirement_id': 'REQ-001', 'title': 'Login',
                 'clarity_score': 90, 'completeness_score': 80, 'testability_score': 70},
                {'requirement_id': 'REQ-002', 'title': 'Reset',
                 'clarity_score': 60, 'completeness_score': 50, 'testability_score': 40},
            ],
            'quality_assessment': {'positive_aspects': ['clear'], 'warnings': ['vague']},
            'test_conditions': [], 'gaps': [], 'test_scenarios': [], 'suggested_requirement': '',
        })
        reqs = result['requirements']
        self.assertEqual(len(reqs), 2)
        # per-requirement overall = average of its three scores
        self.assertEqual(reqs[0]['overall_score'], 80)   # (90+80+70)/3
        self.assertEqual(reqs[0]['severity'], 'Low')
        self.assertEqual(reqs[1]['overall_score'], 50)   # (60+50+40)/3
        self.assertEqual(reqs[1]['severity'], 'High')
        # document-level scores = average across requirements
        qa = result['quality_assessment']
        self.assertEqual(qa['overall_score'], 65)        # (80+50)/2
        self.assertEqual(qa['severity'], 'Medium')
        self.assertEqual(qa['positive_aspects'], ['clear'])

    def test_condition_and_scenario_refs_default_to_first_requirement(self):
        result = self.parse({
            'requirements': [{'requirement_id': 'REQ-001', 'clarity_score': 80,
                              'completeness_score': 80, 'testability_score': 80}],
            'quality_assessment': {},
            'test_conditions': [{'condition_id': 'C01', 'description': 'x', 'type': 'Positive', 'priority': 'High'}],
            'test_scenarios': [{'scenario_id': 'TS-001', 'condition_ref': 'C01', 'description': 'y'}],
            'gaps': [], 'suggested_requirement': '',
        })
        self.assertEqual(result['test_conditions'][0]['requirement_ref'], 'REQ-001')
        self.assertEqual(result['test_scenarios'][0]['requirement_ref'], 'REQ-001')

    def test_backward_compat_single_requirement_info(self):
        # Old Gemini format used "requirement_info" (a single object).
        result = self.parse({
            'requirement_info': {'requirement_id': 'REQ-001', 'actors': ['user']},
            'quality_assessment': {}, 'test_conditions': [], 'gaps': [],
            'test_scenarios': [], 'suggested_requirement': '',
        })
        self.assertEqual(len(result['requirements']), 1)
        self.assertEqual(result['requirements'][0]['requirement_id'], 'REQ-001')

    def test_empty_response_returns_safe_default(self):
        result = QAAnalyzer()._parse('')
        self.assertEqual(len(result['requirements']), 1)
        self.assertEqual(result['quality_assessment']['overall_score'], 0)

    def test_garbage_response_returns_safe_default(self):
        result = QAAnalyzer()._parse('not json at all {oops')
        self.assertEqual(len(result['requirements']), 1)
        self.assertTrue(result['quality_assessment']['warnings'])


class FakeLLM:
    """Stands in for GeminiService: replies based on which prompt it receives."""

    def __init__(self, extract_reply, scenario_replies=None):
        self.extract_reply = extract_reply
        self.scenario_replies = scenario_replies or {}
        self.prompts = []

    def fetch_response(self, prompt):
        self.prompts.append(prompt)
        for req_id, reply in self.scenario_replies.items():
            if 'ONE requirement only: ' + req_id in prompt:
                return reply
        return self.extract_reply


def _scenario_reply(req_id):
    """A stage-2 reply with two conditions and two scenarios (local ids)."""
    return json.dumps({
        'test_conditions': [
            {'condition_id': 'C01', 'requirement_ref': req_id,
             'description': 'valid input accepted', 'type': 'Positive', 'priority': 'High'},
            {'condition_id': 'C02', 'requirement_ref': req_id,
             'description': 'invalid input rejected', 'type': 'Negative', 'priority': 'Medium'},
        ],
        'test_scenarios': [
            {'scenario_id': 'TS-001', 'requirement_ref': req_id, 'condition_ref': 'C01',
             'description': 'happy path', 'preconditions': 'x', 'expected_result': 'ok',
             'priority': 'High', 'type': 'positive'},
            {'scenario_id': 'TS-002', 'requirement_ref': req_id, 'condition_ref': 'C02',
             'description': 'error path', 'preconditions': 'x', 'expected_result': 'error',
             'priority': 'Medium', 'type': 'negative'},
        ],
    })


class TwoStageAnalyzerTests(SimpleTestCase):
    """The two-stage analyze flow: weak input stops early to save tokens,
    strong input generates scenarios per requirement in parallel."""

    WEAK_EXTRACT = json.dumps({
        'requirements': [{'requirement_id': 'REQ-001', 'title': 'Vague thing',
                          'clarity_score': 30, 'completeness_score': 30, 'testability_score': 30}],
        'quality_assessment': {'positive_aspects': [], 'warnings': ['too vague']},
        'gaps': [],
        'suggested_requirement': 'The system shall respond within 2 seconds.',
    })

    STRONG_EXTRACT = json.dumps({
        'requirements': [
            {'requirement_id': 'REQ-001', 'title': 'Login',
             'clarity_score': 90, 'completeness_score': 90, 'testability_score': 90},
            {'requirement_id': 'REQ-002', 'title': 'Fine payment',
             'clarity_score': 85, 'completeness_score': 85, 'testability_score': 85},
        ],
        'quality_assessment': {'positive_aspects': ['clear'], 'warnings': []},
        'gaps': [],
        'suggested_requirement': '',
    })

    def analyzer_with(self, fake):
        analyzer = QAAnalyzer()
        analyzer.llm_client = fake
        return analyzer

    def test_weak_input_stops_after_one_call(self):
        fake = FakeLLM(self.WEAK_EXTRACT)
        result = self.analyzer_with(fake).analyze('be fast and easy')
        self.assertEqual(len(fake.prompts), 1)
        self.assertEqual(result['test_conditions'], [])
        self.assertEqual(result['test_scenarios'], [])
        self.assertTrue(result['suggested_requirement'])

    def test_weak_input_force_full_generates_scenarios(self):
        fake = FakeLLM(self.WEAK_EXTRACT, {'REQ-001': _scenario_reply('REQ-001')})
        result = self.analyzer_with(fake).analyze('be fast and easy', force_full=True)
        self.assertEqual(len(fake.prompts), 2)   # extract + one scenario call
        self.assertEqual(len(result['test_scenarios']), 2)

    def test_strong_input_generates_per_requirement_and_merges_ids(self):
        fake = FakeLLM(self.STRONG_EXTRACT, {
            'REQ-001': _scenario_reply('REQ-001'),
            'REQ-002': _scenario_reply('REQ-002'),
        })
        result = self.analyzer_with(fake).analyze('login and fine payment')
        self.assertEqual(len(fake.prompts), 3)   # extract + 2 parallel scenario calls
        # The full input text is sent ONCE (extract only) — stage-2 calls
        # carry just their own requirement's details, saving input tokens.
        scenario_prompts = [p for p in fake.prompts if 'ONE requirement only' in p]
        self.assertEqual(len(scenario_prompts), 2)
        for p in scenario_prompts:
            self.assertNotIn('login and fine payment', p)
        conditions, scenarios = result['test_conditions'], result['test_scenarios']
        self.assertEqual([c['condition_id'] for c in conditions], ['C01', 'C02', 'C03', 'C04'])
        self.assertEqual([s['id'] for s in scenarios], ['TS-001', 'TS-002', 'TS-003', 'TS-004'])
        # REQ-002's local C01 must be remapped to its merged id C03
        self.assertEqual(scenarios[2]['requirement_ref'], 'REQ-002')
        self.assertEqual(scenarios[2]['condition_ref'], 'C03')

    def test_broken_scenario_reply_gives_empty_lists_not_crash(self):
        fake = FakeLLM(self.STRONG_EXTRACT, {
            'REQ-001': 'not json {oops',
            'REQ-002': _scenario_reply('REQ-002'),
        })
        result = self.analyzer_with(fake).analyze('login and fine payment')
        # REQ-001's broken reply is skipped; REQ-002 still comes through
        self.assertEqual(len(result['test_scenarios']), 2)
        self.assertEqual(result['test_scenarios'][0]['requirement_ref'], 'REQ-002')

    def test_generate_scenarios_only_skips_the_extract_call(self):
        # No extract_reply needed — this must never send the EXTRACT_PROMPT.
        fake = FakeLLM('SHOULD NOT BE USED', {'REQ-001': _scenario_reply('REQ-001')})
        already_scored = [{'requirement_id': 'REQ-001', 'title': 'Speed',
                            'clarity_score': 30, 'completeness_score': 30,
                            'testability_score': 30, 'overall_score': 30, 'severity': 'High'}]
        result = self.analyzer_with(fake).generate_scenarios_only(already_scored)
        self.assertEqual(len(fake.prompts), 1)   # only the scenario call, no extract
        self.assertEqual(len(result['test_scenarios']), 2)
        self.assertEqual(result['requirements'], already_scored)


class KeepOriginalViewTests(TestCase):
    """POST /analyze/ with keep_session_id fills in scenarios for the
    already-saved weak session (the 'use my original input' button)."""

    def setUp(self):
        self.user = User.objects.create_user('dick', '', 'pw')
        self.client.force_login(self.user)
        saved_requirements = [{'requirement_id': 'REQ-001', 'title': 'Speed',
                               'clarity_score': 30, 'completeness_score': 30,
                               'testability_score': 30, 'overall_score': 30, 'severity': 'High'}]
        self.session = AnalysisSession.objects.create(
            user=self.user, title='weak', requirements_text='be fast',
            accuracy_score=30, requirement_id='REQ-001',
            extracted_info=json.dumps({'requirements': saved_requirements}),
        )
        self.saved_requirements = saved_requirements

    def test_keep_original_skips_reextraction_and_generates_scenarios(self):
        full_result = {
            'requirements': self.saved_requirements,
            'quality_assessment': {'clarity_score': 30, 'completeness_score': 30,
                                   'testability_score': 30, 'overall_score': 30,
                                   'severity': 'High', 'positive_aspects': [], 'warnings': ['vague']},
            'test_conditions': [],
            'gaps': [],
            'test_scenarios': [{'id': 'TS-001', 'requirement_ref': 'REQ-001',
                                'condition_ref': 'C01', 'description': 'd', 'preconditions': 'p',
                                'steps': [], 'expected_result': 'e', 'priority': 'High',
                                'type': 'positive'}],
            'suggested_requirement': '',
        }
        with patch('core.views.QAAnalyzer') as MockAnalyzer:
            MockAnalyzer.return_value.generate_scenarios_only.return_value = full_result
            r = self.client.post('/analyze/',
                                 json.dumps({'keep_session_id': self.session.id}),
                                 content_type='application/json')
            self.assertEqual(r.status_code, 200)
            # Stage 1 (extract) must NOT be called again — only stage 2.
            MockAnalyzer.return_value.analyze.assert_not_called()
            MockAnalyzer.return_value.generate_scenarios_only.assert_called_once_with(
                self.saved_requirements)
        self.assertEqual(self.session.test_scenarios.count(), 1)

    def test_keep_original_other_users_session_denied(self):
        other = User.objects.create_user('other', '', 'pw')
        self.client.force_login(other)
        r = self.client.post('/analyze/',
                             json.dumps({'keep_session_id': self.session.id}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 404)


class MeaningfulInputTests(SimpleTestCase):
    """The guard that blocks junk input (like '.') before it reaches the AI."""

    def test_junk_is_rejected(self):
        from core.views import _is_meaningful_requirement
        self.assertFalse(_is_meaningful_requirement('.'))
        self.assertFalse(_is_meaningful_requirement('abc'))
        self.assertFalse(_is_meaningful_requirement('12345'))
        self.assertFalse(_is_meaningful_requirement('   '))

    def test_real_requirement_is_accepted(self):
        from core.views import _is_meaningful_requirement
        self.assertTrue(_is_meaningful_requirement('The system shall let a user log in.'))
        self.assertTrue(_is_meaningful_requirement('be fast and easy to use'))


class AnalyzeInputValidationTests(TestCase):
    """POST /analyze/ rejects meaningless input with 400 before calling the AI."""

    def setUp(self):
        self.user = User.objects.create_user('vi', '', 'pw')
        self.client.force_login(self.user)

    def test_dot_input_rejected(self):
        r = self.client.post('/analyze/', json.dumps({'requirements_text': '.'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)

    def test_short_junk_rejected(self):
        r = self.client.post('/analyze/', json.dumps({'requirements_text': 'abc'}),
                             content_type='application/json')
        self.assertEqual(r.status_code, 400)


class TextPreprocessorTests(SimpleTestCase):
    """The NLP text-normalization step applied before the LLM analysis."""

    def setUp(self):
        self.pre = TextPreprocessor()

    def test_empty_input(self):
        self.assertEqual(self.pre.clean(''), '')

    def test_collapses_whitespace_and_blank_lines(self):
        out = self.pre.clean('The   system    shall   log   in.\n\n\n\nIt is fast.')
        self.assertEqual(out, 'The system shall log in.\n\nIt is fast.')

    def test_strips_markdown_markers_at_line_start(self):
        out = self.pre.clean('# Heading\n- bullet point\n> quote')
        self.assertEqual(out, 'Heading\nbullet point\nquote')

    def test_normalizes_unicode_smart_quotes(self):
        # smart quotes / full-width chars become plain equivalents
        out = self.pre.clean('“Login” must be Ｔested')
        self.assertEqual(out, '"Login" must be Tested')

    def test_removes_zero_width_characters(self):
        out = self.pre.clean('pass​word')
        self.assertEqual(out, 'password')
