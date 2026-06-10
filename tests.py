import json

from django.test import TestCase
from django.contrib.auth.models import User

from .models import Workspace, WorkspaceMembership, AnalysisSession, TestScenario


class WorkspaceMembershipTests(TestCase):
    """Owner-only rules for renaming, adding/removing members, and deleting."""

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

    def test_member_cannot_rename(self):
        self.client.force_login(self.member)
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

    def test_member_cannot_add(self):
        self.client.force_login(self.member)
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

    def test_member_cannot_delete_workspace(self):
        self.client.force_login(self.member)
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
        r = self.client.post('/register/', {'username': 'carol', 'email': 'carol@example.com', 'password': 'Str0ng!Pass99'})
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
