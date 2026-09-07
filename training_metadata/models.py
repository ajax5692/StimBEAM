from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from animals_metadata.utils import (
    BaseAsyncJobModel,
    validate_measurement_unit_ranges,
)


class TrainingSession(BaseAsyncJobModel):
    animal = models.ForeignKey(
        "animals_metadata.Animal",
        on_delete=models.PROTECT,
        related_name="training_sessions",
    )

    training_date = models.DateField()

    bpod_file_path = models.CharField(
        max_length=500,
        help_text="Path to the source BPod .mat file.",
    )

    training_unit_range = models.CharField(
        max_length=200,
        validators=[validate_measurement_unit_ranges],
        help_text="Example: 10:21,25:55",
    )

    output_plot_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to the generated average lick traces plot PNG.",
    )

    output_raster_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to the generated lick occurrences raster plot PNG.",
    )

    output_excel_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to the exported Excel licking traces file.",
    )

    output_log_path = models.CharField(
        max_length=500,
        blank=True,
        help_text="Path to pipeline log if available.",
    )

    metrics_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="Calculated integrals and session summary metrics.",
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    def mark_completed(self) -> None:
        self.status = self.StatusChoices.COMPLETED
        self.completed_at = timezone.now()
        self.error_message = ""
        self.save(
            update_fields=[
                "status",
                "completed_at",
                "output_plot_path",
                "output_raster_path",
                "output_excel_path",
                "output_log_path",
                "metrics_json",
                "error_message",
            ]
        )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Training Session"
        verbose_name_plural = "Training Sessions"
        ordering = ["-training_date"]

    def __str__(self):
        return f"{self.animal.animal_id} - {self.training_date}"


class MouseBodyWeight(models.Model):
    animal = models.OneToOneField(
        "animals_metadata.Animal",
        on_delete=models.CASCADE,
        related_name="body_weight_tracker",
        verbose_name="Animal ID",
    )

    water_restriction_start_date = models.DateField(blank=True,
        null=True,verbose_name="Water Restriction Start Date",)
        
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Mouse Body Weight Record"
        verbose_name_plural = "Mice Body Weight Records"
        ordering = ["animal__animal_id"]

    def __str__(self):
        return f"{self.animal.animal_id}"

    def recalculate_percentages(self):
        entries = list(self.entries.all().order_by("date", "id"))
        if not entries:
            return
        start_wt = entries[0].body_weight_g
        to_update = []
        for entry in entries:
            if start_wt and start_wt > 0 and entry.body_weight_g is not None:
                new_pct = round((entry.body_weight_g / start_wt) * 100.0, 2)
            else:
                new_pct = 100.0
            if entry.percent_body_weight != new_pct:
                entry.percent_body_weight = new_pct
                to_update.append(entry)
        if to_update:
            BodyWeightEntry.objects.bulk_update(to_update, ["percent_body_weight"])


class BodyWeightEntry(models.Model):
    tracker = models.ForeignKey(
        MouseBodyWeight,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name="Mouse Body Weight",
    )

    date = models.DateField(
        verbose_name="Date",
    )

    body_weight_g = models.FloatField(
        verbose_name="Body Weight in Grams",
        validators=[MinValueValidator(0.01, message="Body weight must be greater than 0.")],
    )

    percent_body_weight = models.FloatField(
        blank=True,
        null=True,
        verbose_name="% Body Weight Compared to Start",
    )
    
    class TrainingPerformedChoices(models.TextChoices):
        YES = 'Y', 'Yes'
        NO  = 'N', 'No'
    
    is_training_done = models.TextField(
        blank=True,
        null=True,
        choices=TrainingPerformedChoices.choices
    )

    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Notes",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Body Weight Entry"
        verbose_name_plural = "Body Weight Entries"
        ordering = ["date"]

    def __str__(self):
        return ""

    def calculate_percent_body_weight(self):
        if not self.tracker_id or self.body_weight_g is None:
            return None
        first_entry = (
            BodyWeightEntry.objects.filter(tracker=self.tracker)
            .order_by("date", "id")
            .first()
        )
        if first_entry and first_entry.pk != self.pk:
            if self.date < first_entry.date:
                start_wt = self.body_weight_g
            else:
                start_wt = first_entry.body_weight_g
        else:
            start_wt = self.body_weight_g

        if start_wt and start_wt > 0:
            return round((self.body_weight_g / start_wt) * 100.0, 2)
        return 100.0

    def save(self, *args, **kwargs):
        self.percent_body_weight = self.calculate_percent_body_weight()
        super().save(*args, **kwargs)
        if self.tracker_id:
            self.tracker.recalculate_percentages()

    def delete(self, *args, **kwargs):
        tracker = self.tracker
        super().delete(*args, **kwargs)
        if tracker:
            tracker.recalculate_percentages()


class TrackChanges(models.Model):

    class CategoryChoices(models.TextChoices):
        TRAINING_SESSION = "training_session", "Training Session"
        MOUSE_BODY_WEIGHT = "mouse_body_weight", "Mouse Body Weight Record"

    class ActionChoices(models.TextChoices):
        CREATED = "+", "Created"
        UPDATED = "~", "Updated"
        DELETED = "-", "Deleted"

    category = models.CharField(
        max_length=30,
        choices=CategoryChoices.choices,
    )

    animal_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    action = models.CharField(
        max_length=1,
        choices=ActionChoices.choices,
    )

    changed_at = models.DateTimeField()

    changed_by = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    changes = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:
        verbose_name = "Track Change"
        verbose_name_plural = "Track Changes"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.get_category_display()} - {self.animal_id}"
