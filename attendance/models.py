from django.db import models
from django.contrib.auth.models import User


class Holiday(models.Model):
    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)

    def __str__(self) -> str:
        return f"{self.date} - {self.name}"


class AttendanceRecord(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    is_holiday = models.BooleanField(default=False)
    allowance_hours = models.FloatField(default=0.0)
    leave_type = models.CharField(max_length=50, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.date}"


class TimesheetActivity(models.Model):
    """Stores a single task/activity row for the NSE Timesheet for a given user & month."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    year = models.IntegerField()
    month = models.IntegerField()  # 1-12
    srno = models.IntegerField(default=1)
    activity = models.CharField(max_length=200, blank=True, default="")
    sub_activity = models.TextField(blank=True, default="")
    comments = models.TextField(blank=True, default="")
    artifact_id = models.CharField(max_length=100, blank=True, default="")
    # Daily hours stored as JSON string: {"1": 4.5, "15": 9, ...}
    daily_hours = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["srno", "id"]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.year}/{self.month} - {self.activity}"


class CompOffRecord(models.Model):
    """Tracks a compensation-off entitlement when an employee works on Saturday."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    worked_date = models.DateField()   # The Saturday that was worked
    leave_date = models.DateField(null=True, blank=True)  # When the comp-off leave is consumed
    reason = models.CharField(max_length=300, blank=True, default="")
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("consumed", "Consumed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "worked_date")
        ordering = ["-worked_date"]

    def __str__(self) -> str:
        return f"{self.user.username} comp-off for {self.worked_date} (status: {self.status})"
