"""Age rules, weekly hour limits, warnings for manual scheduling, and the automatic scheduler."""
import datetime
from collections import defaultdict
from decimal import Decimal

from .models import (AvailabilitySlot, CompatibilityGroup, EmployeeProfile, Schedule, Shift, TimeOffRequest)

FULL_TIME_LIMIT = 40          # hours a week, unless overtime is allowed
PART_TIME_MIN = 5             # part time gets 5-39 hours
PART_TIME_MAX = 39
PART_TIME_TARGET = 24         # the auto scheduler fills part-timers up to this first
MINOR_AGE = 18
MINOR_DAY_LIMIT = 8           # hours
MINOR_WEEK_LIMIT = 18         # hours
MINOR_LATEST_END = datetime.time(21, 0)

# Compatibility groups (1-10): 1-3 avoid, 4-6 okay, 7-10 prefer.
AVOID_MAX = 3
PREFER_MIN = 7


# --- age -------------------------------------------------------------------------------------

def age_on(dob, day):
    return day.year - dob.year - ((day.month, day.day) < (dob.month, dob.day))


def age_of(profile, day=None):
    return age_on(profile.user.date_of_birth, day or datetime.date.today())


def is_minor(profile, day=None):
    return age_of(profile, day) < MINOR_AGE


# --- hours -----------------------------------------------------------------------------------

def monday_of(day):
    return day - datetime.timedelta(days=day.weekday())


def duration_hours(start, end):
    return (datetime.datetime.combine(datetime.date.min, end) - datetime.datetime.combine(datetime.date.min, start)).seconds / 3600


def hours_in_week(profile, day, extra=()):
    """Hours this person is scheduled in the Monday-Sunday week containing `day`."""
    monday = monday_of(day)
    rows = (Schedule.objects.filter(employee=profile, shift_date__range=(monday, monday + datetime.timedelta(days=6)))
            .exclude(status=Schedule.Status.CANCELLED))
    return sum(duration_hours(r.start_time, r.end_time) for r in rows) + sum(extra)


def hours_on_day(profile, day):
    rows = Schedule.objects.filter(employee=profile, shift_date=day).exclude(status=Schedule.Status.CANCELLED)
    return sum(duration_hours(r.start_time, r.end_time) for r in rows)


def weekly_limit(profile):
    """Max hours a week for this person, or None for no limit (full time with overtime allowed)."""
    if profile.employment_type == EmployeeProfile.EmploymentType.PART_TIME:
        return PART_TIME_MAX
    return None if profile.allow_overtime else FULL_TIME_LIMIT


def fmt_hours(h):
    return f'{h:g}' if abs(h - round(h)) > 1e-9 else str(int(round(h)))


def availability_warning(profile, name, day, start, end):
    """A sentence when this block is outside what the person said they can work, else None.
    Days they never edited count as available all day (same rule the automatic scheduler uses)."""
    weekday = day.weekday()
    label = day.strftime('%A')
    if weekday in (profile.unavailable_days or []):
        return f'{name} marked {label} as not available.'
    slots = list(AvailabilitySlot.objects.filter(employee=profile, day_of_week=weekday))
    if slots and not any(s.start_time <= start and s.end_time >= end for s in slots):
        times = ', '.join(f'{_clock(s.start_time)} - {_clock(s.end_time)}' for s in sorted(slots, key=lambda s: s.start_time))
        return f'{name} is only available {times} on {label}s, and this shift is {_clock(start)} - {_clock(end)}.'
    return None


def _clock(t):
    hour = t.hour % 12 or 12
    return f'{hour}{":%02d" % t.minute if t.minute else ""} {"AM" if t.hour < 12 else "PM"}'


def assignment_warnings(profile, name, day, start, end):
    """Things a manager should confirm before scheduling this person on this block."""
    length = duration_hours(start, end)
    out = []
    limit = weekly_limit(profile)
    total = hours_in_week(profile, day) + length
    if limit is not None and total > limit:
        kind = 'part time' if profile.employment_type == EmployeeProfile.EmploymentType.PART_TIME else 'full time'
        out.append(f'{name} is {kind} with a {limit}-hour weekly limit and would work {fmt_hours(total)} hours this week.')
    if is_minor(profile, day):
        issues = []
        if hours_on_day(profile, day) + length > MINOR_DAY_LIMIT:
            issues.append(f'more than {MINOR_DAY_LIMIT} hours that day')
        if total > MINOR_WEEK_LIMIT:
            issues.append(f'more than {MINOR_WEEK_LIMIT} hours this week')
        if end > MINOR_LATEST_END:
            issues.append('past 9 PM')
        if issues:
            out.append(f'{name} is under 18 and would work ' + ' and '.join(issues) + '.')
    return out


# --- automatic scheduler ---------------------------------------------------------------------

def pair_scores(company_id):
    """{(a, b): average compatibility score} for every pair that shares a rated group."""
    sums, counts = defaultdict(float), defaultdict(int)
    for group in CompatibilityGroup.objects.filter(company_id=company_id).prefetch_related('members'):
        ids = sorted(m.id for m in group.members.all())
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                sums[(a, b)] += group.score
                counts[(a, b)] += 1
    return {pair: sums[pair] / counts[pair] for pair in sums}


def pending_time_off(department, date_from, date_to):
    return (TimeOffRequest.objects.filter(employee__department=department, status=TimeOffRequest.Status.PENDING,
                                          start_date__lte=date_to, end_date__gte=date_from)
            .select_related('employee__user'))


class AutoScheduler:
    """
    Fills the open spots of a department's shifts in a date range (existing assignments stay).
    People with the best productivity score are scheduled first. Compatibility between people
    on the same shift: 1-3 avoided unless completely necessary, 4-6 okay but other options are
    tried first, 7-10 preferred.
    """

    def __init__(self, department, date_from, date_to, name_of):
        self.department = department
        self.date_from, self.date_to = date_from, date_to
        self.name_of = name_of
        self.scores = pair_scores(department.company_id)
        self.shifts = list(Shift.objects.filter(department=department, shift_date__range=(date_from, date_to))
                           .prefetch_related('assignments__employee__user').order_by('shift_date', 'start_time', 'id'))
        self.people = list(EmployeeProfile.objects.filter(department=department).exclude(role=EmployeeProfile.Role.CEO)
                           .select_related('user'))
        self.people.sort(key=lambda p: (-(p.productivity_score if p.productivity_score is not None else Decimal(-1)), p.id))
        self.profiles = {p.id: p for p in self.people}
        for s in self.shifts:
            for a in s.assignments.all():
                self.profiles.setdefault(a.employee_id, a.employee)
        self.on_shift = {s.id: {a.employee_id for a in s.assignments.all()} for s in self.shifts}
        self.time_off = defaultdict(list)
        for t in TimeOffRequest.objects.filter(employee__in=self.people, status=TimeOffRequest.Status.APPROVED,
                                               start_date__lte=date_to, end_date__gte=date_from):
            self.time_off[t.employee_id].append((t.start_date, t.end_date))
        self.availability = defaultdict(list)
        for slot in AvailabilitySlot.objects.filter(employee__in=self.people):
            self.availability[slot.employee_id].append(slot)
        # what each person already works (any department), by day, as (start, end) blocks
        self.blocks = defaultdict(list)
        weeks_from, weeks_to = monday_of(date_from), monday_of(date_to) + datetime.timedelta(days=6)
        for row in (Schedule.objects.filter(employee__in=self.people, shift_date__range=(weeks_from, weeks_to))
                    .exclude(status=Schedule.Status.CANCELLED)):
            self.blocks[(row.employee_id, row.shift_date)].append((row.start_time, row.end_time))
        self.created = []          # (shift, person)
        self.notes = []
        self.open_before = sum(max(s.headcount - len(self.on_shift[s.id]), 0) for s in self.shifts)

    # -- hour bookkeeping from the in-memory blocks
    def _week_hours(self, person, day):
        monday = monday_of(day)
        return sum(duration_hours(a, b) for d in range(7)
                   for a, b in self.blocks[(person.id, monday + datetime.timedelta(days=d))])

    def _day_hours(self, person, day):
        return sum(duration_hours(a, b) for a, b in self.blocks[(person.id, day)])

    def _open(self, shift):
        return shift.headcount - len(self.on_shift[shift.id])

    def _eligible(self, person, shift, week_cap, overtime_ok):
        if person.id in self.on_shift[shift.id] or self._open(shift) <= 0:
            return False
        if any(a < shift.end_time and b > shift.start_time for a, b in self.blocks[(person.id, shift.shift_date)]):
            return False
        if any(a <= shift.shift_date <= b for a, b in self.time_off[person.id]):
            return False
        # A day the person never edited is available all day. A ticked "not available" day is off.
        # A day with availability slots limits the person to those hours.
        day = shift.shift_date.weekday()
        if day in (person.unavailable_days or []):
            return False
        day_slots = [s for s in self.availability[person.id] if s.day_of_week == day]
        if day_slots and not any(s.start_time <= shift.start_time and s.end_time >= shift.end_time for s in day_slots):
            return False
        length = duration_hours(shift.start_time, shift.end_time)
        total = self._week_hours(person, shift.shift_date) + length
        if person.employment_type == EmployeeProfile.EmploymentType.PART_TIME:
            if total > week_cap:
                return False
        elif total > FULL_TIME_LIMIT and not (overtime_ok and person.allow_overtime):
            return False
        if is_minor(person, shift.shift_date):
            if (self._day_hours(person, shift.shift_date) + length > MINOR_DAY_LIMIT or total > MINOR_WEEK_LIMIT
                    or shift.end_time > MINOR_LATEST_END):
                return False
        return True

    def _pair(self, a, b):
        return self.scores.get((min(a, b), max(a, b)))

    def _compat(self, person, shift):
        """(has_avoid, points) for putting `person` on `shift` given who is already there."""
        avoid, points = False, 0.0
        for other in self.on_shift[shift.id]:
            score = self._pair(person.id, other)
            if score is None:
                continue
            if score <= AVOID_MAX:
                avoid = True
            elif score >= PREFER_MIN:
                points += 2
            else:
                points -= 0.5
        return avoid, points

    def run(self):
        # (part-time cap, allow avoided pairings, allow overtime)
        phases = [(PART_TIME_TARGET, False, False), (PART_TIME_MAX, False, False),
                  (PART_TIME_MAX, True, False), (PART_TIME_MAX, True, True)]
        for week_cap, allow_avoid, overtime_ok in phases:
            for person in self.people:
                while True:
                    best = None
                    for shift in self.shifts:
                        if not self._eligible(person, shift, week_cap, overtime_ok):
                            continue
                        avoid, points = self._compat(person, shift)
                        if avoid and not allow_avoid:
                            continue
                        key = (-points, -self._open(shift) / shift.headcount, shift.shift_date, shift.start_time, shift.id)
                        if best is None or key < best[0]:
                            best = (key, shift, avoid)
                    if best is None:
                        break
                    _, shift, avoid = best
                    self._place(person, shift, avoid)
        return self._finish()

    def _place(self, person, shift, avoid):
        others = [o for o in self.on_shift[shift.id]]
        self.on_shift[shift.id].add(person.id)
        self.blocks[(person.id, shift.shift_date)].append((shift.start_time, shift.end_time))
        self.created.append((shift, person))
        if avoid:
            lows = [self.profiles[o] for o in others
                    if self._pair(person.id, o) is not None and self._pair(person.id, o) <= AVOID_MAX]
            self.notes.append(f'{self.name_of(person)} was put on {shift.shift_date:%a %b} {shift.shift_date.day} with '
                              + ', '.join(self.name_of(p) for p in lows)
                              + ' because no better option was left (low compatibility).')

    def _finish(self):
        for shift, person in self.created:
            Schedule.objects.create(task_name=shift.name or 'Shift', employee=person, shift_date=shift.shift_date,
                                    start_time=shift.start_time, end_time=shift.end_time, shift=shift)
        left = sum(max(self._open(s), 0) for s in self.shifts)
        for person in self.people:
            if person.employment_type == EmployeeProfile.EmploymentType.PART_TIME:
                hrs = self._week_hours(person, self.date_from)
                if hrs < PART_TIME_MIN:
                    self.notes.append(f'{self.name_of(person)} (part time) only has {fmt_hours(hrs)} hours; '
                                      f'part time is meant to get at least {PART_TIME_MIN}.')
        return {'created': len(self.created), 'open_before': self.open_before, 'open_after': left, 'notes': self.notes}
