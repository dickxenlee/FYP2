import io
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.http import require_POST
from django.db.models import Avg, Count

from .forms import RegisterForm, LoginForm
from .models import (
    AnalysisSession, RequirementGap, TestScenario,
    FeedbackItem, TestCondition,
    Workspace, WorkspaceMembership,
)
from .services.test_scenario_generator import TestScenarioGenerator
from .services.qa_analyzer import QAAnalyzer
from .services.detailed_case_generator import DetailedCaseGenerator
from .services.training_data_manager import TrainingDataManager
from .services.gemini_service import GeminiQuotaExceeded


# ─────────────────────────────────────────────
# Public pages
# ─────────────────────────────────────────────

def home_view(request):
    return render(request, 'home.html')


def about_view(request):
    return render(request, 'about.html')


# ─────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────

def register_view(request):
    if request.user.is_authenticated:
        return redirect('workspace')

    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('workspace')
    else:
        form = RegisterForm()

    return render(request, 'register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('workspace')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('workspace')
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('home')


# ─────────────────────────────────────────────
# Main workspace
# ─────────────────────────────────────────────

def _my_workspaces(user):
    """Team workspaces this user belongs to, newest first."""
    return Workspace.objects.filter(
        memberships__user=user
    ).distinct().order_by('-created_at')


@login_required
def workspace_view(request):
    history = AnalysisSession.objects.filter(
        user=request.user, workspace__isnull=True
    ).order_by('-is_pinned', '-created_at')
    return render(request, 'workspace.html', {
        'history': history,
        'my_workspaces': _my_workspaces(request.user),
    })


# ─────────────────────────────────────────────
# Shared workspace (multi-user)
# ─────────────────────────────────────────────

@login_required
def shared_workspace_view(request, workspace_id):
    workspace = get_object_or_404(Workspace, workspace_id=workspace_id)

    membership, just_joined = WorkspaceMembership.objects.get_or_create(
        workspace=workspace,
        user=request.user,
        defaults={'role': 'member'},
    )

    history = AnalysisSession.objects.filter(
        workspace=workspace
    ).order_by('-is_pinned', '-created_at')

    members = WorkspaceMembership.objects.filter(
        workspace=workspace
    ).select_related('user')

    return render(request, 'workspace.html', {
        'history': history,
        'workspace': workspace,
        'members': members,
        'just_joined': just_joined,
        'my_workspaces': _my_workspaces(request.user),
    })


# ─────────────────────────────────────────────
# Create workspace
# ─────────────────────────────────────────────

@login_required
@require_POST
def create_workspace_view(request):
    try:
        body = json.loads(request.body)
        name = body.get('name', '').strip() or 'Team Workspace'
    except (json.JSONDecodeError, AttributeError):
        name = 'Team Workspace'

    workspace = Workspace.objects.create(name=name[:200], owner=request.user)
    WorkspaceMembership.objects.create(workspace=workspace, user=request.user, role='owner')

    return JsonResponse({'workspace_id': workspace.workspace_id, 'name': workspace.name})


# ─────────────────────────────────────────────
# Serialization helpers
# ─────────────────────────────────────────────

def _serialize_scenarios(session):
    return [
        {
            'db_id': s.id,
            'id': s.scenario_id,
            'requirement_ref': s.requirement_ref,
            'condition_ref': s.condition_ref,
            'description': s.description,
            'preconditions': s.preconditions,
            'steps': s.get_steps(),
            'expected_result': s.expected_result,
            'type': s.scenario_type,
            'priority': s.priority,
            'user_rating': s.user_rating,
        }
        for s in session.test_scenarios.all()
    ]


def _serialize_conditions(session):
    return [
        {
            'db_id': c.id,
            'condition_id': c.condition_id,
            'description': c.description,
            'type': c.condition_type,
            'priority': c.priority,
        }
        for c in session.test_conditions.all()
    ]


def _serialize_gaps(session):
    return [
        {
            'db_id': g.id,
            'issue_id': g.issue_id,
            'issue_type': g.issue_type,
            'description': g.description,
            'suggested_clarification': g.suggested_clarification,
        }
        for g in session.gaps.all()
    ]


def _serialize_quality_assessment(session):
    return {
        'clarity_score': session.clarity_score,
        'completeness_score': session.completeness_score,
        'testability_score': session.testability_score,
        'overall_score': session.accuracy_score,
        'severity': session.severity or 'Medium',
        'positive_aspects': [
            {'db_id': f.id, 'text': f.message}
            for f in session.feedback_items.filter(feedback_type='positive')
        ],
        'warnings': [
            {'db_id': f.id, 'text': f.message}
            for f in session.feedback_items.filter(feedback_type='warning')
        ],
    }


def _build_session_response(session, requirement_info=None, requires_decision=False, suggested=''):
    """Build the standard JSON response payload for a session."""
    info = requirement_info or session.get_extracted_info() or {'requirement_id': session.requirement_id or 'REQ-001'}
    return {
        'session_id': session.id,
        'requirements_text': session.requirements_text,
        'score': session.accuracy_score,
        'score_label': session.get_score_label(),
        'score_color': session.get_score_color(),
        'requirement_info': info,
        'quality_assessment': _serialize_quality_assessment(session),
        'test_conditions': _serialize_conditions(session),
        'gaps': _serialize_gaps(session),
        'scenarios': _serialize_scenarios(session),
        'requires_user_decision': requires_decision,
        'suggested_requirement': suggested,
        'team_notes': session.team_notes,
    }


def _get_accessible_session(session_id, user):
    """Return session if user is the owner or a workspace member, else raise Http404."""
    session = get_object_or_404(AnalysisSession, id=session_id)
    if session.user == user:
        return session
    if session.workspace and WorkspaceMembership.objects.filter(
        workspace=session.workspace, user=user
    ).exists():
        return session
    raise Http404()


# ─────────────────────────────────────────────
# Load session
# ─────────────────────────────────────────────

@login_required
def load_session_view(request, session_id):
    session = _get_accessible_session(session_id, request.user)
    return JsonResponse(_build_session_response(session))


# ─────────────────────────────────────────────
# Analyze requirements — Phase 3 QA redesign
# ─────────────────────────────────────────────

@login_required
@require_POST
def analyze_view(request):
    try:
        body = json.loads(request.body)
        requirements_text = body.get('requirements_text', '').strip()
        workspace_id = body.get('workspace_id', '').strip()
    except (json.JSONDecodeError, AttributeError):
        requirements_text = request.POST.get('requirements_text', '').strip()
        workspace_id = ''

    if not requirements_text:
        return JsonResponse({'error': 'Requirements text is required.'}, status=400)

    # Resolve workspace (if any)
    workspace = None
    if workspace_id:
        try:
            ws = Workspace.objects.get(workspace_id=workspace_id)
            if WorkspaceMembership.objects.filter(workspace=ws, user=request.user).exists():
                workspace = ws
        except Workspace.DoesNotExist:
            pass

    EDITED_PREFIX = 'EDITED:'
    if requirements_text.startswith(EDITED_PREFIX):
        edited_text = requirements_text[len(EDITED_PREFIX):].strip()
        try:
            qa_result = QAAnalyzer().analyze(edited_text)
        except GeminiQuotaExceeded as e:
            return JsonResponse({'error': str(e)}, status=429)
        session = TrainingDataManager().save_qa_session(
            user=request.user,
            requirements_text=edited_text,
            qa_result=qa_result,
        )
        if workspace:
            session.workspace = workspace
            session.save(update_fields=['workspace'])
        resp = _build_session_response(session, requirement_info=qa_result['requirement_info'])
        resp['system_action'] = 'analysis_and_generation'
        return JsonResponse(resp)

    try:
        qa_result = QAAnalyzer().analyze(requirements_text)
    except GeminiQuotaExceeded as e:
        return JsonResponse({'error': str(e)}, status=429)
    except Exception as e:
        # Return JSON (not an HTML 500 page) so the frontend can show a real message
        return JsonResponse({'error': f'Analysis failed: {e}'}, status=500)

    session = TrainingDataManager().save_qa_session(
        user=request.user,
        requirements_text=requirements_text,
        qa_result=qa_result,
    )
    if workspace:
        session.workspace = workspace
        session.save(update_fields=['workspace'])

    overall_score = session.accuracy_score
    suggested = qa_result.get('suggested_requirement', '')
    requires_improvement = overall_score < 80

    return JsonResponse(_build_session_response(
        session,
        requirement_info=qa_result['requirement_info'],
        requires_decision=requires_improvement,
        suggested=suggested if requires_improvement else '',
    ))


# ─────────────────────────────────────────────
# Section 6: Generate detailed test cases on demand
# ─────────────────────────────────────────────

@login_required
@require_POST
def generate_detailed_cases_view(request):
    try:
        body = json.loads(request.body)
        session_id = body.get('session_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if not session_id:
        return JsonResponse({'error': 'session_id is required.'}, status=400)

    session = _get_accessible_session(session_id, request.user)

    scenarios = [
        {
            'scenario_id': s.scenario_id,
            'description': s.description,
            'preconditions': s.preconditions,
            'expected_result': s.expected_result,
        }
        for s in session.test_scenarios.all()
    ]

    if not scenarios:
        return JsonResponse({'error': 'No scenarios found for this session.'}, status=400)

    try:
        detailed_cases = DetailedCaseGenerator().generate(scenarios)
    except GeminiQuotaExceeded as e:
        return JsonResponse({'error': str(e)}, status=429)
    TrainingDataManager().save_detailed_cases(session_id, detailed_cases)

    return JsonResponse({'session_id': session_id, 'detailed_cases': detailed_cases})


# ─────────────────────────────────────────────
# Update a single output field (feedback / gap / condition / scenario)
# ─────────────────────────────────────────────

@login_required
@require_POST
def update_output_field_view(request):
    try:
        body = json.loads(request.body)
        model_name = body.get('model')
        db_id = body.get('db_id')
        field = body.get('field')
        value = body.get('value', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    if not all([model_name, db_id, field]):
        return JsonResponse({'error': 'model, db_id, field are required.'}, status=400)

    def _has_access(session):
        if session.user == request.user:
            return True
        return session.workspace and WorkspaceMembership.objects.filter(
            workspace=session.workspace, user=request.user
        ).exists()

    if model_name == 'scenario':
        obj = get_object_or_404(TestScenario, id=db_id)
        if not _has_access(obj.session):
            return JsonResponse({'error': 'Access denied.'}, status=403)
        allowed = ('description', 'preconditions', 'expected_result')
        if field not in allowed:
            return JsonResponse({'error': 'Invalid field.'}, status=400)
        setattr(obj, field, value)
        obj.save(update_fields=[field])

    elif model_name == 'feedback':
        obj = get_object_or_404(FeedbackItem, id=db_id)
        if not _has_access(obj.session):
            return JsonResponse({'error': 'Access denied.'}, status=403)
        if field != 'message':
            return JsonResponse({'error': 'Invalid field.'}, status=400)
        obj.message = value
        obj.save(update_fields=['message'])

    elif model_name == 'gap':
        obj = get_object_or_404(RequirementGap, id=db_id)
        if not _has_access(obj.session):
            return JsonResponse({'error': 'Access denied.'}, status=403)
        allowed = ('description', 'suggested_clarification')
        if field not in allowed:
            return JsonResponse({'error': 'Invalid field.'}, status=400)
        setattr(obj, field, value)
        obj.save(update_fields=[field])

    elif model_name == 'condition':
        obj = get_object_or_404(TestCondition, id=db_id)
        if not _has_access(obj.session):
            return JsonResponse({'error': 'Access denied.'}, status=403)
        if field != 'description':
            return JsonResponse({'error': 'Invalid field.'}, status=400)
        obj.description = value
        obj.save(update_fields=['description'])

    else:
        return JsonResponse({'error': 'Invalid model.'}, status=400)

    return JsonResponse({'status': 'ok'})


# ─────────────────────────────────────────────
# Update team notes on a session
# ─────────────────────────────────────────────

@login_required
@require_POST
def update_team_notes_view(request):
    try:
        body = json.loads(request.body)
        session_id = body.get('session_id')
        notes = body.get('notes', '')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    if not session_id:
        return JsonResponse({'error': 'session_id is required.'}, status=400)

    session = _get_accessible_session(session_id, request.user)
    session.team_notes = notes
    session.save(update_fields=['team_notes'])
    return JsonResponse({'status': 'ok'})


# ─────────────────────────────────────────────
# STATE 2: Confirm user decision — legacy, kept for backward compat
# ─────────────────────────────────────────────

@login_required
@require_POST
def confirm_view(request):
    try:
        body = json.loads(request.body)
        session_id = body.get('session_id')
        decision = body.get('decision', '').lower()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if not session_id or decision not in ('yes', 'no'):
        return JsonResponse(
            {'error': 'session_id and decision (yes or no) are required.'}, status=400
        )

    session = _get_accessible_session(session_id, request.user)

    text_to_use = session.suggested_requirement if decision == 'yes' else session.requirements_text
    scenarios = TestScenarioGenerator().generate_scenarios(text_to_use)
    TrainingDataManager().add_scenarios_to_session(session_id, scenarios)

    return JsonResponse({'session_id': session.id, 'scenarios': scenarios, 'requires_user_decision': False})


# ─────────────────────────────────────────────
# Delete all history
# ─────────────────────────────────────────────

@login_required
@require_POST
def delete_history_view(request):
    try:
        body = json.loads(request.body)
        workspace_id = body.get('workspace_id', '').strip()
    except (json.JSONDecodeError, AttributeError):
        workspace_id = ''

    if workspace_id:
        workspace = get_object_or_404(Workspace, workspace_id=workspace_id)
        if workspace.owner != request.user:
            return JsonResponse({'error': 'Only the workspace owner can clear history.'}, status=403)
        AnalysisSession.objects.filter(workspace=workspace).delete()
    else:
        AnalysisSession.objects.filter(user=request.user, workspace__isnull=True).delete()

    return JsonResponse({'status': 'cleared', 'message': 'History cleared successfully.'})


# ─────────────────────────────────────────────
# Toggle pin
# ─────────────────────────────────────────────

@login_required
@require_POST
def toggle_pin_view(request):
    try:
        body = json.loads(request.body)
        session_id = body.get('session_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if not session_id:
        return JsonResponse({'error': 'session_id is required.'}, status=400)

    session = _get_accessible_session(session_id, request.user)
    session.is_pinned = not session.is_pinned
    session.save()

    return JsonResponse({
        'system_action': 'chat_pinned',
        'session_id': session.id,
        'chat_metadata': {'is_pinned': session.is_pinned},
    })


# ─────────────────────────────────────────────
# Rename chat
# ─────────────────────────────────────────────

@login_required
@require_POST
def rename_chat_view(request):
    try:
        body = json.loads(request.body)
        session_id = body.get('session_id')
        new_title = body.get('new_title', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if not session_id or not new_title:
        return JsonResponse({'error': 'session_id and new_title are required.'}, status=400)

    session = _get_accessible_session(session_id, request.user)
    session.title = new_title[:200]
    session.save()

    return JsonResponse({'system_action': 'chat_renamed', 'chat_title': session.title, 'session_id': session.id})


# ─────────────────────────────────────────────
# Delete current chat
# ─────────────────────────────────────────────

@login_required
@require_POST
def delete_current_chat_view(request):
    try:
        body = json.loads(request.body)
        session_id = body.get('session_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request body.'}, status=400)

    if not session_id:
        return JsonResponse({'error': 'session_id is required.'}, status=400)

    session = _get_accessible_session(session_id, request.user)
    session.delete()

    return JsonResponse({'system_action': 'chat_deleted', 'session_id': session_id})


# ─────────────────────────────────────────────
# Dashboard — analytics overview
# ─────────────────────────────────────────────

@login_required
def dashboard_view(request):
    sessions = AnalysisSession.objects.filter(user=request.user)
    total = sessions.count()

    avg_score    = round(sessions.aggregate(avg=Avg('accuracy_score'))['avg'] or 0, 1)
    high_count   = sessions.filter(accuracy_score__gte=80).count()
    medium_count = sessions.filter(accuracy_score__gte=60, accuracy_score__lt=80).count()
    low_count    = sessions.filter(accuracy_score__lt=60).count()

    all_scenarios    = TestScenario.objects.filter(session__user=request.user)
    total_scenarios  = all_scenarios.count()
    useful_count     = all_scenarios.filter(user_rating='useful').count()
    not_useful_count = all_scenarios.filter(user_rating='not_useful').count()

    top_gaps = (
        RequirementGap.objects
        .filter(session__user=request.user)
        .values('issue_type')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    recent = sessions.order_by('-created_at')[:6]

    return render(request, 'dashboard.html', {
        'total': total,
        'avg_score': avg_score,
        'high_count': high_count,
        'medium_count': medium_count,
        'low_count': low_count,
        'total_scenarios': total_scenarios,
        'useful_count': useful_count,
        'not_useful_count': not_useful_count,
        'top_gaps': top_gaps,
        'recent': recent,
    })


# ─────────────────────────────────────────────
# Rate a scenario
# ─────────────────────────────────────────────

@login_required
@require_POST
def rate_scenario_view(request):
    try:
        body = json.loads(request.body)
        db_id  = body.get('db_id')
        rating = body.get('rating', '')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    if rating not in ('useful', 'not_useful', ''):
        return JsonResponse({'error': 'Invalid rating value.'}, status=400)

    scenario = get_object_or_404(TestScenario, id=db_id)
    session  = scenario.session

    if session.user != request.user:
        if not (session.workspace and WorkspaceMembership.objects.filter(
            workspace=session.workspace, user=request.user
        ).exists()):
            return JsonResponse({'error': 'Access denied.'}, status=403)

    scenario.user_rating = '' if scenario.user_rating == rating else rating
    scenario.save()

    return JsonResponse({'status': 'ok', 'db_id': scenario.id, 'rating': scenario.user_rating})


# ─────────────────────────────────────────────
# Re-analyze an existing session
# ─────────────────────────────────────────────

@login_required
@require_POST
def reanalyze_view(request):
    try:
        body = json.loads(request.body)
        session_id = body.get('session_id')
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)

    session = _get_accessible_session(session_id, request.user)

    try:
        qa_result = QAAnalyzer().analyze(session.requirements_text)
    except GeminiQuotaExceeded as e:
        return JsonResponse({'error': str(e)}, status=429)

    TrainingDataManager().reanalyze_session(session, qa_result)

    return JsonResponse(_build_session_response(
        session,
        requirement_info=qa_result['requirement_info'],
        requires_decision=session.accuracy_score < 80,
        suggested=session.suggested_requirement,
    ))


# ─────────────────────────────────────────────
# Export — CSV
# ─────────────────────────────────────────────

@login_required
def export_csv_view(request, session_id):
    import csv
    session = _get_accessible_session(session_id, request.user)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="test_scenarios_{session_id}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Scenario ID', 'Requirement Ref', 'Condition Ref',
        'Description', 'Preconditions', 'Expected Result',
        'Type', 'Priority', 'User Rating',
    ])
    for s in session.test_scenarios.all():
        writer.writerow([
            s.scenario_id, s.requirement_ref, s.condition_ref,
            s.description, s.preconditions, s.expected_result,
            s.scenario_type, s.priority, s.user_rating,
        ])

    return response


# ─────────────────────────────────────────────
# Export — PDF
# ─────────────────────────────────────────────

@login_required
def export_pdf_view(request, session_id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_LEFT

    session = _get_accessible_session(session_id, request.user)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('ReportTitle', parent=styles['Title'], fontSize=16, spaceAfter=6)
    heading_style = ParagraphStyle('ReportHeading', parent=styles['Heading2'], fontSize=12, spaceAfter=4)
    normal_style = ParagraphStyle('ReportNormal', parent=styles['Normal'], fontSize=9, leading=12)
    header_cell_style = ParagraphStyle(
        'HeaderCell', parent=styles['Normal'], fontSize=8, leading=10,
        textColor=colors.white, fontName='Helvetica-Bold',
    )
    body_cell_style = ParagraphStyle(
        'BodyCell', parent=styles['Normal'], fontSize=7.5, leading=10,
        textColor=colors.black, wordWrap='CJK',
    )

    story = []
    story.append(Paragraph('Test Scenario Report', title_style))
    story.append(Paragraph(f'Project: {session.title}', heading_style))
    story.append(Paragraph(
        f'Quality Score: {session.accuracy_score}% ({session.get_score_label()})', normal_style
    ))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph('Requirements', heading_style))
    req_text = session.requirements_text.replace('&', '&amp;').replace('<', '&lt;').replace('\n', '<br/>')
    story.append(Paragraph(req_text, normal_style))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph('Analysis Feedback', heading_style))
    for item in session.feedback_items.all():
        prefix = '&#10003;' if item.feedback_type == 'positive' else '&#9632;'
        safe_msg = item.message.replace('&', '&amp;').replace('<', '&lt;')
        story.append(Paragraph(f'{prefix} {safe_msg}', normal_style))
    story.append(Spacer(1, 0.5*cm))

    story.append(Paragraph('Generated Test Scenarios', heading_style))
    story.append(Spacer(1, 0.2*cm))

    col_widths = [1.4*cm, 3.8*cm, 3.3*cm, 4.9*cm, 3.6*cm]
    header_labels = ['ID', 'Description', 'Pre-Conditions', 'Test Steps', 'Expected Result']
    table_data = [[Paragraph(label, header_cell_style) for label in header_labels]]

    for s in session.test_scenarios.all():
        steps = s.get_steps()
        steps_html = '<br/>'.join(
            f'{i+1}. {step.replace("&", "&amp;").replace("<", "&lt;")}'
            for i, step in enumerate(steps)
        )
        table_data.append([
            Paragraph(s.scenario_id, body_cell_style),
            Paragraph(s.description.replace('&', '&amp;').replace('<', '&lt;'), body_cell_style),
            Paragraph(s.preconditions.replace('&', '&amp;').replace('<', '&lt;'), body_cell_style),
            Paragraph(steps_html, body_cell_style),
            Paragraph(s.expected_result.replace('&', '&amp;').replace('<', '&lt;'), body_cell_style),
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR',    (0, 0), (-1, 0), colors.white),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
        ('GRID',         (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
        ('VALIGN',       (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',   (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 4),
        ('LEFTPADDING',  (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(table)

    doc.build(story)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="test_scenarios_{session_id}.pdf"'
    return response


# ─────────────────────────────────────────────
# Export — Excel
# ─────────────────────────────────────────────

@login_required
def export_excel_view(request, session_id):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    session = _get_accessible_session(session_id, request.user)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Test Scenarios'

    ws['A1'] = 'Project'
    ws['B1'] = session.title
    ws['A2'] = 'Quality Score'
    ws['B2'] = f"{session.accuracy_score}% ({session.get_score_label()})"
    ws['A3'] = 'Generated By'
    ws['B3'] = session.user.username

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2c3e50', end_color='2c3e50', fill_type='solid')
    center_align = Alignment(horizontal='center', vertical='top', wrap_text=True)
    top_align = Alignment(vertical='top', wrap_text=True)

    headers = ['ID', 'Description', 'Pre-Conditions', 'Test Steps', 'Expected Result', 'Type']
    header_row = 5
    for col_num, header_text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_num, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    alt_fill = PatternFill(start_color='f2f2f2', end_color='f2f2f2', fill_type='solid')
    for row_idx, s in enumerate(session.test_scenarios.all(), start=header_row + 1):
        steps_text = '\n'.join(s.get_steps())
        row_data = [s.scenario_id, s.description, s.preconditions, steps_text, s.expected_result, s.scenario_type]
        for col_num, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_num, value=value)
            cell.alignment = top_align
            if row_idx % 2 == 0:
                cell.fill = alt_fill

    column_widths = [10, 30, 30, 45, 35, 12]
    for i, width in enumerate(column_widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    response = HttpResponse(
        buffer,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="test_scenarios_{session_id}.xlsx"'
    return response
