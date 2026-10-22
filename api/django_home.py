from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect


@staff_member_required
def django_home(request):
    """Send authenticated staff users to the Django-native publishing dashboard."""
    return redirect("browser-automation-dashboard")
