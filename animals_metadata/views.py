from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone

from animals_metadata.services import MouseTrackerService


@staff_member_required
def mouse_tracker_view(request):
    """
    Renders the unified Laboratory Dashboard & Mouse-Centric Profile Workstation.
    """
    today = timezone.now().date()
    context = MouseTrackerService.get_tracker_dashboard_context(today=today)
    return render(request, "admin/mouse_tracker.html", context)