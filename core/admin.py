from django.contrib import admin
from .models import AnalysisSession, FeedbackItem, TestScenario


class FeedbackItemInline(admin.TabularInline):
    model = FeedbackItem
    extra = 0


class TestScenarioInline(admin.TabularInline):
    model = TestScenario
    extra = 0


@admin.register(AnalysisSession)
class AnalysisSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'accuracy_score', 'created_at')
    list_filter = ('user',)
    inlines = [FeedbackItemInline, TestScenarioInline]


@admin.register(TestScenario)
class TestScenarioAdmin(admin.ModelAdmin):
    list_display = ('scenario_id', 'description', 'scenario_type', 'session')
