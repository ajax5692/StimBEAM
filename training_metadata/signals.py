from typing import Any

from django.db import models
from django.dispatch import receiver
from simple_history.signals import post_create_historical_record

from animals_metadata.utils import record_track_change
from .models import (
    BodyWeightEntry,
    MouseBodyWeight,
    MouseTrainingRecord,
    TrackChanges,
    TrainingSession,
)


@receiver(post_create_historical_record)
def create_track_change(
    sender: Any,
    instance: models.Model,
    history_instance: Any,
    **kwargs: Any,
) -> None:
    """
    Record an audit trail entry in TrackChanges upon historical record creation for training models.
    """
    model = instance.__class__

    if model is MouseTrainingRecord:
        category = TrackChanges.CategoryChoices.MOUSE_TRAINING
        try:
            animal_id = instance.animal.animal_id
        except Exception:
            animal_id = getattr(history_instance, "animal_id", None)
            if animal_id is not None:
                animal_id = str(animal_id)

    elif model is TrainingSession:
        category = TrackChanges.CategoryChoices.TRAINING_SESSION
        try:
            animal_id = instance.animal.animal_id
        except Exception:
            animal_id = getattr(history_instance, "animal_id", None)
            if animal_id is not None:
                animal_id = str(animal_id)

    elif model is MouseBodyWeight:
        category = TrackChanges.CategoryChoices.MOUSE_BODY_WEIGHT
        try:
            animal_id = instance.animal.animal_id
        except Exception:
            animal_id = getattr(history_instance, "animal_id", None)
            if animal_id is not None:
                animal_id = str(animal_id)

    elif model is BodyWeightEntry:
        category = TrackChanges.CategoryChoices.MOUSE_BODY_WEIGHT
        try:
            animal_id = instance.tracker.animal.animal_id
        except Exception:
            tracker_id = getattr(history_instance, "tracker_id", None)
            if tracker_id is not None:
                try:
                    tracker = MouseBodyWeight.objects.get(pk=tracker_id)
                    animal_id = tracker.animal.animal_id
                except Exception:
                    animal_id = str(tracker_id)
            else:
                animal_id = None
    else:
        return

    record_track_change(
        track_changes_model=TrackChanges,
        category=category,
        entity_id=animal_id,
        history_instance=history_instance,
    )
