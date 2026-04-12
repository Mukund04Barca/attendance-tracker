from django.contrib import admin
from .models import AttendanceRecord, Holiday, TimesheetActivity, CompOffRecord


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
    )
    list_filter = ("user", "is_holiday", "date")
    search_fields = ("user__username",)


@admin.register(TimesheetActivity)
class TimesheetActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "year", "month", "srno", "activity")
    list_filter = ("user", "year", "month")


@admin.register(CompOffRecord)
class CompOffRecordAdmin(admin.ModelAdmin):
    list_display = ("user", "worked_date", "leave_date", "status")
    list_filter = ("user", "status")

