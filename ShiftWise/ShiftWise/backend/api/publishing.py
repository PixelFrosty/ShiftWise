"""Draft / posted weeks. A department's week is a draft until a manager posts it; employees only see posted weeks."""
import datetime

from django.db.models import Exists, OuterRef, Q

from .models import Schedule, SchedulePublication, Shift


def monday_of(day):
    return day - datetime.timedelta(days=day.weekday())


def published_shifts(queryset):
    """Only the shifts whose department-week has been posted."""
    return queryset.filter(Exists(SchedulePublication.objects.filter(
        department_id=OuterRef('department_id'), week_start=OuterRef('week_start'))))


def published_schedules(queryset):
    """Assignment rows an employee may see: not tied to a shift, or tied to a posted one."""
    return queryset.filter(Q(shift__isnull=True) | Q(shift__in=published_shifts(Shift.objects.all())))


def get_publication(department_id, week_start):
    return SchedulePublication.objects.filter(department_id=department_id, week_start=week_start
                                              ).select_related('published_by').first()


def is_posted(department_id, week_start):
    return SchedulePublication.objects.filter(department_id=department_id, week_start=week_start).exists()
