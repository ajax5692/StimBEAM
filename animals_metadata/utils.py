import os
from pathlib import Path
import re
from typing import Any, List, Optional, Set, Tuple, Union

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpRequest
from django.utils import timezone
from django.utils.html import SafeString, format_html


def get_user_initials(user_or_username: Any) -> str:
    """
    Convert a User instance or username string into initials matching
    the convention in Animal.OwnerChoices (e.g. 'abhrajyoti.chakrabarti' -> 'AC').

    Args:
        user_or_username: Django User instance, username string, or None.

    Returns:
        A uppercase 2-letter or 3-letter initials string.
    """
    if not user_or_username:
        return ""

    # Known mappings for project members / usernames
    known_initials_map = {
        "abhrajyoti.chakrabarti": "AC",
        "abhrajyoti": "AC",
        "ac": "AC",
        "balazs": "TB",
        "balázs": "TB",
        "tb": "TB",
        "varada": "VK",
        "vk": "VK",
    }

    # Handle User model instance
    if hasattr(user_or_username, "username"):
        user = user_or_username
        if user.first_name and user.last_name:
            return f"{user.first_name[0]}{user.last_name[0]}".upper()

        raw_name = user.username or ""
    else:
        raw_name = str(user_or_username).strip()

    if not raw_name:
        return ""

    lower_name = raw_name.lower()
    if lower_name in known_initials_map:
        return known_initials_map[lower_name]

    # If already 2-3 characters (e.g. 'AC', 'TB', 'VK')
    if len(raw_name) <= 3 and raw_name.isalpha():
        return raw_name.upper()

    # If formatted as 'firstname.lastname', 'firstname_lastname', or 'first last'
    parts = [p for p in re.split(r"[._\s-]+", raw_name) if p]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()

    if len(parts) == 1:
        from animals_metadata.models import Animal

        if hasattr(Animal, "OwnerChoices"):
            for choice_val, choice_label in Animal.OwnerChoices.choices:
                if parts[0].lower() in choice_label.lower():
                    return choice_val

        return parts[0][:2].upper()

    return raw_name


def format_initial_entry(history_instance: Any) -> str:
    """
    Generate a detailed multi-line string of all field values present at record creation.

    Args:
        history_instance: The newly created simple_history historical instance.

    Returns:
        Formatted multi-line text listing initial non-empty field values.
    """
    if not history_instance:
        return "Initial Entry"

    excluded_fields = {
        "id",
        "history_id",
        "history_date",
        "history_type",
        "history_user",
        "history_user_id",
        "history_change_reason",
    }

    entries = []
    for field in history_instance._meta.fields:
        if field.name in excluded_fields:
            continue
        val = getattr(history_instance, field.name, None)
        if val is not None and str(val).strip() != "":
            entries.append(f"{field.name}: '{val}'")

    if entries:
        return "Initial Entry:\n" + "\n".join(entries)
    return "Initial Entry"


def build_history_diff_text(history_instance: Any) -> str:
    """
    Construct a human-readable summary of changes for a historical record event.
    Handles record creation (+), deletion (-), and field updates (~) with fallback.

    Args:
        history_instance: The simple_history historical model instance.

    Returns:
        A concise or multi-line string describing modified field names and old->new values.
    """
    if not history_instance:
        return ""

    if history_instance.history_type == "+":
        return format_initial_entry(history_instance)

    if history_instance.history_type == "-":
        return "Deleted Record"

    prev_record = getattr(history_instance, "prev_record", None)
    if not prev_record:
        return "No previous record"

    changes = []

    try:
        delta = history_instance.diff_against(prev_record)
        for change in delta.changes:
            changes.append(f"{change.field}: '{change.old}' → '{change.new}'")

    except Exception:
        excluded_fields = {
            "history_id",
            "history_date",
            "history_type",
            "history_user",
            "history_user_id",
            "history_change_reason",
        }

        for field in history_instance._meta.fields:
            if field.name in excluded_fields:
                continue

            old_val = getattr(prev_record, field.name, None)
            new_val = getattr(history_instance, field.name, None)

            if old_val != new_val:
                changes.append(f"{field.name}: '{old_val}' → '{new_val}'")

    return "\n".join(changes) if changes else "No field changes"


def render_copyable_path_widget(
    file_path: Optional[str],
    tooltip: str = "Copy file path",
) -> SafeString:
    """
    Render a clean inline copy button widget with SVG icon and text container.

    Args:
        file_path: Path string to display and copy.
        tooltip: Tooltip message for hover state and aria-label.

    Returns:
        Escaped HTML string safely rendered in Django admin tables.
    """
    path_val = (file_path or "").strip()
    if not path_val or path_val.lower() == "not available":
        return format_html('<span style="color: #64748b;">-</span>')

    return format_html(
        '<div style="display: grid; '
        'grid-template-columns: max-content 1fr; '
        'column-gap: 6px; '
        'align-items: start;">'
            '<button type="button" '
            'class="pstim-copy-button" '
            'data-copy-text="{}" '
            'title="{}" '
            'aria-label="{}">'
                '<svg '
                'width="16" '
                'height="16" '
                'viewBox="0 0 24 24" '
                'fill="none" '
                'stroke="currentColor" '
                'stroke-width="2" '
                'stroke-linecap="round" '
                'stroke-linejoin="round" '
                'aria-hidden="true">'
                    '<rect x="8" y="8" width="12" height="12" rx="2"></rect>'
                    '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>'
                '</svg>'
            '</button>'
            '<span style="overflow-wrap: anywhere;">{}</span>'
        '</div>',
        path_val,
        tooltip,
        tooltip,
        path_val,
    )


def render_output_resource_row(
    run_id: int,
    field_name: str,
    label: str,
    file_path: Optional[str],
    copy_tooltip: str = "Copy file path",
    edit_tooltip: str = "Edit file path",
) -> SafeString:
    """
    Render an output resource row for AnalysisRun changelist with:
      - Left-aligned copy button (.pstim-copy-button)
      - Bold label (e.g. • Log: or • Suite2P:)
      - File path text with a blue pencil edit button (.pstim-edit-button) at the end of the text
      - Inline editor container (.pstim-resource-editor) with save and cancel buttons

    Args:
        run_id: The ID of the AnalysisRun instance.
        field_name: Model field name ('output_log_path' or 'output_path').
        label: Label string to display (e.g. '• Log:' or '• Suite2P:').
        file_path: Current path string or None.
        copy_tooltip: Tooltip for the copy button.
        edit_tooltip: Tooltip for the edit pencil button.

    Returns:
        Escaped HTML string safely rendered in Django admin tables.
    """
    path_val = (file_path or "").strip()
    display_text = path_val if path_val else "Not available"
    update_url = f"/admin/imaging_analysis_metadata/analysisrun/{run_id}/update-output-path/"

    return format_html(
        '<div class="pstim-resource-row" data-run-id="{}" data-field="{}" data-update-url="{}" '
        'style="display: grid; grid-template-columns: max-content max-content 1fr; column-gap: 6px; align-items: start;">'
            '<button type="button" class="pstim-copy-button" data-copy-text="{}" title="{}" aria-label="{}">'
                '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                    '<rect x="8" y="8" width="12" height="12" rx="2"></rect>'
                    '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>'
                '</svg>'
            '</button>'
            '<strong>{}</strong>'
            '<div>'
                '<div class="pstim-resource-display" style="overflow-wrap: anywhere; word-break: break-all;">'
                    '<span class="pstim-resource-text">{}</span>'
                    '<button type="button" class="pstim-edit-button" title="{}" aria-label="{}" data-field="{}" data-current-path="{}">'
                        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                            '<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"></path>'
                            '<path d="m15 5 4 4"></path>'
                        '</svg>'
                    '</button>'
                '</div>'
                '<div class="pstim-resource-editor" style="display: none; align-items: center; gap: 4px; width: 100%; margin-top: 2px;">'
                    '<input type="text" class="pstim-resource-input" value="{}" placeholder="Enter file path..." />'
                    '<button type="button" class="pstim-resource-save-btn" title="Save file path" aria-label="Save file path">'
                        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
                            '<polyline points="20 6 9 17 4 12"></polyline>'
                        '</svg>'
                    '</button>'
                    '<button type="button" class="pstim-resource-cancel-btn" title="Cancel edit" aria-label="Cancel edit">'
                        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
                            '<line x1="18" y1="6" x2="6" y2="18"></line>'
                            '<line x1="6" y1="6" x2="18" y2="18"></line>'
                        '</svg>'
                    '</button>'
                '</div>'
            '</div>'
        '</div>',
        run_id,
        field_name,
        update_url,
        path_val,
        copy_tooltip,
        copy_tooltip,
        label,
        display_text,
        edit_tooltip,
        edit_tooltip,
        field_name,
        path_val,
        path_val,
    )


class CopyablePathInput(forms.TextInput):
    """
    TextInput widget with an inline copy button on the left for file paths.
    """
    def __init__(self, *args, tooltip="Copy file path", **kwargs):
        self.tooltip = tooltip
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        val_str = str(value or "").strip()
        copy_btn_html = format_html(
            '<button type="button" class="pstim-copy-button" data-copy-text="{}" '
            'title="{}" aria-label="{}" '
            'style="background: transparent; border: none; cursor: pointer; padding: 2px 4px; color: #94a3b8; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; transition: color 0.15s ease;" '
            'onmouseover="this.style.color=\'#38bdf8\';" onmouseout="this.style.color=\'#94a3b8\';">'
            '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<rect x="8" y="8" width="12" height="12" rx="2"></rect>'
            '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>'
            '</svg>'
            '</button>',
            val_str,
            self.tooltip,
            self.tooltip,
        )
        return format_html(
            '<div style="display: inline-flex; align-items: center; gap: 4px; width: 100%; min-width: 220px;">'
            '{}'
            '{}'
            '</div>',
            copy_btn_html,
            input_html,
        )


class BaseTrackChangesAdmin(admin.ModelAdmin):
    """
    Shared base ModelAdmin for TrackChanges audit trail across all domain apps.
    Eliminates duplicated admin configuration across apps.
    """

    list_display = (
        "category",
        "animal_id",
        "action",
        "changed_at",
        "display_changed_by",
        "changes",
    )

    list_filter = (
        "category",
        "action",
        "changed_at",
    )

    search_fields = (
        "animal_id",
        "changed_by",
        "changes",
    )

    readonly_fields = (
        "category",
        "animal_id",
        "action",
        "changed_at",
        "changed_by",
        "changes",
    )

    ordering = ("-changed_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Optional[models.Model] = None) -> bool:
        return False

    @admin.display(description="User Initials")
    def display_changed_by(self, obj: Any) -> str:
        return get_user_initials(obj.changed_by)


class BaseAsyncJobModel(models.Model):
    """
    Abstract base model for asynchronous pipeline jobs (e.g. Suite2p analysis, Bpod lick extraction).
    Standardizes status choices, timestamps, error fields, and state transitions.
    """

    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )

    created_at = models.DateTimeField(
        default=timezone.now,
    )

    started_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    completed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    error_message = models.TextField(
        blank=True,
        help_text="Error details recorded if the analysis job fails.",
    )

    def mark_running(self) -> None:
        self.status = self.StatusChoices.RUNNING
        self.started_at = timezone.now()
        self.completed_at = None
        self.error_message = ""
        self.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "error_message",
            ]
        )

    def mark_completed(self) -> None:
        self.status = self.StatusChoices.COMPLETED
        self.completed_at = timezone.now()
        self.error_message = ""
        self.save(
            update_fields=[
                "status",
                "completed_at",
                "error_message",
            ]
        )

    def mark_failed(self, error_message: Any = "") -> None:
        self.status = self.StatusChoices.FAILED
        self.completed_at = timezone.now()
        self.error_message = str(error_message)
        self.save(
            update_fields=[
                "status",
                "completed_at",
                "error_message",
            ]
        )

    class Meta:
        abstract = True


def parse_unit_ranges(unit_range_input: Optional[Union[str, List[int], range, Set[int]]]) -> Optional[List[int]]:
    """
    Convert a unit/trial range string (e.g. '10:21,25:55' or '3-174') into a sorted list of 1-based integers.

    Args:
        unit_range_input: String, list of integers, or range.

    Returns:
        Sorted list of integer numbers, or None if all units/trials should be included.
    """
    if unit_range_input is None:
        return None

    if isinstance(unit_range_input, (list, tuple, range, set)):
        return sorted(list(set(int(x) for x in unit_range_input)))

    unit_range_str = str(unit_range_input).strip()
    if not unit_range_str or unit_range_str.lower() in ("all", "none", "*", ""):
        return None

    units: Set[int] = set()
    for part in unit_range_str.split(","):
        part = part.strip()
        if not part:
            continue

        if ":" in part:
            pieces = part.split(":")
            if len(pieces) == 2:
                try:
                    s, e = int(pieces[0]), int(pieces[1])
                    units.update(range(min(s, e), max(s, e) + 1))
                except ValueError:
                    continue
        elif "-" in part:
            pieces = part.split("-")
            if len(pieces) == 2:
                try:
                    s, e = int(pieces[0]), int(pieces[1])
                    units.update(range(min(s, e), max(s, e) + 1))
                except ValueError:
                    continue
        else:
            try:
                units.add(int(part))
            except ValueError:
                continue

    return sorted(list(units)) if units else None


def is_same_bpod_file(path1: Any, path2: Any) -> bool:
    """
    Check if two BPod file paths or names refer to the same BPod data file.
    Normalizes path slashes, case-insensitivity on Windows, and compares file basenames.
    """
    if not path1 or not path2:
        return False
    p1 = str(path1).strip()
    p2 = str(path2).strip()
    if not p1 or not p2:
        return False
    if os.path.normcase(os.path.normpath(p1)) == os.path.normcase(os.path.normpath(p2)):
        return True
    name1 = Path(p1).name.lower()
    name2 = Path(p2).name.lower()
    if name1 and name2 and name1 == name2:
        return True
    return False


is_same_file = is_same_bpod_file
is_same_mesc_file = is_same_bpod_file


def record_track_change(
    track_changes_model: type,
    category: str,
    entity_id: Optional[str],
    history_instance: Any,
) -> None:
    """
    Centralized helper to record an audit trail entry in a domain TrackChanges table.

    Args:
        track_changes_model: The TrackChanges model class for the domain.
        category: CategoryChoices enum value.
        entity_id: The animal_id or virus_id associated with the change.
        history_instance: The historical record created by django-simple-history.
    """
    changes_text = build_history_diff_text(history_instance)
    user_initials = (
        get_user_initials(history_instance.history_user)
        if history_instance.history_user
        else None
    )

    track_changes_model.objects.create(
        category=category,
        animal_id=str(entity_id) if entity_id is not None else "",
        action=history_instance.history_type,
        changed_at=history_instance.history_date,
        changed_by=user_initials,
        changes=changes_text,
    )


def validate_measurement_unit_ranges(value: Any) -> None:
    """
    Validate measurement unit ranges string format, e.g.:
        10:21,25:55
        3,5:8,12
    """
    if not value or not str(value).strip():
        raise ValidationError("Measurement unit ranges cannot be empty.")

    for part in str(value).split(","):
        part = part.strip()
        if not part:
            raise ValidationError("Invalid measurement unit range.")

        if ":" in part:
            values = part.split(":")
            if len(values) != 2:
                raise ValidationError(f"Invalid range '{part}'. Use the format start:end.")

            try:
                start = int(values[0])
                end = int(values[1])
            except ValueError:
                raise ValidationError(f"Invalid range '{part}'. Unit numbers must be integers.")

            if start > end:
                raise ValidationError(f"Invalid range '{part}'. Start must not be greater than end.")
        else:
            try:
                int(part)
            except ValueError:
                raise ValidationError(f"Invalid unit '{part}'. Unit numbers must be integers.")


def validate_non_overlapping_session_units(
    model_class: Any,
    animal: Any,
    session_date: Any,
    unit_range_str: Any,
    date_field_name: str = "acquisition_date",
    unit_field_name: str = "measurement_unit_ranges",
    exclude_pk: Optional[Any] = None,
    model_name: str = "session",
) -> None:
    """
    Failsafe validator preventing duplicate or overlapping unit range measurements
    for the same animal on the same date.
    """
    if not animal or not session_date or not unit_range_str:
        return

    current_units = parse_unit_ranges(unit_range_str)

    filter_kwargs = {
        "animal": animal,
        date_field_name: session_date,
    }
    existing_sessions = model_class.objects.filter(**filter_kwargs)
    if exclude_pk is not None:
        existing_sessions = existing_sessions.exclude(pk=exclude_pk)

    for other in existing_sessions:
        other_range_str = getattr(other, unit_field_name, None)
        other_units = parse_unit_ranges(other_range_str)

        # If either covers all units (None) or units overlap
        if current_units is None or other_units is None:
            raise ValidationError({
                unit_field_name: (
                    f"A {model_name} for animal '{animal}' on {session_date} already exists "
                    f"(Record #{other.pk} with units '{other_range_str}'). "
                    f"Duplicate measurements on the same animal and date are not allowed."
                )
            })

        overlap = set(current_units) & set(other_units)
        if overlap:
            overlap_sorted = sorted(list(overlap))
            if len(overlap_sorted) > 10:
                overlap_display = f"{overlap_sorted[:10]}... ({len(overlap_sorted)} units)"
            else:
                overlap_display = str(overlap_sorted)

            raise ValidationError({
                unit_field_name: (
                    f"A {model_name} for animal '{animal}' on {session_date} already exists "
                    f"covering unit number(s) {overlap_display} (Record #{other.pk} with units '{other_range_str}'). "
                    f"Please specify non-overlapping unit numbers to analyze."
                )
            })



