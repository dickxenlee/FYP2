import json
import random
import string
from django.db import models
from django.contrib.auth.models import User


class Workspace(models.Model):
    workspace_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200, default='Team Workspace')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_workspaces')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.workspace_id:
            while True:
                candidate = 'WS-' + ''.join(random.choices(string.digits, k=3))
                if not Workspace.objects.filter(workspace_id=candidate).exists():
                    self.workspace_id = candidate
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.workspace_id}: {self.name}'


class WorkspaceMembership(models.Model):
    ROLE_CHOICES = [('owner', 'Owner'), ('member', 'Member')]
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workspace_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['workspace', 'user']

    def __str__(self):
        return f'{self.user.username} in {self.workspace.workspace_id} ({self.role})'


class AnalysisSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    workspace = models.ForeignKey(
        Workspace, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions'
    )
    title = models.CharField(max_length=200, default='New Analysis')
    requirements_text = models.TextField()
    suggested_requirement = models.TextField(blank=True, default='')
    team_notes = models.TextField(blank=True, default='')
    accuracy_score = models.IntegerField(default=0)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    requirement_id = models.CharField(max_length=20, blank=True, default='')
    extracted_info = models.TextField(blank=True, default='{}')
    clarity_score = models.IntegerField(default=0)
    completeness_score = models.IntegerField(default=0)
    testability_score = models.IntegerField(default=0)
    severity = models.CharField(max_length=10, blank=True, default='')

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.accuracy_score}%) - {self.user.username}"

    def get_score_label(self):
        if self.accuracy_score >= 80:
            return 'High Accuracy'
        elif self.accuracy_score >= 60:
            return 'Medium Accuracy'
        else:
            return 'Low Accuracy'

    def get_score_color(self):
        if self.accuracy_score >= 80:
            return 'green'
        elif self.accuracy_score >= 60:
            return 'orange'
        else:
            return 'red'

    def get_extracted_info(self):
        try:
            return json.loads(self.extracted_info)
        except (json.JSONDecodeError, TypeError):
            return {}


class FeedbackItem(models.Model):
    FEEDBACK_TYPE_CHOICES = [
        ('positive', 'Positive'),
        ('warning', 'Warning'),
    ]
    session = models.ForeignKey(
        AnalysisSession, on_delete=models.CASCADE, related_name='feedback_items'
    )
    feedback_type = models.CharField(max_length=20, choices=FEEDBACK_TYPE_CHOICES)
    message = models.TextField()

    def __str__(self):
        return f"[{self.feedback_type}] {self.message[:60]}"


class TestCondition(models.Model):
    CONDITION_TYPE_CHOICES = [
        ('Positive', 'Positive'),
        ('Negative', 'Negative'),
        ('Boundary', 'Boundary'),
        ('Security', 'Security'),
        ('Performance', 'Performance'),
    ]
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]
    session = models.ForeignKey(
        AnalysisSession, on_delete=models.CASCADE, related_name='test_conditions'
    )
    condition_id = models.CharField(max_length=10)
    description = models.TextField()
    condition_type = models.CharField(max_length=20, choices=CONDITION_TYPE_CHOICES)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')

    def __str__(self):
        return f"{self.condition_id}: {self.description[:50]}"


class RequirementGap(models.Model):
    session = models.ForeignKey(
        AnalysisSession, on_delete=models.CASCADE, related_name='gaps'
    )
    issue_id = models.CharField(max_length=10)
    issue_type = models.CharField(max_length=50)
    description = models.TextField()
    suggested_clarification = models.TextField()

    def __str__(self):
        return f"{self.issue_id}: {self.description[:50]}"


class TestScenario(models.Model):
    SCENARIO_TYPE_CHOICES = [
        ('positive', 'Positive'),
        ('negative', 'Negative'),
        ('edge', 'Edge Case'),
    ]
    PRIORITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
    ]
    session = models.ForeignKey(
        AnalysisSession, on_delete=models.CASCADE, related_name='test_scenarios'
    )
    scenario_id = models.CharField(max_length=20)
    requirement_ref = models.CharField(max_length=20, blank=True, default='')
    condition_ref = models.CharField(max_length=10, blank=True, default='')
    description = models.TextField()
    preconditions = models.TextField()
    steps_json = models.TextField()
    expected_result = models.TextField()
    scenario_type = models.CharField(
        max_length=20, choices=SCENARIO_TYPE_CHOICES, default='positive'
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='Medium')
    user_rating = models.CharField(max_length=10, blank=True, default='')

    def get_steps(self):
        try:
            return json.loads(self.steps_json)
        except (json.JSONDecodeError, TypeError):
            return [self.steps_json]

    def get_steps_display(self):
        return '\n'.join(self.get_steps())

    def __str__(self):
        return f"{self.scenario_id}: {self.description[:60]}"


class DetailedTestCase(models.Model):
    """Expanded test case generated on demand for Section 6."""
    scenario = models.OneToOneField(
        TestScenario, on_delete=models.CASCADE, related_name='detailed_case'
    )
    test_data = models.TextField(blank=True, default='')
    steps_json = models.TextField(default='[]')
    expected_results = models.TextField(blank=True, default='')
    postconditions = models.TextField(blank=True, default='')

    def get_steps(self):
        try:
            return json.loads(self.steps_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def __str__(self):
        return f"DetailedCase for {self.scenario.scenario_id}"
