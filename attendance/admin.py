from django.contrib import admin

from .models import AttendanceRecord, Holiday


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("date", "name")
    ordering = ("-date",)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "check_in",
        "check_out",
        "is_holiday",
        "allowance_hours",
    )
    list_filter = ("user", "is_holiday", "date")
    search_fields = ("user__username",)

