from pathlib import Path

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
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

from .models import (
    BodyWeightEntry,
    MouseBodyWeight,
    MouseTrainingRecord,
    TrackChanges,
    TrainingSession,
)
from .services import execute_training_analysis


@admin.register(TrainingSession)
class TrainingSessionAdmin(SimpleHistoryAdmin):
    list_select_related = ("animal",)

    list_display = (
        "animal",
        "training_date",
        "display_status",
        "display_d_prime",
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

    @admin.display(description="d'")
    def display_d_prime(self, obj):
        if not obj or not obj.metrics_json or "d_prime" not in obj.metrics_json:
            return "-"
        d_val = obj.metrics_json["d_prime"]
        color = "#4ade80" if d_val >= 1.5 else "#60a5fa"
        return format_html('<strong style="color: {}; font-size: 13px;">{}</strong>', color, f"{d_val:.2f}")

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


class CopyablePathInput(forms.TextInput):
    """
    TextInput widget with an inline copy button on the left for file paths.
    """
    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        val_str = str(value or "").strip()
        copy_btn_html = format_html(
            '<button type="button" class="pstim-copy-button" data-copy-text="{}" '
            'title="Copy BPod file path" aria-label="Copy BPod file path" '
            'style="background: transparent; border: none; cursor: pointer; padding: 2px 4px; color: #94a3b8; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; transition: color 0.15s ease;" '
            'onmouseover="this.style.color=\'#38bdf8\';" onmouseout="this.style.color=\'#94a3b8\';">'
            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<rect x="8" y="8" width="12" height="12" rx="2"></rect>'
            '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>'
            '</svg>'
            '</button>',
            val_str,
        )
        return format_html(
            '<div style="display: inline-flex; align-items: center; gap: 4px; width: 100%; min-width: 220px;">'
            '{}'
            '{}'
            '</div>',
            copy_btn_html,
            input_html,
        )


class TrainingSessionInline(admin.TabularInline):
    model = TrainingSession
    fk_name = "tracker"
    extra = 0
    fields = (
        "training_date",
        "bpod_file_path",
        "training_unit_range",
        "display_status",
        "display_d_prime",
        "display_performance",
        "display_lick_traces_link",
        "notes",
    )
    readonly_fields = (
        "display_status",
        "display_d_prime",
        "display_performance",
        "display_lick_traces_link",
    )

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "bpod_file_path":
            kwargs["widget"] = CopyablePathInput(attrs={"style": "width: 100%; min-width: 200px;"})
            return db_field.formfield(**kwargs)
        if db_field.name == "training_unit_range":
            kwargs["widget"] = forms.TextInput(attrs={"style": "min-width: 110px;"})
            return db_field.formfield(**kwargs)
        if db_field.name == "notes":
            kwargs["widget"] = forms.TextInput(attrs={"style": "min-width: 140px;"})
            return db_field.formfield(**kwargs)
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Status")
    def display_status(self, obj):
        if not obj or not obj.pk:
            return "-"
        if obj.status == TrainingSession.StatusChoices.RUNNING:
            return format_html(
                '<span style="display: inline-flex; align-items: center; gap: 6px; color: #60a5fa; font-weight: 600;">'
                '<span>{}</span>'
                '<span style="'
                'width: 12px;'
                'height: 12px;'
                'border: 2px solid rgba(255,255,255,0.35);'
                'border-top-color: currentColor;'
                'border-radius: 50%;'
                'display: inline-block;'
                'animation: analysis-spin 0.8s linear infinite;'
                'flex-shrink: 0;'
                '"></span>'
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

    @admin.display(description="d'")
    def display_d_prime(self, obj):
        if not obj or not obj.metrics_json or "d_prime" not in obj.metrics_json:
            return "-"
        d_val = obj.metrics_json["d_prime"]
        color = "#4ade80" if d_val >= 1.5 else "#60a5fa"
        return format_html('<strong style="color: {}; font-size: 13px;">{}</strong>', color, f"{d_val:.2f}")

    @admin.display(description="Performance (Hit / FA)")
    def display_performance(self, obj):
        if not obj or not obj.metrics_json:
            return "-"
        m = obj.metrics_json
        hr = m.get("hit_rate")
        far = m.get("false_alarm_rate")
        if hr is not None and far is not None:
            return format_html(
                '<span style="font-size: 12px; color: #cbd5e1;">Hit: <strong style="color: #4ade80;">{}%</strong> | FA: <strong style="color: #f87171;">{}%</strong></span>',
                f"{hr * 100:.1f}",
                f"{far * 100:.1f}",
            )
        return "-"

    @admin.display(description="Lick Traces")
    def display_lick_traces_link(self, obj):
        if not obj or not obj.pk:
            return "-"
        url = reverse("admin:training_session_lick_traces", args=[obj.pk])
        if obj.status == TrainingSession.StatusChoices.COMPLETED:
            return format_html(
                '<a href="{}" target="_blank" class="button" style="background: #0284c7; color: white; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px; white-space: nowrap;">'
                '📊 View Traces'
                '</a>',
                url,
            )
        return format_html(
            '<a href="{}" target="_blank" class="button" style="background: #334155; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; white-space: nowrap;">'
            'Open Viewer'
            '</a>',
            url,
        )


@admin.register(MouseTrainingRecord)
class MouseTrainingRecordAdmin(SimpleHistoryAdmin):
    inlines = [TrainingSessionInline]
    list_select_related = ("animal", "animal__owner")

    list_display = (
        "get_animal_id",
        "get_owner",
        "get_total_sessions",
        "get_latest_training_date",
        "get_latest_d_prime",
        "get_pipeline_stage",
    )

    list_filter = (
        "animal__owner",
        "animal__status",
        "animal__pipeline_stage",
    )

    search_fields = (
        "animal__animal_id",
        "animal__owner__username",
        "animal__owner__first_name",
        "animal__owner__last_name",
        "notes",
    )

    ordering = (
        "animal__animal_id",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    (
                        "animal",
                        "get_owner_display",
                        "notes",
                    ),
                ),
            },
        ),
    )

    readonly_fields = (
        "get_owner_display",
    )

    formfield_overrides = {
        models.TextField: {
            "widget": forms.Textarea(
                attrs={
                    "rows": 1,
                    "style": "height: 36px; width: 100%; min-width: 250px; max-width: 450px; resize: vertical;",
                    "placeholder": "Notes...",
                }
            ),
        },
    }

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("animal",)
        return self.readonly_fields

    @admin.display(description="Animal ID", ordering="animal__animal_id")
    def get_animal_id(self, obj):
        return obj.animal.animal_id if obj.animal else "-"

    @admin.display(description="Owner", ordering="animal__owner")
    def get_owner(self, obj):
        if obj.animal and obj.animal.owner:
            return obj.animal.owner.first_name if obj.animal.owner.first_name else obj.animal.owner.username
        return "-"

    @admin.display(description="Owner")
    def get_owner_display(self, obj):
        if obj and obj.animal and obj.animal.owner:
            owner_name = obj.animal.owner.first_name if obj.animal.owner.first_name else obj.animal.owner.username
            return f"{owner_name}"
        return "-"

    @admin.display(description="Total Sessions")
    def get_total_sessions(self, obj):
        return obj.sessions.count()

    @admin.display(description="Last Training Day")
    def get_latest_training_date(self, obj):
        latest = obj.sessions.order_by("-training_date", "-id").first()
        return latest.training_date if latest else "-"

    @admin.display(description="LATEST d'")
    def get_latest_d_prime(self, obj):
        latest = obj.sessions.filter(status=TrainingSession.StatusChoices.COMPLETED).order_by("-training_date", "-id").first()
        if latest and latest.metrics_json and "d_prime" in latest.metrics_json:
            d_val = latest.metrics_json["d_prime"]
            color = "#4ade80" if d_val >= 1.5 else "#60a5fa"
            return format_html('<strong style="color: {}; font-size: 13px;">{}</strong>', color, f"{d_val:.2f}")
        return "-"

    @admin.display(description="Pipeline Stage", ordering="animal__pipeline_stage")
    def get_pipeline_stage(self, obj):
        return obj.animal.get_pipeline_stage_display() if (obj.animal and hasattr(obj.animal, "get_pipeline_stage_display")) else (obj.animal.pipeline_stage if obj.animal else "-")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("sessions")

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, TrainingSession):
                if not instance.animal_id and form.instance.animal_id:
                    instance.animal = form.instance.animal
                instance.tracker = form.instance
            instance.save()
        for deleted_obj in formset.deleted_objects:
            deleted_obj.delete()
        formset.save_m2m()

    def response_add(self, request, obj, post_url_continue=None):
        if "_save" in request.POST:
            self.message_user(request, f"Mouse training record for {obj.animal.animal_id} was saved successfully.")
            return redirect(reverse("admin:training_metadata_mousetrainingrecord_change", args=[obj.pk]))
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_save" in request.POST:
            self.message_user(request, f"Mouse training record for {obj.animal.animal_id} was saved successfully.")
            return redirect(reverse("admin:training_metadata_mousetrainingrecord_change", args=[obj.pk]))
        return super().response_change(request, obj)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        context["subtitle"] = None
        return super().render_change_form(request, context, add=add, change=change, form_url=form_url, obj=obj)


    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:record_id>/delete-session/<int:session_id>/",
                self.admin_site.admin_view(self.delete_session_view),
                name="training_delete_session",
            ),
        ]
        return custom_urls + urls

    def delete_session_view(self, request, record_id, session_id):
        if not self.has_change_permission(request):
            raise PermissionDenied

        record = get_object_or_404(MouseTrainingRecord, pk=record_id)
        session = TrainingSession.objects.filter(pk=session_id).first()
        if not session:
            messages.warning(request, "Training session not found or already deleted.")
            return redirect(reverse("admin:training_metadata_mousetrainingrecord_change", args=[record_id]))

        if session.tracker_id != record.pk and session.animal_id != record.animal_id:
            messages.error(request, "This training session does not belong to this animal.")
            return redirect(reverse("admin:training_metadata_mousetrainingrecord_change", args=[record_id]))

        date_str = str(session.training_date)
        animal_str = str(session.animal.animal_id) if session.animal else ""
        session.delete()
        messages.success(
            request,
            f"Training session ({date_str}) for animal {animal_str} was deleted successfully.",
        )
        return redirect(reverse("admin:training_metadata_mousetrainingrecord_change", args=[record_id]))


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
    list_select_related = ("animal", "animal__owner")

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
        "animal__owner__username",
        "animal__owner__first_name",
        "animal__owner__last_name",
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
        if obj.animal and obj.animal.owner:
            return obj.animal.owner.first_name if obj.animal.owner.first_name else obj.animal.owner.username
        return "-"

    @admin.display(description="Owner")
    def get_owner_display(self, obj):
        if obj and obj.animal and obj.animal.owner:
            owner_name = obj.animal.owner.first_name if obj.animal.owner.first_name else obj.animal.owner.username
            return f"{owner_name} ({obj.animal.owner.username})"
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
