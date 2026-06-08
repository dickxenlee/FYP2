from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('about/', views.about_view, name='about'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Personal workspace
    path('workspace/', views.workspace_view, name='workspace'),
    path('workspace/session/<int:session_id>/', views.load_session_view, name='load_session'),

    # Shared workspace — must come after the more specific patterns above
    path('workspace/create/', views.create_workspace_view, name='create_workspace'),
    path('workspace/<str:workspace_id>/', views.shared_workspace_view, name='shared_workspace'),

    # Analysis
    path('analyze/', views.analyze_view, name='analyze'),
    path('confirm/', views.confirm_view, name='confirm'),
    path('reanalyze/', views.reanalyze_view, name='reanalyze'),

    # Collaborative output editing
    path('update_output_field/', views.update_output_field_view, name='update_output_field'),
    path('update_team_notes/', views.update_team_notes_view, name='update_team_notes'),

    # Session management
    path('delete_history/', views.delete_history_view, name='delete_history'),
    path('toggle_pin/', views.toggle_pin_view, name='toggle_pin'),
    path('rename_chat/', views.rename_chat_view, name='rename_chat'),
    path('delete_current_chat/', views.delete_current_chat_view, name='delete_current_chat'),

    # Detailed cases
    path('generate_detailed_cases/', views.generate_detailed_cases_view, name='generate_detailed_cases'),

    # Ratings
    path('rate_scenario/', views.rate_scenario_view, name='rate_scenario'),

    # Exports
    path('export/pdf/<int:session_id>/', views.export_pdf_view, name='export_pdf'),
    path('export/excel/<int:session_id>/', views.export_excel_view, name='export_excel'),
    path('export/csv/<int:session_id>/', views.export_csv_view, name='export_csv'),

    # Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),
]
