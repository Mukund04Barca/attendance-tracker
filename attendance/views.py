from datetime import date, datetime, timedelta
import logging

import pandas as pd
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
import calendar
from io import BytesIO

from .models import AttendanceRecord, Holiday

logger = logging.getLogger("attendance")

ATT_CFG = getattr(settings, "ATTENDANCE_CONFIG", {})

WORKDAY_START = datetime.strptime(
    ATT_CFG.get("workday_start", "09:00"), "%H:%M"
).time()
WORKDAY_END = datetime.strptime(
    ATT_CFG.get("workday_end", "18:00"), "%H:%M"
).time()
DEFAULT_ALLOWANCE = float(ATT_CFG.get("default_allowance_hours", 0.0))
CONFIG_HOLIDAYS = set(ATT_CFG.get("holidays", []))
WEEKLY_TARGET = float(ATT_CFG.get("weekly_hours_target", 40))
DAILY_TARGET_HOURS = float(ATT_CFG.get("daily_hours_target", 9))


def is_config_holiday(date):
    return date.isoformat() in CONFIG_HOLIDAYS


@login_required
def checkin_checkout_view(request):
    now = timezone.localtime(timezone.now())
    today = now.date()

    record, created = AttendanceRecord.objects.get_or_create(
        user=request.user,
        date=today,
        defaults={
            "is_holiday": Holiday.objects.filter(date=today).exists()
            or is_config_holiday(today),
            "allowance_hours": DEFAULT_ALLOWANCE if is_config_holiday(today) else 0.0,
        },
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "check_in" and record.check_in is None:
            record.check_in = now
            record.save()
            logger.info(
                "User %s checked in at %s", request.user.username, now.isoformat()
            )
        elif action == "check_out" and record.check_out is None and record.check_in:
            record.check_out = now
            record.save()
            logger.info(
                "User %s checked out at %s", request.user.username, now.isoformat()
            )
        elif action == "set_manual":
            check_in_str = request.POST.get("manual_check_in") or ""
            check_out_str = request.POST.get("manual_check_out") or ""
            try:
                if check_in_str:
                    ci_naive = datetime.strptime(
                        f"{today} {check_in_str}", "%Y-%m-%d %H:%M"
                    )
                    record.check_in = timezone.make_aware(ci_naive)
                if check_out_str:
                    co_naive = datetime.strptime(
                        f"{today} {check_out_str}", "%Y-%m-%d %H:%M"
                    )
                    record.check_out = timezone.make_aware(co_naive)
                record.save()
                logger.info(
                    "User %s set manual times: %s - %s",
                    request.user.username,
                    check_in_str or "—",
                    check_out_str or "—",
                )
            except ValueError:
                pass
        elif action == "delete":
            logger.info(
                "User %s deleted attendance for %s",
                request.user.username,
                today.isoformat(),
            )
            record.delete()
            return redirect("checkin_checkout")

        return redirect("weekly_summary")

    hours_today = None
    if record.check_in and record.check_out:
        delta = record.check_out - record.check_in
        hours_today = round(max(delta.total_seconds() / 3600.0, 0), 2)

    check_in_display = None
    check_out_display = None
    if record.check_in:
        ci_local = timezone.localtime(record.check_in)
        check_in_display = ci_local.strftime("%H:%M")
    if record.check_out:
        co_local = timezone.localtime(record.check_out)
        check_out_display = co_local.strftime("%H:%M")

    expected_checkout = None
    if record.check_in:
        expected_dt = record.check_in + timedelta(hours=DAILY_TARGET_HOURS)
        expected_local = timezone.localtime(expected_dt)
        expected_checkout = expected_local.strftime("%H:%M")

    context = {
        "record": record,
        "hours_today": hours_today,
        "check_in_display": check_in_display,
        "check_out_display": check_out_display,
        "expected_checkout": expected_checkout,
        "daily_target_hours": DAILY_TARGET_HOURS,
        "today": today,
        # Upcoming holidays this month + next (max 3)
        "upcoming_holidays": list(
            Holiday.objects.filter(date__gte=today).order_by("date")[:3]
        ),
        # Weekly hours total so far (last 7 days)
        "weekly_total": round(
            sum(
                max((r.check_out - r.check_in).total_seconds() / 3600.0, 0)
                for r in AttendanceRecord.objects.filter(
                    user=request.user,
                    date__range=(today - timedelta(days=6), today),
                    check_in__isnull=False,
                    check_out__isnull=False,
                )
            ),
            1,
        ),
        "weekly_target": WEEKLY_TARGET,
    }
    return render(request, "attendance/checkin_checkout.html", context)



@login_required
def weekly_summary_view(request):
    today = timezone.localtime(timezone.now()).date()
    start_date = today - timedelta(days=6)

    qs = (
        AttendanceRecord.objects.filter(
            user=request.user,
            date__range=(start_date, today),
        )
        .order_by("date")
        .values("date", "check_in", "check_out", "is_holiday", "allowance_hours")
    )

    df = pd.DataFrame(list(qs))
    summary = {}

    if not df.empty:
        df["check_in"] = pd.to_datetime(df["check_in"], utc=True).dt.tz_convert(
            settings.TIME_ZONE
        ).dt.tz_localize(None)
        df["check_out"] = pd.to_datetime(df["check_out"], utc=True).dt.tz_convert(
            settings.TIME_ZONE
        ).dt.tz_localize(None)

        df["hours"] = (
            (df["check_out"] - df["check_in"])
            .dt.total_seconds()
            .fillna(0)
            / 3600.0
        ).clip(lower=0)

        df["effective_hours"] = df.apply(
            lambda row: 0.0 if row["is_holiday"] else row["hours"], axis=1
        )

        df["total_with_allowance"] = df["effective_hours"] + df["allowance_hours"]

        df["check_in_time"] = df["check_in"].dt.strftime("%H:%M").fillna("")
        df["check_out_time"] = df["check_out"].dt.strftime("%H:%M").fillna("")

        weekly_avg = df["total_with_allowance"].mean()
        weekly_total = df["total_with_allowance"].sum()

        summary = {
            "rows": df.to_dict(orient="records"),
            "weekly_avg": round(float(weekly_avg), 2),
            "weekly_total": round(float(weekly_total), 2),
            "weekly_target": WEEKLY_TARGET,
        }

    context = {
        "summary": summary,
        "start_date": start_date,
        "end_date": today,
    }
    return render(request, "attendance/weekly_summary.html", context)


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("checkin_checkout")

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            logger.info("New user signed up: %s", user.username)
            return redirect("checkin_checkout")
    else:
        form = UserCreationForm()

    return render(request, "registration/signup.html", {"form": form})


@login_required
def month_calendar_view(request):
    year = request.GET.get("year")
    month = request.GET.get("month")

    today = timezone.localtime(timezone.now()).date()
    if year and month:
        year = int(year)
        month = int(month)
        current = date(year, month, 1)
    else:
        current = date(today.year, today.month, 1)

    cal = calendar.Calendar(firstweekday=6)  # Sunday start
    month_weeks_raw = cal.monthdatescalendar(current.year, current.month)

    records = AttendanceRecord.objects.filter(
        user=request.user,
        date__year=current.year,
        date__month=current.month,
    )

    records_by_date: dict[date, dict] = {}
    for r in records:
        ci_str = co_str = None
        hours = None
        if r.check_in:
            ci_local = timezone.localtime(r.check_in)
            ci_str = ci_local.strftime("%H:%M")
        if r.check_out:
            co_local = timezone.localtime(r.check_out)
            co_str = co_local.strftime("%H:%M")
        if r.check_in and r.check_out:
            delta = r.check_out - r.check_in
            hours = round(max(delta.total_seconds() / 3600.0, 0), 2)

        records_by_date[r.date] = {
            "check_in": ci_str,
            "check_out": co_str,
            "hours": hours,
        }

    db_holidays = Holiday.objects.filter(date__year=current.year, date__month=current.month)
    holiday_dates = {h.date for h in db_holidays}
    # add config holidays that fall in this month
    for d in cal.itermonthdates(current.year, current.month):
        if is_config_holiday(d):
            holiday_dates.add(d)

    prev_month = (current.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

    weeks = []
    for week in month_weeks_raw:
        row = []
        for d in week:
            row.append(
                {
                    "date": d,
                    "is_current_month": d.month == current.month,
                    "is_holiday": d in holiday_dates,
                    "record": records_by_date.get(d),
                }
            )
        weeks.append(row)

    context = {
        "current": current,
        "weeks": weeks,
        "today": today,
        "prev_year": prev_month.year,
        "prev_month": prev_month.month,
        "next_year": next_month.year,
        "next_month": next_month.month,
    }
    return render(request, "attendance/month_calendar.html", context)


@login_required
def holiday_list_view(request):
    holidays = Holiday.objects.all().order_by("date")

    if request.method == "POST" and request.user.is_staff:
        date_str = request.POST.get("date")
        name = request.POST.get("name") or "Holiday"
        try:
            h_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            Holiday.objects.get_or_create(date=h_date, defaults={"name": name})
        except (TypeError, ValueError):
            pass
        return redirect("holiday_list")

    return render(
        request,
        "attendance/holiday_list.html",
        {"holidays": holidays},
    )


@login_required
def month_excel_export_view(request):
    year = request.GET.get("year")
    month = request.GET.get("month")

    today = timezone.localtime(timezone.now()).date()
    if year and month:
        year = int(year)
        month = int(month)
    else:
        year = today.year
        month = today.month

    qs = AttendanceRecord.objects.filter(
        user=request.user,
        date__year=year,
        date__month=month,
    ).values("date", "check_in", "check_out", "is_holiday", "allowance_hours")

    df = pd.DataFrame(list(qs))
    if not df.empty:
        df["check_in"] = pd.to_datetime(df["check_in"], utc=True).dt.tz_convert(
            settings.TIME_ZONE
        ).dt.tz_localize(None)
        df["check_out"] = pd.to_datetime(df["check_out"], utc=True).dt.tz_convert(
            settings.TIME_ZONE
        ).dt.tz_localize(None)
        df["hours"] = (
            (df["check_out"] - df["check_in"])
            .dt.total_seconds()
            .fillna(0)
            / 3600.0
        ).clip(lower=0)
        df["effective_hours"] = df.apply(
            lambda row: 0.0 if row["is_holiday"] else row["hours"], axis=1
        )
        df["total_with_allowance"] = df["effective_hours"] + df["allowance_hours"]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        (df if not df.empty else pd.DataFrame()).to_excel(
            writer, index=False, sheet_name="Attendance"
        )

    output.seek(0)
    filename = f"attendance_{request.user.username}_{year}_{month:02d}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def delete_record_view(request, record_date):
    """Delete an AttendanceRecord for any date from the month calendar."""
    if request.method != "POST":
        return redirect("month_calendar")

    try:
        target_date = datetime.strptime(record_date, "%Y-%m-%d").date()
    except ValueError:
        return redirect("month_calendar")

    deleted, _ = AttendanceRecord.objects.filter(
        user=request.user, date=target_date
    ).delete()

    if deleted:
        logger.info(
            "User %s deleted attendance record for %s",
            request.user.username,
            target_date.isoformat(),
        )

    # Redirect back to the same month the user was viewing
    url = reverse("month_calendar")
    return redirect(f"{url}?year={target_date.year}&month={target_date.month}")


@login_required
def edit_record_view(request, record_date):
    """Create or update an AttendanceRecord's check-in/check-out for any date."""
    try:
        target_date = datetime.strptime(record_date, "%Y-%m-%d").date()
    except ValueError:
        return redirect("month_calendar")

    if request.method != "POST":
        return redirect("month_calendar")

    check_in_str = request.POST.get("check_in", "").strip()
    check_out_str = request.POST.get("check_out", "").strip()

    record, _ = AttendanceRecord.objects.get_or_create(
        user=request.user,
        date=target_date,
        defaults={
            "is_holiday": Holiday.objects.filter(date=target_date).exists()
            or is_config_holiday(target_date),
            "allowance_hours": DEFAULT_ALLOWANCE if is_config_holiday(target_date) else 0.0,
        },
    )

    try:
        if check_in_str:
            ci_naive = datetime.strptime(f"{target_date} {check_in_str}", "%Y-%m-%d %H:%M")
            record.check_in = timezone.make_aware(ci_naive)
        else:
            record.check_in = None

        if check_out_str:
            co_naive = datetime.strptime(f"{target_date} {check_out_str}", "%Y-%m-%d %H:%M")
            record.check_out = timezone.make_aware(co_naive)
        else:
            record.check_out = None

        record.save()
        logger.info(
            "User %s edited record for %s: in=%s out=%s",
            request.user.username, target_date.isoformat(),
            check_in_str or "—", check_out_str or "—",
        )
    except ValueError:
        pass

    url = reverse("month_calendar")
    return redirect(f"{url}?year={target_date.year}&month={target_date.month}")
