from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing_view, name="landing"),
    path("checkin/", views.checkin_checkout_view, name="checkin_checkout"),
    path("summary/", views.weekly_summary_view, name="weekly_summary"),
    path("month/", views.month_calendar_view, name="month_calendar"),
    path("holidays/", views.holiday_list_view, name="holiday_list"),
    path("export/month/", views.month_excel_export_view, name="month_excel_export"),
    path("delete/<str:record_date>/", views.delete_record_view, name="delete_record"),
    path("edit/<str:record_date>/", views.edit_record_view, name="edit_record"),
    # Timesheet
    path("timesheet/", views.timesheet_view, name="timesheet"),
    path("timesheet/export/", views.timesheet_export_view, name="timesheet_export"),
    # Comp-off
    path("compoff/add/", views.compoff_view, name="compoff_add"),
    path("compoff/<int:compoff_id>/consume/", views.compoff_consume_view, name="compoff_consume"),
    path("compoff/<int:compoff_id>/delete/", views.compoff_delete_view, name="compoff_delete"),
    # Legal
    path("privacy/", views.privacy_policy_view, name="privacy_policy"),
    path("terms/", views.terms_of_service_view, name="terms_of_service"),
    path("support/", views.support_view, name="support"),
]

