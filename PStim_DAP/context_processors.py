"""
Custom template context processors for PStim_DAP.
"""

from typing import Any, Dict
from django.apps import apps
from django.http import HttpRequest


def enabled_apps(request: HttpRequest) -> Dict[str, Any]:
    """
    Expose active INSTALLED_APPS and navigation items to all templates dynamically.
    """
    context: Dict[str, Any] = {
        "installed_apps": {
            app_config.name: True for app_config in apps.get_app_configs()
        }
    }
    if apps.is_installed("training_metadata"):
        try:
            from training_metadata.models import MouseBodyWeight, MouseTrainingRecord
            context["nav_body_weight_records"] = list(
                MouseBodyWeight.objects.select_related("animal").order_by("animal__animal_id")
            )
            context["nav_training_records"] = list(
                MouseTrainingRecord.objects.select_related("animal").order_by("animal__animal_id")
            )
        except Exception:
            context["nav_body_weight_records"] = []
            context["nav_training_records"] = []
    if apps.is_installed("imaging_metadata"):
        try:
            from imaging_metadata.models import MouseImagingRecord
            context["nav_imaging_records"] = list(
                MouseImagingRecord.objects.select_related("animal").order_by("animal__animal_id")
            )
        except Exception:
            context["nav_imaging_records"] = []
    return context

