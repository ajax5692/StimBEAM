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
from django.urls import path

# Disable the "VIEW SITE" link in Django Admin
admin.site.site_url = None
admin.site.index_title = ""

# Redirect the admin index landing to the Mouse Tracker
# admin.site.index = lambda request, extra_context=None: redirect('mouse_tracker')

from animals_metadata.views import mouse_tracker_view

urlpatterns = [
    path('admin/tracker/', mouse_tracker_view, name='mouse_tracker'),
    path('admin/mouse-tracker/', mouse_tracker_view, name='mouse_tracker_alias'),
    path('admin/', admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

