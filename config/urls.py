"""
URL configuration for config project.
"""
from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

# --- DRF / API ---
from rest_framework.routers import DefaultRouter
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from orgs.views import OrgViewSet, me_view
from compliance_app.views import ComplianceRecordViewSet
from .views import health_view

# DRF router (API)
router = DefaultRouter()
router.register(r"orgs", OrgViewSet, basename="org")
router.register(r"compliance", ComplianceRecordViewSet, basename="compliance")

schema_view = get_schema_view(
    openapi.Info(
        title="NIS2 Compliance API",
        default_version="v1",
        description="API documentation for your SaaS",
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path("accounts/", include("django.contrib.auth.urls")),  # login, logout, password reset, etc.
    # ---------- UI (HTML) ----------
    path("", include(("ui.urls", "ui"), namespace="ui")),
    path("", include(("orgs.urls", "orgs"), namespace="orgs")),
    path("", include(("incidents.urls", "incidents"), namespace="incidents")),  # include ONCE

    # If you have UI routes for compliance records:
    path(
        "orgs/<int:org_id>/records/",
        include(("compliance_app.urls", "compliance_ui"), namespace="compliance_ui"),
    ),

    # ---------- Admin ----------
    path("admin/", admin.site.urls),

    # ---------- API ----------
    path("api/", include(router.urls)),
    path("api/token/", obtain_auth_token),
    path("api/me/", me_view, name="me"),
    path("api/health/", health_view, name="health-check"),

    # ---------- API docs ----------
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-swagger-ui"),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
]

# Serve uploaded media in DEBUG
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
