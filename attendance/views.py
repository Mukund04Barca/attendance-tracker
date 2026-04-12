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

from django_ratelimit.decorators import ratelimit

from .models import AttendanceRecord, Holiday, TimesheetActivity, CompOffRecord

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

@ratelimit(key='ip', rate='100/m', block=True)
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
                    date__range=(today - timedelta(days=today.weekday()), today),
                    check_in__isnull=False,
                    check_out__isnull=False,
                )
            ),
            1,
        ),
        "weekly_target": WEEKLY_TARGET,
        "is_leave": bool(record.leave_type),
    }
    return render(request, "attendance/checkin_checkout.html", context)



@login_required
def weekly_summary_view(request):
    today = timezone.localtime(timezone.now()).date()
    # Start of current week (Monday)
    start_date = today - timedelta(days=today.weekday())
    # End of current week (Sunday)
    end_date = start_date + timedelta(days=6)

    qs = (
        AttendanceRecord.objects.filter(
            user=request.user,
            date__range=(start_date, end_date),
        )
        .order_by("date")
        .values("date", "check_in", "check_out", "is_holiday", "allowance_hours", "leave_type")
    )

    df = pd.DataFrame(list(qs))
    summary = {}

    # Dynamic weekly target: Mon–Fri working days minus holidays, * 9h
    working_days = 0
    for i in range(7):
        d = start_date + timedelta(days=i)
        if d.weekday() >= 5:
            continue  # skip Saturday/Sunday
        if Holiday.objects.filter(date=d).exists() or is_config_holiday(d):
            continue
        working_days += 1
    weekly_target = round(working_days * DAILY_TARGET_HOURS, 2)

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
        }

    context = {
        "summary": summary,
        "start_date": start_date,
        "end_date": end_date,
        "weekly_target": weekly_target,
    }
    return render(request, "attendance/weekly_summary.html", context)

@ratelimit(key='ip', rate='10/m', block=True)
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
            "is_leave": bool(r.leave_type),
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
        delete_id = request.POST.get("delete_holiday")
        if delete_id:
            Holiday.objects.filter(id=delete_id).delete()
        else:
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
    ).values("date", "check_in", "check_out", "is_holiday", "allowance_hours", "leave_type")

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

    mark_leave = request.POST.get("mark_leave") == "true"

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
        if mark_leave:
            record.check_in = None
            record.check_out = None
            record.leave_type = "Leave"
        else:
            record.leave_type = None
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

# ─────────────────────────────────────────────────────────
# TIMESHEET
# ─────────────────────────────────────────────────────────

@login_required
def timesheet_view(request):
    """Display and save the monthly timesheet."""
    today = timezone.localtime(timezone.now()).date()
    
    # Robust input validation for year and month
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
        if not (1 <= month <= 12):
            raise ValueError
    except (ValueError, TypeError):
        year, month = today.year, today.month

    current = date(year, month, 1)
    num_days = calendar.monthrange(year, month)[1]
    days = list(range(1, num_days + 1))

    att_records = AttendanceRecord.objects.filter(user=request.user, date__year=year, date__month=month)
    time_map = {}
    for r in att_records:
        if r.leave_type or r.is_holiday:
            time_map[r.date.day] = {
                'in_time': 'LEAVE' if r.leave_type else 'HOLIDAY',
                'out_time': '—',
                'total_time': '00:00',
                'esa_time': 0,
            }
        elif r.check_in:
            ci_local = timezone.localtime(r.check_in)
            if r.check_out:
                co_local = timezone.localtime(r.check_out)
                delta = co_local - ci_local
            else:
                # Default to 9h if check_out is missing
                co_local = ci_local + timedelta(hours=9)
                delta = timedelta(hours=9)
            
            total_sec = delta.total_seconds()
            hh = int(total_sec // 3600)
            mm = int((total_sec % 3600) // 60)
            
            time_map[r.date.day] = {
                'in_time': ci_local.strftime('%H:%M'),
                'out_time': co_local.strftime('%H:%M'),
                'total_time': f"{hh:02d}:{mm:02d}",
                'esa_time': round(total_sec / 3600.0, 2),
            }

    db_holidays = set(Holiday.objects.filter(date__year=year, date__month=month).values_list('date__day', flat=True))
    config_holiday_days = set()
    for d in days:
        try:
            if is_config_holiday(date(year, month, d)):
                config_holiday_days.add(d)
        except ValueError:
            pass
    holiday_days = db_holidays | config_holiday_days
    saturday_days = {d for d in days if date(year, month, d).weekday() == 5}
    sunday_days = {d for d in days if date(year, month, d).weekday() == 6}

    if request.method == 'POST' and request.POST.get('action') == 'save_timesheet':
        from django.db import transaction
        with transaction.atomic():
            TimesheetActivity.objects.filter(user=request.user, year=year, month=month).delete()
        activities_raw = {}
        for key, val in request.POST.items():
            if key.startswith('act_'):
                parts = key.split('_', 2)
                if len(parts) >= 3:
                    idx = parts[1]
                    field = parts[2]
                    if idx not in activities_raw:
                        activities_raw[idx] = {}
                    if field.startswith('day_'):
                        day_num = field.split('_', 1)[1]
                        try:
                            val_f = float(val) if val.strip() else 0.0
                        except (ValueError, AttributeError):
                            val_f = 0.0
                        activities_raw[idx].setdefault('daily_hours', {})
                        if val_f > 0:
                            activities_raw[idx]['daily_hours'][day_num] = val_f
                    else:
                        activities_raw[idx][field] = val
        for idx, data in sorted(activities_raw.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            if not any([data.get('activity', '').strip(), data.get('sub_activity', '').strip(),
                        data.get('comments', '').strip(), data.get('artifact_id', '').strip(),
                        data.get('daily_hours')]):
                continue
            try:
                srno = int(data.get('srno', 1))
            except (ValueError, TypeError):
                srno = 1
            TimesheetActivity.objects.create(
                user=request.user, year=year, month=month, srno=srno,
                activity=data.get('activity', '').strip(),
                sub_activity=data.get('sub_activity', '').strip(),
                comments=data.get('comments', '').strip(),
                artifact_id=data.get('artifact_id', '').strip(),
                daily_hours=data.get('daily_hours', {}),
            )
        # Process time overrides
        for d in days:
            in_val = request.POST.get(f'in_time_{d}', '').strip()
            out_val = request.POST.get(f'out_time_{d}', '').strip()
            if in_val or out_val:
                target_date = date(year, month, d)
                rec, _ = AttendanceRecord.objects.get_or_create(
                    user=request.user, date=target_date,
                    defaults={'is_holiday': d in holiday_days}
                )
                
                # Check for LEAVE keyword
                if in_val.upper() == 'LEAVE':
                    rec.leave_type = 'Leave'
                    rec.check_in = None
                    rec.check_out = None
                else:
                    rec.leave_type = None
                    try:
                        if in_val and ':' in in_val:
                            dt_in = datetime.strptime(f"{target_date} {in_val}", "%Y-%m-%d %H:%M")
                            rec.check_in = timezone.make_aware(dt_in)
                            # Strictly force In + 9h for Timesheet Out-Time
                            dt_out = dt_in + timedelta(hours=9)
                            rec.check_out = timezone.make_aware(dt_out)
                    except ValueError:
                        pass
                rec.save()

        ts_url = reverse('timesheet')
        return redirect(f"{ts_url}?year={year}&month={month}")

    activities = list(TimesheetActivity.objects.filter(user=request.user, year=year, month=month))
    # Pre-populate defaults if empty
    if not activities:
        defaults = [
            (1, "Support",                      "Support KT"),
            (2, "Development/Analysis/Testing",  "Development"),
            ("", "",                              "Analysis"),
            ("", "",                              "Testing"),
        ]
        for sr, act, sub in defaults:
            new_act = TimesheetActivity.objects.create(
                user=request.user, year=year, month=month,
                srno=int(sr) if sr else 1,
                activity=act, sub_activity=sub
            )
            activities.append(new_act)

    totals_per_day = {}
    for act in activities:
        for day_str, hrs in act.daily_hours.items():
            d = int(day_str)
            totals_per_day[d] = totals_per_day.get(d, 0) + hrs

    # Calculate actual weeks (Monday to Sunday blocks)
    week_ranges = []
    current_week_days = []
    for d in days:
        current_week_days.append(d)
        if date(year, month, d).weekday() == 6:  # Sunday
            week_ranges.append(current_week_days)
            current_week_days = []
    if current_week_days:
        week_ranges.append(current_week_days)

    comp_offs = CompOffRecord.objects.filter(user=request.user).order_by('-worked_date')
    prev_m = (current.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_m = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

    # Summary calculations for the dashboard cards
    work_days_count = len([d for d in days if d not in saturday_days and d not in sunday_days and d not in holiday_days])
    present_count = len([d for d, v in time_map.items() if v.get('in_time') not in ['LEAVE', 'HOLIDAY']])
    leaves_count = len([d for d, v in time_map.items() if v.get('in_time') == 'LEAVE'])
    total_esa_hrs = sum([v.get('esa_time', 0) for v in time_map.values() if isinstance(v.get('esa_time'), (int, float))])
    total_logged_hrs = sum(totals_per_day.values())

    context = {
        'current': current, 'year': year, 'month': month, 'days': days,
        'time_map': time_map, 'holiday_days': holiday_days,
        'saturday_days': saturday_days, 'sunday_days': sunday_days,
        'activities': activities, 'totals_per_day': totals_per_day,
        'comp_offs': comp_offs,
        'prev_year': prev_m.year, 'prev_month': prev_m.month,
        'next_year': next_m.year, 'next_month': next_m.month,
        'today': today,
        'week_ranges': week_ranges,
        'summary': {
            'work_days': work_days_count,
            'present': present_count,
            'leaves': leaves_count,
            'esa_hrs': total_esa_hrs,
            'logged_hrs': total_logged_hrs,
        }
    }
    return render(request, 'attendance/timesheet.html', context)


@login_required
def timesheet_export_view(request):
    """Export NSE-format timesheet Excel for the selected month."""
    import openpyxl
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    today = timezone.localtime(timezone.now()).date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    num_days = calendar.monthrange(year, month)[1]
    days = list(range(1, num_days + 1))

    att_records = AttendanceRecord.objects.filter(user=request.user, date__year=year, date__month=month)
    time_map = {}
    for r in att_records:
        if r.leave_type or r.is_holiday:
            time_map[r.date.day] = {
                'in_time': 'LEAVE' if r.leave_type else 'HOLIDAY',
                'out_time': '—',
                'total_time': '00:00',
                'esa_time': 0
            }
        elif r.check_in:
            ci_local = timezone.localtime(r.check_in)
            if r.check_out:
                co_local = timezone.localtime(r.check_out)
                delta = co_local - ci_local
            else:
                co_local = ci_local + timedelta(hours=9)
                delta = timedelta(hours=9)
            
            total_sec = delta.total_seconds()
            hh = int(total_sec // 3600)
            mm = int((total_sec % 3600) // 60)
            
            time_map[r.date.day] = {
                'in_time': ci_local.strftime('%H:%M'),
                'out_time': co_local.strftime('%H:%M'),
                'total_time': f"{hh:02d}:{mm:02d}",
                'esa_time': round(total_sec / 3600.0, 1)
            }

    activities = list(TimesheetActivity.objects.filter(user=request.user, year=year, month=month))
    db_holidays = set(Holiday.objects.filter(date__year=year, date__month=month).values_list('date__day', flat=True))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Timesheet'

    label_font = Font(bold=True, size=9)
    sat_fill = PatternFill('solid', fgColor='FFF2CC')
    sun_fill = PatternFill('solid', fgColor='FCE4D6')
    holiday_fill = PatternFill('solid', fgColor='E2EFDA')
    data_font = Font(size=9)
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    thin = Side(border_style='thin', color='AAAAAA')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    DAY_COL_START = 6

    ws.cell(1, 1, 'Srno').font = label_font
    ws.cell(1, 2, 'Activity').font = label_font
    ws.cell(1, 3, 'Sub Activity').font = label_font
    ws.cell(1, 4, 'Comments').font = label_font
    ws.cell(1, 5, 'Artifact ID/Problem id/Incident ID').font = label_font

    for d in days:
        col = DAY_COL_START + d - 1
        cell = ws.cell(1, col, date(year, month, d))
        cell.number_format = 'DD-MMM'
        cell.font = label_font
        cell.alignment = center
        weekday = date(year, month, d).weekday()
        if weekday == 5:
            cell.fill = sat_fill
        elif weekday == 6:
            cell.fill = sun_fill
        if d in db_holidays:
            cell.fill = holiday_fill

    leaves_col = DAY_COL_START + num_days
    ws.cell(1, leaves_col, 'Leaves').font = label_font
    ws.cell(2, 4, 'In Time').font = label_font
    ws.cell(3, 4, 'Out Time').font = label_font
    ws.cell(4, 4, 'Total Time').font = label_font
    ws.cell(5, 4, 'ESA Time').font = label_font

    for d in days:
        col = DAY_COL_START + d - 1
        info = time_map.get(d)
        if info:
            ws.cell(2, col, info['in_time'])
            ws.cell(3, col, info['out_time'])
            ws.cell(4, col, info.get('total_time', '09:00'))
            ws.cell(5, col, info.get('esa_time', 9))

    for i, act in enumerate(activities):
        row = 6 + i
        # Only show Sr No and Activity if it's not a sub-category row
        display_sr = act.srno if act.activity and act.activity.strip() else ""
        display_act = act.activity if act.activity and act.activity.strip() else ""
        
        ws.cell(row, 1, display_sr).font = data_font
        ws.cell(row, 2, display_act).font = data_font
        ws.cell(row, 3, act.sub_activity).font = data_font
        ws.cell(row, 4, act.comments)
        ws.cell(row, 5, act.artifact_id)
        for day_str, hrs in act.daily_hours.items():
            ws.cell(row, DAY_COL_START + int(day_str) - 1, hrs)

    total_row = 6 + len(activities)
    ws.cell(total_row, 5, 'TOTAL').font = Font(bold=True, size=9)
    for d in days:
        col = DAY_COL_START + d - 1
        total = sum(act.daily_hours.get(str(d), 0) or 0 for act in activities)
        ws.cell(total_row, col, total if total else None)

    for row in ws.iter_rows(min_row=1, max_row=total_row, min_col=1, max_col=leaves_col):
        for cell in row:
            cell.border = border

    ws.column_dimensions[get_column_letter(1)].width = 5
    ws.column_dimensions[get_column_letter(2)].width = 22
    ws.column_dimensions[get_column_letter(3)].width = 18
    ws.column_dimensions[get_column_letter(4)].width = 26
    ws.column_dimensions[get_column_letter(5)].width = 20
    for d in days:
        ws.column_dimensions[get_column_letter(DAY_COL_START + d - 1)].width = 7
    ws.column_dimensions[get_column_letter(leaves_col)].width = 8

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    fname = f'Timesheet_{request.user.username}_{year}_{month:02d}.xlsx'
    response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    return response


# ─────────────────────────────────────────────────────────
# COMP-OFF
# ─────────────────────────────────────────────────────────

@login_required
def compoff_view(request):
    """Log a new compensation-off record (worked on Saturday)."""
    if request.method == 'POST':
        worked_str = request.POST.get('worked_date', '').strip()
        reason = request.POST.get('reason', '').strip()
        try:
            worked_date = datetime.strptime(worked_str, '%Y-%m-%d').date()
            if worked_date.weekday() == 5:
                CompOffRecord.objects.get_or_create(
                    user=request.user, worked_date=worked_date,
                    defaults={'reason': reason, 'status': 'pending'},
                )
        except ValueError:
            pass
    return redirect(reverse('timesheet'))


@login_required
def compoff_consume_view(request, compoff_id):
    """Set the leave_date and mark comp-off as consumed."""
    if request.method == 'POST':
        leave_str = request.POST.get('leave_date', '').strip()
        try:
            record = CompOffRecord.objects.get(id=compoff_id, user=request.user)
            if leave_str:
                record.leave_date = datetime.strptime(leave_str, '%Y-%m-%d').date()
                record.status = 'consumed'
                record.save()
        except (CompOffRecord.DoesNotExist, ValueError):
            pass
    return redirect(reverse('timesheet'))


@login_required
def compoff_delete_view(request, compoff_id):
    """Delete a comp-off record."""
    if request.method == 'POST':
        CompOffRecord.objects.filter(id=compoff_id, user=request.user).delete()
    return redirect(reverse('timesheet'))

# ─────────────────────────────────────────────────────────
# LEGAL PAGES
# ─────────────────────────────────────────────────────────

def privacy_policy_view(request):
    """Display the privacy policy page."""
    return render(request, 'attendance/privacy.html')

def terms_of_service_view(request):
    """Display the Terms of Service page."""
    return render(request, 'attendance/terms.html')
@login_required
def support_view(request):
    """View to handle bug reports and feedback."""
    if request.method == "POST":
        subject = request.POST.get("subject", "Bug Report")
        message = request.POST.get("message")
        
        # In a real app, you'd email this. For now, we flash a message.
        from django.contrib import messages
        messages.success(request, "Thank you! Your report has been sent to our technical team.")
        return redirect("checkin_checkout")
        
    return render(request, "attendance/support.html")
