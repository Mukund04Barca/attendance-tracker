from django.contrib import admin
from django.urls import include, path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from rest_framework import routers
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from attendance.views import signup_view
from attendance.api import AttendanceRecordViewSet, ProfileViewSet
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit

@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class RateLimitedLoginView(auth_views.LoginView):
    pass

def ratelimited_error(request, exception=None):
    response = JsonResponse({
        "error": "Too Many Requests", 
        "detail": "You have exceeded your rate limit."
    }, status=429)
    response["X-RateLimit-Limit"] = "100"
    response["Retry-After"] = "60"
    return response

router = routers.DefaultRouter()
router.register(r'attendance', AttendanceRecordViewSet, basename='api-attendance')
router.register(r'user', ProfileViewSet, basename='api-user')

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        RateLimitedLoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),
    path("accounts/signup/", signup_view, name="signup"),
    path("accounts/", include("django.contrib.auth.urls")),
    # Mobile API Routes
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/", include(router.urls)),
    
    path("robots.txt", TemplateView.as_view(template_name="robots.txt", content_type="text/plain")),
    path("sitemap.xml", TemplateView.as_view(template_name="sitemap.xml", content_type="application/xml")),

    path("", include("attendance.urls")),
]
