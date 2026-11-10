"""Hours of operation, shifts (with how many people each needs), shift templates and shift requests."""

import datetime

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import access, publishing, scheduling, services
from .models import (Department, EmployeeProfile, Notification, Schedule, SchedulePublication, Shift, ShiftRequest,
                     ShiftTemplate, TimeOffRequest)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Conflict.'
    default_code = 'conflict'


# --- small helpers ---------------------------------------------------------------------------

def hhmm(t):
    return t.strftime('%H:%M')


def pretty_time(t):
    hour = t.hour % 12 or 12
    suffix = 'AM' if t.hour < 12 else 'PM'
    return f'{hour}:{t.minute:02d} {suffix}' if t.minute else f'{hour} {suffix}'


def pretty_range(start, end):
    return f'{pretty_time(start)} - {pretty_time(end)}'


def when(schedule):
    day = schedule.shift_date
    return f'{day:%a} {day:%b} {day.day}, {pretty_range(schedule.start_time, schedule.end_time)}'


def hours_text(company):
    return pretty_range(company.open_time, company.close_time)


def check_within_hours(company, start, end, allow=False, strict=True):
    """Validate a time range against the hours of operation; returns True when it lies outside them.

    Outside hours is an error (400) for templates (strict). For shifts it asks for confirmation (409
    outside_hours) unless the caller passes allow_outside_hours, in which case it is accepted.
    """
    if end <= start:
        raise ValidationError({'end_time': 'The end time must be after the start time.'})
    if start < company.open_time or end > company.close_time:
        if allow:
            return True
        if strict:
            raise ValidationError({'start_time': f'Shifts must fall within the hours of operation ({hours_text(company)}).'})
        raise Conflict({'code': 'outside_hours',
                        'detail': f'This shift is outside the hours of operation ({hours_text(company)}). '
                                  'Are you sure you want to schedule it?'})
    return False


def approved_time_off(employee, day):
    return TimeOffRequest.objects.filter(employee=employee, status=TimeOffRequest.Status.APPROVED,
                                         start_date__lte=day, end_date__gte=day).exists()


def overlapping(employee, day, start, end, exclude=()):
    return (Schedule.objects.filter(employee__user=employee.user, shift_date=day, start_time__lt=end, end_time__gt=start)
            .exclude(status=Schedule.Status.CANCELLED).exclude(pk__in=exclude).first())


def notify_managers(department, message):
    """Tell the department's managers what happened (the General Manager if it has none)."""
    managers = list(services.department_manager_profiles(department).select_related('user'))
    users = [m.user for m in managers] or list(services.ceo_users(department.company_id))
    for user in users:
        services.notify(user, Notification.Kind.INFO, message)


def tell_assignee(shift, employee, message, *, was_posted=None):
    """Tell one employee about a change to their shift. Nothing is sent while the week is still a draft, because
    they cannot see it yet. `was_posted` lets a caller pass the state from before its own change."""
    posted = publishing.is_posted(shift.department_id, shift.week_start) if was_posted is None else was_posted
    if posted:
        services.notify(employee.user, Notification.Kind.INFO, message)


def week_label(week_start):
    end = week_start + datetime.timedelta(days=6)
    return f'{week_start:%b} {week_start.day} - {end:%b} {end.day}'


# --- serializers/data ------------------------------------------------------------------------

NOTE_MAX = 500


def assignment_data(schedule, show_note=False):
    user = schedule.employee.user
    return {'id': schedule.id, 'employee_id': schedule.employee_id, 'name': services.display_name(user),
            'is_roster': services.is_roster_user(user),
            'is_minor': scheduling.is_minor(schedule.employee, schedule.shift_date),
            # what the manager / General Manager wants this person to do; only they and the person see it
            'note': schedule.notes if show_note else ''}


def clean_note(value):
    """An optional note: text up to NOTE_MAX characters, blank allowed."""
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValidationError({'note': ['The note must be text.']})
    value = value.strip()
    if len(value) > NOTE_MAX:
        raise ValidationError({'note': [f'Keep the note under {NOTE_MAX} characters.']})
    return value


def shift_data(shift, viewer=None):
    assignments = list(shift.assignments.all())
    can_see_all = viewer is not None and access.can_manage_department(viewer, shift.department_id)
    return {
        'id': shift.id, 'department': {'id': shift.department_id, 'name': shift.department.name},
        'name': shift.name, 'shift_date': shift.shift_date.isoformat(),
        'start_time': hhmm(shift.start_time), 'end_time': hhmm(shift.end_time),
        'headcount': shift.headcount, 'outside_hours': shift.outside_hours, 'open_count': max(shift.headcount - len(assignments), 0),
        'assignments': [assignment_data(a, can_see_all or (viewer is not None and viewer.pk == a.employee_id))
                        for a in sorted(assignments, key=lambda a: a.id)],
    }


def template_data(t):
    return {'id': t.id, 'name': t.name, 'start_time': hhmm(t.start_time), 'end_time': hhmm(t.end_time),
            'headcount': t.headcount, 'created_by': services.display_name(t.created_by) if t.created_by else None}


def schedule_brief(schedule):
    return {'id': schedule.id, 'shift_date': schedule.shift_date.isoformat(), 'start_time': hhmm(schedule.start_time),
            'end_time': hhmm(schedule.end_time), 'label': when(schedule),
            'department': schedule.shift.department.name if schedule.shift else ''}


def request_data(sr):
    return {
        'id': sr.id, 'kind': sr.kind, 'status': sr.status,
        'requester': {'id': sr.requester_id, 'name': services.display_name(sr.requester.user)},
        'target': {'id': sr.target_id, 'name': services.display_name(sr.target.user)} if sr.target_id else None,
        'schedule': schedule_brief(sr.schedule),
        'other_schedule': schedule_brief(sr.other_schedule) if sr.other_schedule else None,
        'created_at': sr.created_at, 'resolved_at': sr.resolved_at,
    }


class ShiftWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    shift_date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    headcount = serializers.IntegerField(min_value=1, max_value=100)


# --- hours of operation ----------------------------------------------------------------------

def company_data(company):
    return {'id': company.id, 'name': company.name, 'open_time': hhmm(company.open_time),
            'close_time': hhmm(company.close_time)}


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated, access.HasProfile])
def company(request):
    """Everyone in the company can read the hours; only the General Manager changes them (open_time / close_time)."""
    profile = access.get_profile(request.user)
    comp = profile.company
    if request.method == 'GET':
        return Response(company_data(comp))
    if not access.is_ceo(profile):
        raise PermissionDenied('Only the General Manager can set the hours of operation.')

    class HoursSerializer(serializers.Serializer):
        open_time = serializers.TimeField()
        close_time = serializers.TimeField()

    serializer = HoursSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    opens, closes = serializer.validated_data['open_time'], serializer.validated_data['close_time']
    if closes <= opens:
        raise ValidationError({'close_time': 'Closing time must be after opening time.'})
    outside = Shift.objects.filter(department__company=comp, shift_date__gte=timezone.localdate(),
                                   outside_hours=False).exclude(start_time__gte=opens, end_time__lte=closes).count()
    if outside:
        raise ValidationError({'detail': f'{outside} upcoming shift(s) fall outside those hours. '
                                         'Move or delete them first.'})
    comp.open_time, comp.close_time = opens, closes
    comp.save()
    return Response(company_data(comp))


@api_view(['GET'])
@permission_classes([IsAuthenticated, access.HasProfile])
def coworkers(request):
    """People in one of my departments (?department=<id>, default my home department) who can answer shift
    requests (they have a login)."""
    profile = access.get_profile(request.user)
    department_id = request.query_params.get('department') or profile.department_id
    try:
        department_id = int(department_id)
    except (TypeError, ValueError):
        raise ValidationError({'department': ['Choose one of your departments.']})
    if department_id not in access.member_department_ids(profile):
        raise PermissionDenied('That is not one of your departments.')
    people = access.members_of(department_id).filter(company_id=profile.company_id).exclude(
        pk=profile.pk).select_related('user')
    return Response([{'id': p.id, 'name': services.display_name(p.user)}
                     for p in people if not services.is_roster_user(p.user)])


# --- templates -------------------------------------------------------------------------------

class ShiftTemplateViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, access.StaffOnly]

    def _qs(self, request):
        return ShiftTemplate.objects.filter(company_id=access.get_profile(request.user).company_id)

    def list(self, request):
        return Response([template_data(t) for t in self._qs(request).select_related('created_by')])

    def create(self, request):
        profile = access.get_profile(request.user)
        serializer = ShiftWriteSerializer(data={**request.data, 'shift_date': '2000-01-01'})
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        if not v['name'].strip():
            raise ValidationError({'name': ['Give the shift a name.']})
        check_within_hours(profile.company, v['start_time'], v['end_time'])
        t = ShiftTemplate.objects.create(company=profile.company, name=v['name'].strip(), start_time=v['start_time'],
                                         end_time=v['end_time'], headcount=v['headcount'], created_by=request.user)
        return Response(template_data(t), status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        profile = access.get_profile(request.user)
        t = get_object_or_404(self._qs(request), pk=pk)
        if not access.is_ceo(profile) and t.created_by_id != request.user.id:
            raise PermissionDenied('Only the General Manager or the person who made a template can delete it.')
        t.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- shifts ----------------------------------------------------------------------------------

class ShiftViewSet(viewsets.ViewSet):
    """
    Employees see the shifts of their own department, but only for weeks a manager has posted. Managers and the General Manager can see every
    department's shifts and who is on them, but only change the departments they run (the General Manager: all):
    they create shifts, set how many people are needed, and assign people there.
    List filters: ?department=<id> ?date_from=YYYY-MM-DD ?date_to=YYYY-MM-DD
    """
    permission_classes = [IsAuthenticated, access.HasProfile]

    def _profile(self, request):
        return access.get_profile(request.user)

    def _qs(self, request):
        profile = self._profile(request)
        qs = Shift.objects.filter(department__company_id=profile.company_id)
        if not access.is_staff_role(profile):   # staff can look at every department (view only outside theirs)
            # employees only see their own department's posted weeks; drafts are for managers
            qs = publishing.published_shifts(qs.filter(department_id__in=access.visible_department_ids(profile)))
        return qs.select_related('department').prefetch_related('assignments__employee__user')

    def _manageable(self, request, pk):
        shift = get_object_or_404(self._qs(request), pk=pk)
        if not access.can_manage_department(self._profile(request), shift.department_id):
            raise PermissionDenied('You do not manage this department.')
        return shift

    def _staff(self, request):
        if not access.is_staff_role(self._profile(request)):
            raise PermissionDenied('Only managers and the General Manager can change the schedule.')

    def list(self, request):
        qs = self._qs(request)
        params = request.query_params
        try:
            if 'department' in params:
                qs = qs.filter(department_id=int(params['department']))
            for key, lookup in (('date_from', 'shift_date__gte'), ('date_to', 'shift_date__lte')):
                if key in params:
                    value = parse_date(params[key])
                    if value is None:
                        raise ValueError
                    qs = qs.filter(**{lookup: value})
        except ValueError:
            raise ValidationError('Invalid filter value.')
        return Response([shift_data(s, self._profile(request)) for s in qs])

    def create(self, request):
        self._staff(request)
        profile = self._profile(request)
        serializer = ShiftWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            department = Department.objects.get(pk=int(request.data.get('department')), company_id=profile.company_id)
        except (TypeError, ValueError, Department.DoesNotExist):
            raise ValidationError({'department': ['Choose a department from this company.']})
        if not access.can_manage_department(profile, department.pk):
            raise PermissionDenied('You do not manage that department.')
        outside = check_within_hours(profile.company, v['start_time'], v['end_time'],
                                     allow=request.data.get('allow_outside_hours') is True, strict=False)
        shift = Shift.objects.create(department=department, created_by=request.user, outside_hours=outside,
                                     **{**v, 'name': v['name'].strip()})
        return Response(shift_data(self._qs(request).get(pk=shift.pk), self._profile(request)), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        shift = self._manageable(request, pk)
        merged = {'name': shift.name, 'shift_date': shift.shift_date, 'start_time': shift.start_time,
                  'end_time': shift.end_time, 'headcount': shift.headcount}
        serializer = ShiftWriteSerializer(data={**{k: (v.isoformat() if hasattr(v, 'isoformat') else v)
                                                   for k, v in merged.items()}, **request.data})
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        profile = self._profile(request)
        outside = check_within_hours(profile.company, v['start_time'], v['end_time'],
                                     allow=request.data.get('allow_outside_hours') is True, strict=False)
        assigned = list(shift.assignments.select_related('employee__user'))
        before = (shift.shift_date, shift.start_time, shift.end_time)
        was_posted = publishing.is_posted(shift.department_id, shift.week_start)
        if v['headcount'] < len(assigned):
            raise ValidationError({'headcount': [f'{len(assigned)} people are already assigned. Remove someone first.']})
        with transaction.atomic():
            for a in assigned:
                clash = overlapping(a.employee, v['shift_date'], v['start_time'], v['end_time'], exclude=[a.pk])
                if clash:
                    raise ValidationError({'detail': f'{services.display_name(a.employee.user)} already works '
                                                     f'{when(clash)}, which overlaps the new time.'})
            for field, value in v.items():
                setattr(shift, field, value.strip() if field == 'name' else value)
            shift.outside_hours = outside
            shift.save()
            for a in assigned:
                a.task_name = shift.name or 'Shift'
                a.shift_date, a.start_time, a.end_time = shift.shift_date, shift.start_time, shift.end_time
                a.save()
        if (shift.shift_date, shift.start_time, shift.end_time) != before:
            for a in assigned:
                tell_assignee(shift, a.employee, f'Your {shift.department.name} shift changed. It is now {when(a)}.',
                              was_posted=was_posted)
        return Response(shift_data(self._qs(request).get(pk=shift.pk), self._profile(request)))

    def destroy(self, request, pk=None):
        shift = self._manageable(request, pk)
        was_posted = publishing.is_posted(shift.department_id, shift.week_start)
        for a in shift.assignments.select_related('employee__user'):
            tell_assignee(shift, a.employee, f'Your {shift.department.name} shift on {when(a)} was cancelled.',
                          was_posted=was_posted)
        shift.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Body: {employee: <profile id>, confirm_time_off: true?}. 409 if the person has approved time off."""
        shift = self._manageable(request, pk)
        try:
            employee = EmployeeProfile.objects.select_related('user').get(
                pk=int(request.data.get('employee')), company_id=shift.department.company_id)
        except (TypeError, ValueError, EmployeeProfile.DoesNotExist):
            raise ValidationError({'employee': ['Choose someone from this company.']})
        name = services.display_name(employee.user)
        if shift.department_id not in access.member_department_ids(employee):
            raise ValidationError({'employee': [f'{name} is not in the {shift.department.name} department.']})
        note = clean_note(request.data.get('note'))
        with transaction.atomic():
            locked = Shift.objects.select_for_update().get(pk=shift.pk)
            if locked.assignments.filter(employee=employee).exists():
                raise ValidationError({'employee': [f'{name} is already on this shift.']})
            if locked.assignments.count() >= locked.headcount:
                raise ValidationError({'detail': 'This shift is full. Raise the number of people needed first.'})
            clash = overlapping(employee, locked.shift_date, locked.start_time, locked.end_time)
            if clash:
                raise ValidationError({'detail': f'{name} already works {when(clash)}.'})
            if approved_time_off(employee, locked.shift_date) and request.data.get('confirm_time_off') is not True:
                raise Conflict({'code': 'time_off_approved', 'employee_name': name,
                                'detail': f"{name}'s request off was approved, are you sure you would like to schedule them?"})
            warnings = scheduling.assignment_warnings(employee, name, locked.shift_date, locked.start_time, locked.end_time)
            outside = scheduling.availability_warning(employee, name, locked.shift_date, locked.start_time, locked.end_time)
            if outside:
                warnings.insert(0, outside)
            if warnings and request.data.get('confirm_warnings') is not True:
                raise Conflict({'code': 'schedule_warning', 'employee_name': name, 'warnings': warnings,
                                'detail': ' '.join(warnings) + ' Are you sure you would like to schedule them?'})
            created = Schedule.objects.create(task_name=locked.name or 'Shift', employee=employee, shift_date=locked.shift_date,
                                              start_time=locked.start_time, end_time=locked.end_time, shift=locked, notes=note)
            tell_assignee(locked, employee, f'You were scheduled for a {locked.department.name} shift: {when(created)}.')
        return Response(shift_data(self._qs(request).get(pk=shift.pk), self._profile(request)))

    # --- draft / post -------------------------------------------------------------------------

    def _department_week(self, request, data, manage):
        """The (department, Monday) named by `data`. With manage=True the caller must run that department."""
        profile = self._profile(request)
        try:
            department = Department.objects.get(pk=int(data.get('department')), company_id=profile.company_id)
        except (TypeError, ValueError, Department.DoesNotExist):
            raise ValidationError({'department': ['Choose a department from this company.']})
        day = parse_date(str(data.get('week_start'))) if data.get('week_start') else None
        if day is None:
            raise ValidationError({'week_start': ['Enter the week as YYYY-MM-DD.']})
        if manage:
            self._staff(request)
            if not access.can_manage_department(profile, department.pk):
                raise PermissionDenied('You do not manage this department.')
        elif not access.is_staff_role(profile) and department.pk not in access.visible_department_ids(profile):
            raise PermissionDenied('That is not your department.')
        return department, publishing.monday_of(day)

    @staticmethod
    def _publication_data(department, monday, publication):
        return {'department': {'id': department.id, 'name': department.name}, 'week_start': monday.isoformat(),
                'published': publication is not None,
                'published_at': publication.published_at.isoformat() if publication else None,
                'published_by': (services.display_name(publication.published_by)
                                 if publication and publication.published_by else None)}

    @action(detail=False, methods=['get'])
    def publication(self, request):
        """?department=<id>&week_start=YYYY-MM-DD: is that week posted? Anyone who can see the department may ask."""
        department, monday = self._department_week(request, request.query_params, manage=False)
        return Response(self._publication_data(department, monday, publishing.get_publication(department.pk, monday)))

    @action(detail=False, methods=['get'])
    def review(self, request):
        """?department=<id>&week_start=YYYY-MM-DD. What a manager looks over before posting the week."""
        department, monday = self._department_week(request, request.query_params, manage=True)
        end = monday + datetime.timedelta(days=6)
        shifts = list(Shift.objects.filter(department=department, shift_date__range=(monday, end))
                      .prefetch_related('assignments__employee__user'))
        slots = sum(s.headcount for s in shifts)
        filled = sum(len(s.assignments.all()) for s in shifts)
        label = lambda s: f'{s.shift_date:%a %b} {s.shift_date.day}, {pretty_range(s.start_time, s.end_time)}'
        open_shifts = [f'{label(s)}{" (" + s.name + ")" if s.name else ""}: {s.headcount - len(s.assignments.all())} open'
                       for s in shifts if len(s.assignments.all()) < s.headcount]
        warnings = [f'{label(s)} is outside the hours of operation.' for s in shifts if s.outside_hours]
        per_person = {}
        for s in shifts:
            for a in s.assignments.all():
                per_person.setdefault(a.employee_id, {'profile': a.employee, 'rows': []})['rows'].append(a)
        people = []
        for entry in sorted(per_person.values(), key=lambda e: services.display_name(e['profile'].user)):
            person, rows = entry['profile'], entry['rows']
            name = services.display_name(person.user)
            hours = sum(scheduling.duration_hours(r.start_time, r.end_time) for r in rows)
            people.append({'name': name, 'hours': round(hours, 2), 'shifts': len(rows)})
            limit = scheduling.weekly_limit(person)
            if limit is not None and hours > limit:
                warnings.append(f'{name} is scheduled {scheduling.fmt_hours(hours)} hours, over their {limit}-hour weekly limit.')
            for r in rows:
                outside = scheduling.availability_warning(person, name, r.shift_date, r.start_time, r.end_time)
                if outside:
                    warnings.append(outside)
                if approved_time_off(person, r.shift_date):
                    warnings.append(f'{name} has approved time off on {r.shift_date:%a %b} {r.shift_date.day} but is scheduled.')
            minor_days = {}
            for r in rows:
                if scheduling.is_minor(person, r.shift_date):
                    minor_days[r.shift_date] = minor_days.get(r.shift_date, 0) + scheduling.duration_hours(r.start_time, r.end_time)
                    if r.end_time > scheduling.MINOR_LATEST_END:
                        warnings.append(f'{name} is under 18 and works past 9 PM on {r.shift_date:%a %b} {r.shift_date.day}.')
            for day, h in minor_days.items():
                if h > scheduling.MINOR_DAY_LIMIT:
                    warnings.append(f'{name} is under 18 and works {scheduling.fmt_hours(h)} hours on {day:%a %b} {day.day}.')
            if minor_days and hours > scheduling.MINOR_WEEK_LIMIT:
                warnings.append(f'{name} is under 18 and works {scheduling.fmt_hours(hours)} hours this week.')
        pending = scheduling.pending_time_off(department, monday, end)
        warnings += [f'{services.display_name(t.employee.user)} has a time-off request that is still waiting for an answer.'
                     for t in pending]
        return Response({**self._publication_data(department, monday, publishing.get_publication(department.pk, monday)),
                         'week_label': week_label(monday), 'shift_count': len(shifts), 'slots': slots, 'filled': filled,
                         'open_slots': slots - filled, 'open_shifts': open_shifts, 'warnings': warnings, 'people': people})

    @action(detail=False, methods=['post'])
    def publish(self, request):
        """
        Body: {department, week_start, reviewed: true, confirmed: true}. Posts the week so employees can see it and
        tells everyone who is on it. The two flags are the review step and the final "are you sure", and both must be
        sent, so posting by accident (or by skipping a step) is not possible.
        """
        department, monday = self._department_week(request, request.data, manage=True)
        if request.data.get('reviewed') is not True:
            raise ValidationError({'detail': 'Review the schedule before posting it.', 'code': 'review_required'})
        if request.data.get('confirmed') is not True:
            raise ValidationError({'detail': 'Confirm that you want to post this schedule.', 'code': 'confirmation_required'})
        end = monday + datetime.timedelta(days=6)
        with transaction.atomic():
            shifts = list(Shift.objects.filter(department=department, shift_date__range=(monday, end))
                          .prefetch_related('assignments__employee__user'))
            if not shifts:
                raise ValidationError({'detail': 'There is nothing to post. Add shifts to this week first.'})
            publication, created = SchedulePublication.objects.get_or_create(
                department=department, week_start=monday, defaults={'published_by': request.user})
            if not created:
                raise ValidationError({'detail': 'This week has already been posted.'})
            rows = {}
            for s in shifts:
                for a in s.assignments.all():
                    rows.setdefault(a.employee_id, (a.employee, []))[1].append(a)
            for person, mine in rows.values():
                hours = sum(scheduling.duration_hours(r.start_time, r.end_time) for r in mine)
                services.notify(person.user, Notification.Kind.INFO,
                                f'The {department.name} schedule for {week_label(monday)} was posted. '
                                f'You work {len(mine)} shift{"" if len(mine) == 1 else "s"}, '
                                f'{scheduling.fmt_hours(hours)} hours.')
        return Response(self._publication_data(department, monday, publication), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='auto-schedule')
    def auto_schedule(self, request):
        """
        Body: {department, date_from, date_to, confirm_pending?}. Fills the open spots in that range, best
        productivity first, using compatibility scores. 409 'pending_time_off' while time-off requests for
        that range are still unanswered, until the caller re-sends with confirm_pending: true.
        """
        self._staff(request)
        profile = self._profile(request)
        department = get_object_or_404(Department, pk=request.data.get('department') or 0,
                                       company_id=profile.company_id)
        if not access.can_manage_department(profile, department.pk):
            raise PermissionDenied('You do not manage that department.')
        date_from, date_to = parse_date(str(request.data.get('date_from'))), parse_date(str(request.data.get('date_to')))
        if not date_from or not date_to or date_to < date_from or (date_to - date_from).days > 31:
            raise ValidationError({'detail': 'Choose a valid date range (up to a month).'})
        pending = list(scheduling.pending_time_off(department, date_from, date_to))
        if pending and request.data.get('confirm_pending') is not True:
            return Response({'code': 'pending_time_off', 'count': len(pending),
                             'people': sorted({services.display_name(t.employee.user) for t in pending}),
                             'detail': 'There are still request offs that have not been looked at. Would you like to continue?'},
                            status=status.HTTP_409_CONFLICT)
        with transaction.atomic():
            scheduler = scheduling.AutoScheduler(department, date_from, date_to, lambda p: services.display_name(p.user))
            result = scheduler.run()
            for shift, person in scheduler.created:  # only matters for weeks that are already posted
                tell_assignee(shift, person, f'You were scheduled for a {department.name} shift on '
                                             f'{shift.shift_date:%a %b} {shift.shift_date.day}, '
                                             f'{pretty_range(shift.start_time, shift.end_time)}.')
        return Response(result)

    @action(detail=True, methods=['post'])
    def note(self, request, pk=None):
        """Body: {assignment: <id>, note: "text"}. Sets (or clears, with blank text) what a person on this shift
        should do. Managers of the department and the General Manager only."""
        shift = self._manageable(request, pk)
        assignment = Schedule.objects.filter(shift=shift, pk=request.data.get('assignment')).first()
        if assignment is None:
            raise ValidationError({'assignment': ['That person is not on this shift.']})
        new_note = clean_note(request.data.get('note'))
        changed = new_note != assignment.notes
        assignment.notes = new_note
        assignment.save(update_fields=['notes', 'modified_at'])
        if changed and new_note:
            tell_assignee(shift, assignment.employee, f'A note was added to your shift on {when(assignment)}.')
        return Response(shift_data(self._qs(request).get(pk=shift.pk), self._profile(request)))

    @action(detail=True, methods=['post'])
    def unassign(self, request, pk=None):
        """Body: {assignment: <id from the shift's assignments>}."""
        shift = self._manageable(request, pk)
        assignment = Schedule.objects.filter(shift=shift, pk=request.data.get('assignment')).select_related('employee__user').first()
        if assignment is None:
            raise ValidationError({'assignment': ['That person is not on this shift.']})
        assignment.delete()
        tell_assignee(shift, assignment.employee, f'You were taken off the {shift.department.name} shift on {when(assignment)}.')
        return Response(shift_data(self._qs(request).get(pk=shift.pk), self._profile(request)))

    @action(detail=False, methods=['post'], url_path='apply-template')
    def apply_template(self, request):
        """Body: {template: <id>, department: <id>, dates: ['YYYY-MM-DD', ...]}"""
        self._staff(request)
        profile = self._profile(request)
        template = get_object_or_404(ShiftTemplate, pk=request.data.get('template') or 0, company_id=profile.company_id)
        try:
            department = Department.objects.get(pk=int(request.data.get('department')), company_id=profile.company_id)
        except (TypeError, ValueError, Department.DoesNotExist):
            raise ValidationError({'department': ['Choose a department from this company.']})
        if not access.can_manage_department(profile, department.pk):
            raise PermissionDenied('You do not manage that department.')
        dates = {parse_date(str(d)) if isinstance(d, str) else None for d in (request.data.get('dates') or [])}
        if not dates or None in dates:
            raise ValidationError({'dates': ['Choose at least one valid day.']})
        outside = check_within_hours(profile.company, template.start_time, template.end_time,
                                     allow=request.data.get('allow_outside_hours') is True, strict=False)
        created = []
        with transaction.atomic():
            for day in sorted(dates):
                duplicate = Shift.objects.filter(department=department, shift_date=day, start_time=template.start_time,
                                                 end_time=template.end_time, name=template.name).exists()
                if not duplicate:
                    created.append(Shift.objects.create(
                        department=department, name=template.name, shift_date=day, start_time=template.start_time,
                        end_time=template.end_time, headcount=template.headcount, outside_hours=outside,
                        created_by=request.user))
        return Response({'created': len(created), 'skipped': len(dates) - len(created)},
                        status=status.HTTP_201_CREATED)


# --- shift requests (give away / take / swap) ------------------------------------------------

class ShiftRequestViewSet(viewsets.ViewSet):
    """Requests between coworkers. Only the person being asked has to accept; managers are just told."""
    permission_classes = [IsAuthenticated, access.HasProfile]

    def _qs(self):
        return ShiftRequest.objects.select_related('requester__user', 'target__user', 'schedule__shift__department',
                                                   'other_schedule__shift__department')

    def _mine(self, request):
        profile = access.get_profile(request.user)
        mine = self._qs().filter(requester=profile) | self._qs().filter(target=profile)
        if profile.role == EmployeeProfile.Role.EMPLOYEE:   # offers to the whole department are everyone's to see
            mine = mine | self._qs().filter(kind=ShiftRequest.Kind.OFFER,
                                            schedule__shift__department_id__in=access.member_department_ids(profile))
        return mine

    def list(self, request):
        return Response([request_data(s) for s in self._mine(request)[:50]])

    @staticmethod
    def _schedule(pk, company_id):
        try:
            schedule = Schedule.objects.select_related('employee__user', 'shift__department').get(
                pk=int(pk), employee__company_id=company_id, shift__isnull=False, status=Schedule.Status.SCHEDULED)
        except (TypeError, ValueError, Schedule.DoesNotExist):
            raise ValidationError({'schedule': ['That shift could not be found.']})
        if schedule.shift_date < timezone.localdate():
            raise ValidationError({'schedule': ['That shift is in the past.']})
        if not publishing.is_posted(schedule.shift.department_id, schedule.shift.week_start):
            raise ValidationError({'schedule': ['That week has not been posted yet.']})
        return schedule

    @staticmethod
    def _check_can_work(employee, schedule, leaving=()):
        """Could `employee` take `schedule`? `leaving` are the schedule ids they would hand over."""
        name = services.display_name(employee.user)
        if approved_time_off(employee, schedule.shift_date):
            raise ValidationError({'detail': f'{name} has approved time off on {schedule.shift_date:%a %b} '
                                             f'{schedule.shift_date.day}.'})
        clash = overlapping(employee, schedule.shift_date, schedule.start_time, schedule.end_time,
                            exclude=[schedule.pk, *leaving])
        if clash:
            raise ValidationError({'detail': f'{name} already works {when(clash)}.'})

    def _validate_pairing(self, kind, me, schedule, other, target):
        """Check the ownership/department/time rules for a request. Returns the person who must answer it."""
        if kind == ShiftRequest.Kind.GIVE:
            if schedule.employee_id != me.pk:
                raise ValidationError({'schedule': ['You can only give away your own shift.']})
            if target is None or target.pk == me.pk or target.company_id != me.company_id:
                raise ValidationError({'to_employee': ['Choose a coworker.']})
            if schedule.shift.department_id not in access.member_department_ids(target):
                raise ValidationError({'to_employee': ['They are not in this shift\'s department.']})
            self._check_can_work(target, schedule)
            return target
        if kind == ShiftRequest.Kind.TAKE:
            if schedule.employee_id == me.pk:
                raise ValidationError({'schedule': ['That is already your shift.']})
            if schedule.shift.department_id not in access.member_department_ids(me):
                raise ValidationError({'schedule': ['You can only take shifts in your own department.']})
            self._check_can_work(me, schedule)
            return schedule.employee
        # swap
        if schedule.employee_id != me.pk or other is None or other.employee_id == me.pk:
            raise ValidationError({'schedule': ['Pick one of your shifts and a coworker\'s shift to swap.']})
        if schedule.shift.department_id != other.shift.department_id:
            raise ValidationError({'other_schedule': ['Both shifts must be in the same department.']})
        self._check_can_work(other.employee, schedule, leaving=[other.pk])
        self._check_can_work(me, other, leaving=[schedule.pk])
        return other.employee

    def create(self, request):
        me = access.get_profile(request.user)
        data = request.data
        kind = data.get('kind')
        if kind not in ShiftRequest.Kind.values:
            raise ValidationError({'kind': ['Choose give, take, swap or offer.']})
        schedule = self._schedule(data.get('schedule'), me.company_id)
        if kind == ShiftRequest.Kind.OFFER:
            return self._offer(request, me, schedule)
        other = self._schedule(data.get('other_schedule'), me.company_id) if kind == 'swap' else None
        target = None
        if kind == 'give':
            try:
                target = EmployeeProfile.objects.select_related('user').get(pk=int(data.get('to_employee')))
            except (TypeError, ValueError, EmployeeProfile.DoesNotExist):
                raise ValidationError({'to_employee': ['Choose a coworker.']})
        answerer = self._validate_pairing(kind, me, schedule, other, target)
        if services.is_roster_user(answerer.user):
            raise ValidationError({'detail': f'{services.display_name(answerer.user)} has no login, so they cannot '
                                             'answer. Ask your manager instead.'})
        busy = ShiftRequest.objects.filter(status=ShiftRequest.Status.PENDING).filter(
            schedule__in=[schedule, *( [other] if other else [])]) | ShiftRequest.objects.filter(
            status=ShiftRequest.Status.PENDING, other_schedule__in=[schedule, *([other] if other else [])])
        if busy.exists():
            raise ValidationError({'detail': 'There is already a pending request for one of those shifts.'})
        with transaction.atomic():
            sr = ShiftRequest.objects.create(kind=kind, requester=me, target=answerer, schedule=schedule,
                                             other_schedule=other)
            who = services.display_name(request.user)
            if kind == 'give':
                text = f'{who} asked you to take their shift on {when(schedule)}.'
            elif kind == 'take':
                text = f'{who} asked to take your shift on {when(schedule)}.'
            else:
                text = (f'{who} asked to swap their shift on {when(schedule)} for your shift on {when(other)}.')
            note = services.notify(answerer.user, Notification.Kind.SHIFT_REQUEST, text)
            if note:
                note.shift_request = sr
                note.save(update_fields=['shift_request'])
        return Response(request_data(self._qs().get(pk=sr.pk)), status=status.HTTP_201_CREATED)

    def _offer(self, request, me, schedule):
        """Give up my shift to the whole department: everyone else in it gets a notification and the first to
        accept takes it."""
        if schedule.employee_id != me.pk:
            raise ValidationError({'schedule': ['You can only give away your own shift.']})
        department = schedule.shift.department
        people = [p for p in access.members_of(department.pk).filter(
                      company_id=me.company_id, role=EmployeeProfile.Role.EMPLOYEE
                  ).exclude(pk=me.pk).select_related('user') if not services.is_roster_user(p.user)]
        if not people:
            raise ValidationError({'detail': 'There is nobody else in this department to offer the shift to.'})
        if ShiftRequest.objects.filter(status=ShiftRequest.Status.PENDING).filter(
                Q(schedule=schedule) | Q(other_schedule=schedule)).exists():
            raise ValidationError({'detail': 'There is already a pending request for that shift.'})
        who = services.display_name(request.user)
        with transaction.atomic():
            sr = ShiftRequest.objects.create(kind=ShiftRequest.Kind.OFFER, requester=me, target=None, schedule=schedule)
            for person in people:
                note = services.notify(person.user, Notification.Kind.SHIFT_REQUEST,
                                       f'{who} wants to give up their shift on {when(schedule)}. Would you like to take it?')
                if note:
                    note.shift_request = sr
                    note.save(update_fields=['shift_request'])
            notify_managers(department, f'{who} offered their shift on {when(schedule)} to the whole department.')
        return Response(request_data(self._qs().get(pk=sr.pk)), status=status.HTTP_201_CREATED)

    @staticmethod
    def _may_answer_offer(me, sr):
        return (me.role == EmployeeProfile.Role.EMPLOYEE and me.pk != sr.requester_id
                and sr.schedule.shift.department_id in access.member_department_ids(me))

    def _pending(self, request, pk):
        sr = get_object_or_404(self._mine(request), pk=pk)
        if sr.status != ShiftRequest.Status.PENDING:
            if sr.kind == ShiftRequest.Kind.OFFER and sr.status == ShiftRequest.Status.ACCEPTED:
                raise ValidationError({'detail': 'Someone else already took this shift.'})
            raise ValidationError({'detail': f'This request was already {sr.status}.'})
        return sr

    def _resolve(self, sr, new_status):
        sr.status = new_status
        sr.resolved_at = timezone.now()
        sr.save(update_fields=['status', 'resolved_at', 'target'])
        Notification.objects.filter(shift_request=sr, kind=Notification.Kind.SHIFT_REQUEST).update(is_read=True)

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        me = access.get_profile(request.user)
        with transaction.atomic():
            sr = self._pending(request, pk)
            if sr.kind == ShiftRequest.Kind.OFFER:
                # lock the request so two people accepting at the same moment cannot both get the shift
                locked = ShiftRequest.objects.select_for_update().get(pk=sr.pk)
                if locked.status != ShiftRequest.Status.PENDING:
                    raise ValidationError({'detail': 'Someone else already took this shift.'})
                if not self._may_answer_offer(me, sr):
                    raise PermissionDenied('Only employees in this department can take this shift.')
            elif sr.target_id != me.pk:
                raise PermissionDenied('Only the person who was asked can accept.')
            schedule = Schedule.objects.select_related('employee__user', 'shift__department').get(pk=sr.schedule_id)
            other = (Schedule.objects.select_related('employee__user', 'shift__department').get(pk=sr.other_schedule_id)
                     if sr.other_schedule_id else None)
            requester = sr.requester
            target = me if sr.kind == ShiftRequest.Kind.OFFER else sr.target
            # The shifts must still belong to the same people as when the request was made.
            if sr.kind in (ShiftRequest.Kind.GIVE, ShiftRequest.Kind.OFFER):
                still_valid = schedule.employee_id == requester.pk
            elif sr.kind == ShiftRequest.Kind.TAKE:
                still_valid = schedule.employee_id == target.pk
            else:
                still_valid = schedule.employee_id == requester.pk and other.employee_id == target.pk
            if not still_valid:
                self._resolve(sr, ShiftRequest.Status.CANCELLED)  # returned (not raised) so the change is kept
                return Response({'detail': 'That shift has changed since the request was made.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if sr.kind in (ShiftRequest.Kind.GIVE, ShiftRequest.Kind.OFFER):
                self._check_can_work(target, schedule)
                schedule.employee, schedule.notes = target, ''   # a note was written for the previous person
                schedule.save()
                summary = f'{services.display_name(requester.user)} gave {services.display_name(target.user)} their shift on {when(schedule)}.'
            elif sr.kind == ShiftRequest.Kind.TAKE:
                self._check_can_work(requester, schedule)
                schedule.employee, schedule.notes = requester, ''
                schedule.save()
                summary = f'{services.display_name(target.user)} gave {services.display_name(requester.user)} their shift on {when(schedule)}.'
            else:
                self._check_can_work(target, schedule, leaving=[other.pk])
                self._check_can_work(requester, other, leaving=[schedule.pk])
                schedule.employee, other.employee = target, requester
                schedule.notes = other.notes = ''
                schedule.save()
                other.save()
                summary = (f'{services.display_name(requester.user)} and {services.display_name(target.user)} swapped shifts: '
                           f'{services.display_name(requester.user)} now works {when(other)}, '
                           f'{services.display_name(target.user)} works {when(schedule)}.')
            if sr.kind == ShiftRequest.Kind.OFFER:
                sr.target = me   # recorded now that it is theirs
            self._resolve(sr, ShiftRequest.Status.ACCEPTED)
            services.notify(requester.user, Notification.Kind.INFO,
                            f'{services.display_name(target.user)} accepted your shift request. {summary}')
            notify_managers(schedule.shift.department, summary)
        return Response(request_data(self._qs().get(pk=sr.pk)))

    @action(detail=True, methods=['post'])
    def decline(self, request, pk=None):
        me = access.get_profile(request.user)
        sr = self._pending(request, pk)
        if sr.kind == ShiftRequest.Kind.OFFER:
            # Saying no to an offer only dismisses it for me; it stays open for the rest of the department.
            if not self._may_answer_offer(me, sr):
                raise PermissionDenied('Only employees in this department can answer this offer.')
            Notification.objects.filter(shift_request=sr, recipient=request.user).update(is_read=True)
            return Response(request_data(self._qs().get(pk=sr.pk)))
        if sr.target_id != me.pk:
            raise PermissionDenied('Only the person who was asked can decline.')
        self._resolve(sr, ShiftRequest.Status.DECLINED)
        services.notify(sr.requester.user, Notification.Kind.INFO,
                        f'{services.display_name(request.user)} declined your request about the shift on {when(sr.schedule)}.')
        return Response(request_data(self._qs().get(pk=sr.pk)))

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        me = access.get_profile(request.user)
        sr = self._pending(request, pk)
        if sr.requester_id != me.pk:
            raise PermissionDenied('Only the person who asked can cancel.')
        self._resolve(sr, ShiftRequest.Status.CANCELLED)
        return Response(request_data(self._qs().get(pk=sr.pk)))
