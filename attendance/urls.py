from django.urls import path

from . import views

urlpatterns = [
    path("", views.checkin_checkout_view, name="checkin_checkout"),
    path("summary/", views.weekly_summary_view, name="weekly_summary"),
    path("month/", views.month_calendar_view, name="month_calendar"),
    path("holidays/", views.holiday_list_view, name="holiday_list"),
    path("export/month/", views.month_excel_export_view, name="month_excel_export"),
    path("delete/<str:record_date>/", views.delete_record_view, name="delete_record"),
    path("edit/<str:record_date>/", views.edit_record_view, name="edit_record"),
]

