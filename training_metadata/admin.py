from pathlib import Path

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from animals_metadata.utils import (
    BaseTrackChangesAdmin,
    get_user_initials,
    render_copyable_path_widget,
)

from .models import BodyWeightEntry, MouseBodyWeight, TrackChanges, TrainingSession
from .services import execute_training_analysis


@admin.register(TrainingSession)
class TrainingSessionAdmin(SimpleHistoryAdmin):
    list_select_related = ("animal",)

    list_display = (
        "animal",
        "training_date",
        "display_status",
        "display_bpod_file_path",
        "training_unit_range",
        "display_lick_traces_link",
        "created_at",
    )

    list_filter = (
        "status",
        "animal",
        "training_date",
    )

    search_fields = (
        "animal__animal_id",
        "bpod_file_path",
        "training_unit_range",
        "notes",
    )

    ordering = ("-training_date",)

    readonly_fields = (
        "status",
        "created_at",
        "started_at",
        "completed_at",
        "output_plot_path",
        "output_raster_path",
        "output_excel_path",
        "output_log_path",
        "metrics_json",
        "error_message",
    )

    fieldsets = (
        (
            "Session Information",
            {
                "fields": (
                    "animal",
                    "training_date",
                    "bpod_file_path",
                    "training_unit_range",
                    "notes",
                ),
            },
        ),
        (
            "Analysis Status & Results",
            {
                "fields": (
                    "status",
                    "created_at",
                    "started_at",
                    "completed_at",
                    "output_plot_path",
                    "output_raster_path",
                    "output_excel_path",
                    "metrics_json",
                    "error_message",
                ),
            },
        ),
    )

    @admin.display(description="BPod File Path", ordering="bpod_file_path")
    def display_bpod_file_path(self, obj):
        return render_copyable_path_widget(obj.bpod_file_path, tooltip="Copy BPod file path")

    @admin.display(description="Status", ordering="status")
    def display_status(self, obj):
        if obj.status == TrainingSession.StatusChoices.RUNNING:
            return format_html(
                '<span style="display: inline-flex; align-items: center; gap: 6px; color: #60a5fa; font-weight: 600;">'
                '<span>{}</span>'
                '<span style="width: 12px; height: 12px; border: 2px solid rgba(255,255,255,0.35); border-top-color: currentColor; border-radius: 50%; display: inline-block; animation: analysis-spin 0.8s linear infinite;"></span>'
                '</span>',
                "Running",
            )
        elif obj.status == TrainingSession.StatusChoices.COMPLETED:
            return format_html(
                '<span style="display: inline-flex; align-items: center; gap: 4px; color: #4ade80; font-weight: 600;">'
                '<span>{}</span>'
                '</span>',
                "✓ Completed",
            )
        elif obj.status == TrainingSession.StatusChoices.FAILED:
            return format_html(
                '<span style="display: inline-flex; align-items: center; gap: 4px; color: #f87171; font-weight: 600;" title="{}">'
                '<span>{}</span>'
                '</span>',
                obj.error_message or "Analysis failed",
                "✗ Failed",
            )
        return format_html(
            '<span style="color: #facc15; font-weight: 600;">{}</span>',
            "Pending",
        )

    @admin.display(description="Lick Analysis")
    def display_lick_traces_link(self, obj):
        url = reverse("admin:training_session_lick_traces", args=[obj.pk])
        if obj.status == TrainingSession.StatusChoices.COMPLETED:
            return format_html(
                '<a href="{}" class="button" style="background: #0284c7; color: white; padding: 4px 10px; border-radius: 4px; font-weight: 600; font-size: 12px;">'
                '📊 View Traces'
                '</a>',
                url,
            )
        return format_html(
            '<a href="{}" class="button" style="background: #334155; color: white; padding: 4px 10px; border-radius: 4px; font-size: 12px;">'
            'Open Viewer'
            '</a>',
            url,
        )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:session_id>/lick-traces/",
                self.admin_site.admin_view(self.lick_traces_view),
                name="training_session_lick_traces",
            ),
            path(
                "<int:session_id>/run-analysis/",
                self.admin_site.admin_view(self.run_analysis_view),
                name="training_session_run_analysis",
            ),
        ]
        return custom_urls + urls

    def lick_traces_view(self, request, session_id):
        session = get_object_or_404(TrainingSession, pk=session_id)
        context = {
            **self.admin_site.each_context(request),
            "session": session,
            "title": f"Lick Traces: Animal {session.animal.animal_id} ({session.training_date})",
        }
        return TemplateResponse(
            request,
            "admin/training_metadata/trainingsession/lick_traces.html",
            context,
        )

    def run_analysis_view(self, request, session_id):
        session = get_object_or_404(TrainingSession, pk=session_id)
        try:
            execute_training_analysis(session)
            messages.success(
                request,
                f"Training analysis completed successfully for session #{session.pk} (Animal {session.animal.animal_id}).",
            )
        except Exception as exc:
            messages.error(
                request,
                f"Training analysis failed: {exc}",
            )
        return redirect("admin:training_session_lick_traces", session_id=session.pk)


class BodyWeightEntryInline(admin.TabularInline):
    model = BodyWeightEntry
    extra = 0
    fields = (
        "date",
        "body_weight_g",
        "display_percent_body_weight",
        "is_training_done",
        "notes",
    )
    readonly_fields = (
        "display_percent_body_weight",
    )
    formfield_overrides = {
        models.FloatField: {
            "widget": forms.NumberInput(attrs={"min": "0", "step": "0.1"}),
        },
    }

    @admin.display(description="% Body Weight Compared to Start")
    def display_percent_body_weight(self, obj):
        if obj and obj.percent_body_weight is not None:
            return f"{obj.percent_body_weight:.1f} %"
        return "-"


@admin.register(MouseBodyWeight)
class MouseBodyWeightAdmin(SimpleHistoryAdmin):
    change_form_template = "admin/training_metadata/mousebodyweight/change_form.html"
    inlines = [BodyWeightEntryInline]
    list_select_related = ("animal",)

    list_display = (
        "get_animal_id",
        "get_owner",
        "water_restriction_start_date",
        "get_latest_percent_body_weight",
        "get_latest_training_date",
    )

    list_filter = (
        "animal__owner",
    )

    search_fields = (
        "animal__animal_id",
        "animal__owner",
    )

    ordering = (
        "animal__animal_id",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "animal",
                    "get_owner_display",
                    "water_restriction_start_date",
                ),
            },
        ),
    )

    readonly_fields = (
        "get_owner_display",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("animal",)
        return self.readonly_fields

    @admin.display(description="Animal ID", ordering="animal__animal_id")
    def get_animal_id(self, obj):
        return obj.animal.animal_id if obj.animal else "-"

    @admin.display(description="Owner", ordering="animal__owner")
    def get_owner(self, obj):
        return obj.animal.owner if obj.animal else "-"

    @admin.display(description="Owner")
    def get_owner_display(self, obj):
        if obj and obj.animal:
            owner_label = obj.animal.get_owner_display() if hasattr(obj.animal, "get_owner_display") else obj.animal.owner
            return f"{owner_label} ({obj.animal.owner})"
        return "-"
    
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("entries")
    
    @admin.display(description="% Body Wt. From Start")
    def get_latest_percent_body_weight(self, obj):
        latest_entry = obj.entries.order_by("-date", "-id").first()
        if latest_entry and latest_entry.percent_body_weight is not None:
            pct = latest_entry.percent_body_weight
            # Optional: highlight in red/warning if weight falls below the 80% safety limit
            color = "#ff4d4f" if pct < 80.0 else "#4ade80"  # red if below 80%, green otherwise
            formatted_pct = f"{pct:.1f} %"
            return format_html(
                '<span style="color: {}; font-weight: 600;">{}</span>',
                color,
                formatted_pct,
            )
        return "-"
    
    @admin.display(description="Last training day")
    def get_latest_training_date(self, obj):
        latest_entry = obj.entries.order_by("-date", "-id").first()
        if latest_entry and latest_entry.is_training_done is not None:
            for entry in obj.entries.order_by("-date", "-id"):
                if entry.is_training_done == 'Y':
                    return entry.date           
        return "-"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.recalculate_percentages()


@admin.register(TrackChanges)
class TrackChangesAdmin(BaseTrackChangesAdmin):
    pass
