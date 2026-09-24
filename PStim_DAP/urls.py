"""
URL configuration for PStim_DAP project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, reverse

# Disable the "VIEW SITE" link in Django Admin
admin.site.site_url = None
admin.site.index_title = ""

# Redirect the admin index landing to the Mouse Tracker
# admin.site.index = lambda request, extra_context=None: redirect('mouse_tracker')

original_admin_login = admin.site.login

def custom_admin_login(request, extra_context=None):
    admin_index_path = reverse('admin:index')
    # If no specific deep link was requested (or if it defaulted to /admin/)
    if request.GET.get('next') in (None, '', admin_index_path, admin_index_path.rstrip('/')):
        extra_context = extra_context or {}
        extra_context['next'] = reverse('mouse_tracker')

    response = original_admin_login(request, extra_context=extra_context)

    # If the login process redirects to /admin/, steer it to the Mouse Tracker
    if response.status_code == 302 and response.url in (admin_index_path, admin_index_path.rstrip('/')):
        tracker_url = reverse('mouse_tracker')
        response.url = tracker_url
        response['Location'] = tracker_url

    return response

admin.site.login = custom_admin_login

from animals_metadata.views import mouse_tracker_view

urlpatterns = [
    path('admin/tracker/', mouse_tracker_view, name='mouse_tracker'),
    path('admin/mouse-tracker/', mouse_tracker_view, name='mouse_tracker_alias'),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

