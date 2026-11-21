import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from ..models import (
    AvailabilitySlot,
    Company,
    CompanyHours,
    Department,
    EmployeeProfile,
    Project,
    Schedule,
    Task,
    TimeOffRequest,
)


def time_to_minutes(t: datetime.time) -> int:
    """Convert datetime.time to minutes since midnight."""
    return t.hour * 60 + t.minute


def minutes_to_time(m: int) -> datetime.time:
    """Convert minutes since midnight to datetime.time, clamped to [0, 1439]."""
    clamped = max(0, min(m, 23 * 60 + 59))
    return datetime.time(clamped // 60, clamped % 60)


def calculate_slot_times(
    open_time: datetime.time,
    close_time: datetime.time,
    duration_hours: float,
    window: str,
) -> Tuple[datetime.time, datetime.time]:
    """
    Given daily open/close times and task duration, compute start_time and end_time
    based on the preferred window.
    """
    open_min = time_to_minutes(open_time)
    close_min = time_to_minutes(close_time)
    day_span_min = close_min - open_min

    if day_span_min <= 0:
        return open_time, close_time

    dur_min = int(duration_hours * 60)
    dur_min = min(dur_min, day_span_min)

    if window == Task.PreferredWindow.OPEN_TO_CLOSE:
        return open_time, close_time

    if window == Task.PreferredWindow.BEGINNING_OF_DAY:
        start_min = open_min
        end_min = min(close_min, open_min + dur_min)
        return minutes_to_time(start_min), minutes_to_time(end_min)

    if window == Task.PreferredWindow.END_OF_DAY:
        end_min = close_min
        start_min = max(open_min, close_min - dur_min)
        return minutes_to_time(start_min), minutes_to_time(end_min)

    if window == Task.PreferredWindow.MID_DAY:
        mid_min = open_min + (day_span_min // 2)
        half_dur = dur_min // 2
        start_min = max(open_min, mid_min - half_dur)
        end_min = min(close_min, start_min + dur_min)
        if end_min == close_min:
            start_min = max(open_min, close_min - dur_min)
        return minutes_to_time(start_min), minutes_to_time(end_min)

    # Default / FLEXIBLE fallback: starts at opening of day
    start_min = open_min
    end_min = min(close_min, open_min + dur_min)
    return minutes_to_time(start_min), minutes_to_time(end_min)


class ShiftGeneratorService:
    """
    Generates weekly shift schedules for a company based on:
    - Company operating hours (from CompanyHours)
    - Active projects and tasks
    - Staff concurrency limits (based on active employee headcount)
    - Intra-day timeline density packing for flexible tasks (waterfilling valleys)
    - Task priority, duration, preferred window, and headcount
    - Pre-assigned employees and their availability / approved time-off
    - Concurrency leveling for flexible shifts and load balancing across the week
    """

    PRIORITY_WEIGHTS = {
        Project.Priority.HIGH: 3,
        Project.Priority.MEDIUM: 2,
        Project.Priority.LOW: 1,
    }

    SLOT_STEP_MINUTES = 30

    def __init__(
        self,
        company: Company,
        week_start: datetime.date,
        department: Optional[Department] = None,
        clear_existing: bool = False,
    ):
        self.company = company
        # Normalize week_start to Monday of that week
        self.week_start = week_start - datetime.timedelta(days=week_start.weekday())
        self.week_end = self.week_start + datetime.timedelta(days=6)
        self.department = department
        self.clear_existing = clear_existing

        # Calculate max concurrent staffing capacity
        staff_qs = EmployeeProfile.objects.filter(company=self.company)
        if self.department:
            staff_qs = staff_qs.filter(department=self.department)
        self.max_concurrency = max(1, staff_qs.count())

        self.warnings: List[str] = []
        self.schedules_to_create: List[Schedule] = []

    def _get_company_hours_map(self) -> Dict[int, Tuple[Optional[datetime.time], Optional[datetime.time]]]:
        """Returns a dict mapping day_of_week (0=Monday..6=Sunday) to (start_time, end_time)."""
        ch = CompanyHours.objects.filter(company=self.company).first()
        if not ch:
            default_start = datetime.time(8, 0)
            default_end = datetime.time(18, 0)
            return {
                0: (default_start, default_end),
                1: (default_start, default_end),
                2: (default_start, default_end),
                3: (default_start, default_end),
                4: (default_start, default_end),
                5: (None, None),
                6: (None, None),
            }

        return {
            0: (ch.monday_start, ch.monday_end),
            1: (ch.tuesday_start, ch.tuesday_end),
            2: (ch.wednesday_start, ch.wednesday_end),
            3: (ch.thursday_start, ch.thursday_end),
            4: (ch.friday_start, ch.friday_end),
            5: (ch.saturday_start, ch.saturday_end),
            6: (ch.sunday_start, ch.sunday_end),
        }

    def _seed_existing_schedules(self, days: List[Dict[str, Any]]):
        """Populates initial load and concurrency from existing non-cancelled schedules."""
        qs = Schedule.objects.filter(
            shift_date__gte=self.week_start,
            shift_date__lte=self.week_end,
        ).exclude(status=Schedule.Status.CANCELLED)

        if self.department:
            qs = qs.filter(Q(task__department=self.department) | Q(department=self.department))
        else:
            qs = qs.filter(Q(task__company=self.company) | Q(company=self.company))

        days_by_date = {d["date"]: d for d in days if d["is_open"]}
        for s in qs:
            day = days_by_date.get(s.shift_date)
            if not day:
                continue
            s_min = time_to_minutes(s.start_time)
            e_min = time_to_minutes(s.end_time)
            dur_h = max(0.0, (e_min - s_min) / 60.0)
            day["scheduled_hours"] += dur_h
            for m in range(max(0, s_min), min(1440, e_min)):
                day["concurrency"][m] += 1

    def _build_days_meta(self) -> List[Dict[str, Any]]:
        """Builds metadata for each of the 7 days of the target week."""
        hours_map = self._get_company_hours_map()
        days = []
        for offset in range(7):
            current_date = self.week_start + datetime.timedelta(days=offset)
            dow = current_date.weekday()
            start_t, end_t = hours_map.get(dow, (None, None))

            is_open = False
            duration_hours = 0.0
            open_min = 0
            close_min = 0
            if start_t is not None and end_t is not None:
                open_min = time_to_minutes(start_t)
                close_min = time_to_minutes(end_t)
                if close_min > open_min:
                    is_open = True
                    duration_hours = (close_min - open_min) / 60.0

            days.append(
                {
                    "date": current_date,
                    "day_of_week": dow,
                    "is_open": is_open,
                    "open_time": start_t,
                    "close_time": end_t,
                    "open_min": open_min,
                    "close_min": close_min,
                    "duration_hours": duration_hours,
                    "scheduled_hours": 0.0,
                    "concurrency": [0] * 1440,
                }
            )

        if not self.clear_existing:
            self._seed_existing_schedules(days)

        return days

    def _find_best_slot_times(
        self,
        day_meta: Dict[str, Any],
        duration_hours: float,
        window: str,
        headcount: int,
        employee: Optional[EmployeeProfile] = None,
    ) -> Tuple[datetime.time, datetime.time]:
        """
        Determines the optimal start and end time for a shift within day_meta.
        For fixed windows (OPEN_TO_CLOSE, BEGINNING, END, MID_DAY), calculates the anchored time.
        For FLEXIBLE windows, uses density packing (waterfilling valleys) across the day's timeline
        so tasks space out naturally rather than stacking at opening time.
        """
        open_time = day_meta["open_time"]
        close_time = day_meta["close_time"]
        open_min = time_to_minutes(open_time)
        close_min = time_to_minutes(close_time)
        day_span_min = close_min - open_min

        dur_min = int(duration_hours * 60)
        dur_min = min(dur_min, day_span_min)

        # 1. Fixed window placement
        if window == Task.PreferredWindow.OPEN_TO_CLOSE:
            return open_time, close_time

        if window == Task.PreferredWindow.BEGINNING_OF_DAY:
            start_min = open_min
            end_min = min(close_min, open_min + dur_min)
            return minutes_to_time(start_min), minutes_to_time(end_min)

        if window == Task.PreferredWindow.END_OF_DAY:
            end_min = close_min
            start_min = max(open_min, close_min - dur_min)
            return minutes_to_time(start_min), minutes_to_time(end_min)

        if window == Task.PreferredWindow.MID_DAY:
            mid_min = open_min + (day_span_min // 2)
            half_dur = dur_min // 2
            start_min = max(open_min, mid_min - half_dur)
            end_min = min(close_min, start_min + dur_min)
            if end_min == close_min:
                start_min = max(open_min, close_min - dur_min)
            return minutes_to_time(start_min), minutes_to_time(end_min)

        # 2. FLEXIBLE window: Density / Waterfilling search
        step = self.SLOT_STEP_MINUTES
        timeline = day_meta["timeline"]
        num_intervals = len(timeline)

        candidate_slots = []
        if dur_min <= 0:
            return open_time, open_time

        for start_m in range(open_min, close_min - dur_min + 1, step):
            end_m = start_m + dur_min
            start_t = minutes_to_time(start_m)
            end_t = minutes_to_time(end_m)

            # If task has a pre-assigned employee, check availability for this candidate window
            if employee:
                is_avail, _ = self._is_employee_available(employee, day_meta["date"], start_t, end_t)
                if not is_avail:
                    continue

            # Map to timeline interval indices
            start_idx = max(0, (start_m - open_min) // step)
            end_idx = min(num_intervals, (end_m - open_min + step - 1) // step)

            window_counts = timeline[start_idx:end_idx] if end_idx > start_idx else [0]
            peak = (max(window_counts) if window_counts else 0) + headcount
            density = sum(window_counts)

            fits_capacity = peak <= self.max_concurrency

            # Optimization score:
            # 1. Fits within max staffing capacity (0 = yes, 1 = overflow)
            # 2. Lowest peak headcount in that window
            # 3. Lowest density sum (valley)
            # 4. Earliest start time (tie breaker)
            score = (0 if fits_capacity else 1, peak, density, start_m)
            candidate_slots.append((score, start_t, end_t))

        if candidate_slots:
            candidate_slots.sort(key=lambda x: x[0])
            return candidate_slots[0][1], candidate_slots[0][2]

        # Fallback if no window matched
        return open_time, minutes_to_time(min(close_min, open_min + dur_min))

    def _record_shift_on_day(
        self,
        day_meta: Dict[str, Any],
        start_time: datetime.time,
        end_time: datetime.time,
        headcount: int,
        duration_hours: float,
    ):
        """Updates the day's timeline interval counts and scheduled person-hours."""
        step = self.SLOT_STEP_MINUTES
        open_min = time_to_minutes(day_meta["open_time"])
        start_min = time_to_minutes(start_time)
        end_min = time_to_minutes(end_time)

        start_idx = max(0, (start_min - open_min) // step)
        end_idx = min(len(day_meta["timeline"]), (end_min - open_min + step - 1) // step)

        for i in range(start_idx, end_idx):
            day_meta["timeline"][i] += headcount

        day_meta["scheduled_hours"] += duration_hours
        day_meta["scheduled_person_hours"] += (duration_hours * headcount)

    def _is_employee_available(
        self,
        employee: EmployeeProfile,
        shift_date: datetime.date,
        start_time: datetime.time,
        end_time: datetime.time,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates whether an employee can work a specific shift window on a given date:
        1. Checks for approved TimeOffRequests covering shift_date.
        2. Checks whether an AvailabilitySlot on shift_date's day_of_week fully covers
           [start_time, end_time].
        """
        # 1. Approved time-off check
        on_leave = TimeOffRequest.objects.filter(
            employee=employee,
            status=TimeOffRequest.Status.APPROVED,
            start_date__lte=shift_date,
            end_date__gte=shift_date,
        ).exists()
        if on_leave:
            return False, f"Employee {employee} has approved time-off on {shift_date}."

        # 2. Availability slot check (must cover start_time <= slot.start and slot.end >= end_time)
        all_emp_slots = AvailabilitySlot.objects.filter(employee=employee)
        if all_emp_slots.exists():
            dow = shift_date.weekday()
            dow_slots = all_emp_slots.filter(day_of_week=dow)
            if not dow_slots.exists():
                return False, f"Employee {employee} has no availability slot on {shift_date.strftime('%A')}."

            covered = dow_slots.filter(start_time__lte=start_time, end_time__gte=end_time).exists()
            if not covered:
                slot_ranges = ", ".join(f"{s.start_time:%H:%M}-{s.end_time:%H:%M}" for s in dow_slots)
                return (
                    False,
                    f"Employee {employee} available hours on {shift_date.strftime('%A')} ({slot_ranges}) do not cover shift ({start_time:%H:%M}-{end_time:%H:%M}).",
                )

        return True, None

    def _find_best_slot_times(
        self,
        day: Dict[str, Any],
        duration_hours: float,
        window: str,
        employee: Optional[EmployeeProfile] = None,
    ) -> Tuple[datetime.time, datetime.time, Optional[EmployeeProfile], Optional[str]]:
        """
        Determines the start and end times for a shift on a given day.
        For fixed windows (BEGINNING_OF_DAY, MID_DAY, END_OF_DAY, OPEN_TO_CLOSE),
        times are anchored.
        For FLEXIBLE, concurrency leveling finds the window that minimizes concurrent staff
        (leveling headcount throughout the day) and respects employee availability if pre-assigned.

        Returns (start_time, end_time, assigned_employee, warning_message).
        """
        open_time = day["open_time"]
        close_time = day["close_time"]
        open_min = day["open_min"]
        close_min = day["close_min"]
        day_span_min = close_min - open_min

        dur_min = int(duration_hours * 60)
        dur_min = min(dur_min, day_span_min)

        if window != Task.PreferredWindow.FLEXIBLE:
            start_t, end_t = calculate_slot_times(open_time, close_time, duration_hours, window)
            assigned_emp = None
            warn = None
            if employee:
                is_avail, reason = self._is_employee_available(employee, day["date"], start_t, end_t)
                if is_avail:
                    assigned_emp = employee
                else:
                    warn = reason
            return start_t, end_t, assigned_emp, warn

        # FLEXIBLE WINDOW: Concurrency leveling
        if dur_min <= 0 or day_span_min <= 0:
            return open_time, open_time, None, None

        max_start = close_min - dur_min
        if max_start < open_min:
            return open_time, close_time, None, None

        # Candidate start times spaced every 15 minutes, plus max_start
        candidates = list(range(open_min, max_start + 1, 15))
        if max_start not in candidates:
            candidates.append(max_start)
        candidates.sort()

        assigned_emp = None
        emp_warning = None

        if employee:
            # Check leave first
            on_leave = TimeOffRequest.objects.filter(
                employee=employee,
                status=TimeOffRequest.Status.APPROVED,
                start_date__lte=day["date"],
                end_date__gte=day["date"],
            ).exists()

            if on_leave:
                emp_warning = f"Employee {employee} has approved time-off on {day['date']}."
                valid_candidates = candidates
            else:
                all_emp_slots = AvailabilitySlot.objects.filter(employee=employee)
                if all_emp_slots.exists():
                    dow = day["date"].weekday()
                    dow_slots = all_emp_slots.filter(day_of_week=dow)
                    if not dow_slots.exists():
                        emp_warning = f"Employee {employee} has no availability slot on {day['date'].strftime('%A')}."
                        valid_candidates = candidates
                    else:
                        matching = []
                        for s in candidates:
                            st = minutes_to_time(s)
                            et = minutes_to_time(s + dur_min)
                            if dow_slots.filter(start_time__lte=st, end_time__gte=et).exists():
                                matching.append(s)

                        if matching:
                            assigned_emp = employee
                            valid_candidates = matching
                        else:
                            slot_ranges = ", ".join(f"{sl.start_time:%H:%M}-{sl.end_time:%H:%M}" for sl in dow_slots)
                            emp_warning = f"Employee {employee} available hours on {day['date'].strftime('%A')} ({slot_ranges}) do not cover shift duration ({duration_hours:.1f}h)."
                            valid_candidates = candidates
                else:
                    assigned_emp = employee
                    valid_candidates = candidates
        else:
            valid_candidates = candidates

        # Leveling: Find candidate with lowest peak concurrency, then lowest average concurrency, then earliest start
        def score(s: int) -> Tuple[int, float, int]:
            e = s + dur_min
            segment = day["concurrency"][s:e]
            max_c = max(segment) if segment else 0
            avg_c = (sum(segment) / float(dur_min)) if dur_min > 0 else 0.0
            return (max_c, avg_c, s)

        best_s = min(valid_candidates, key=score)
        start_t = minutes_to_time(best_s)
        end_t = minutes_to_time(best_s + dur_min)

        return start_t, end_t, assigned_emp, emp_warning

    def _task_priority_key(self, task: Task) -> Tuple[int, int, float]:
        """Sorting key to prioritize high-priority projects and tasks first."""
        proj_prio = self.PRIORITY_WEIGHTS.get(
            task.project.priority if task.project else Project.Priority.MEDIUM, 2
        )
        task_prio = self.PRIORITY_WEIGHTS.get(task.priority, 2)
        # Fixed window tasks (1) anchor their specific times before flexible tasks (0) fill valleys
        is_fixed = 0 if task.preferred_window == Task.PreferredWindow.FLEXIBLE else 1
        dur = float(task.duration_hours or 1.0)
        return (proj_prio, is_fixed, task_prio, -dur)

    def _create_schedule_slots(
        self,
        task: Task,
        shift_date: datetime.date,
        start_time: datetime.time,
        end_time: datetime.time,
        assigned_emp: Optional[EmployeeProfile] = None,
    ):
        """
        Creates the required headcount Schedule slots for a task block.
        All headcount positions work at the exact same time window.
        Slot 1 gets assigned_emp (if available).
        Slots 2..N are created unassigned.
        """
        headcount = max(1, task.required_people)

        # Slot 1
        self.schedules_to_create.append(
            Schedule(
                company=task.company,
                department=task.department,
                task=task,
                task_name=task.name,
                shift_date=shift_date,
                start_time=start_time,
                end_time=end_time,
                employee=assigned_emp,
                status=Schedule.Status.SCHEDULED,
                notes=f"Auto-generated for {task.name}",
            )
        )

        # Slots 2..N: always unassigned for the smart scheduler to fill
        for pos in range(2, headcount + 1):
            self.schedules_to_create.append(
                Schedule(
                    company=task.company,
                    department=task.department,
                    task=task,
                    task_name=task.name,
                    shift_date=shift_date,
                    start_time=start_time,
                    end_time=end_time,
                    employee=None,
                    status=Schedule.Status.SCHEDULED,
                    notes=f"Auto-generated for {task.name} (Position {pos})",
                )
            )

    def _record_day_usage(
        self,
        day: Dict[str, Any],
        start_time: datetime.time,
        end_time: datetime.time,
        headcount: int,
    ):
        """Records concurrency and scheduled person-hours on a day's timeline."""
        s_min = time_to_minutes(start_time)
        e_min = time_to_minutes(end_time)
        dur_h = max(0.0, (e_min - s_min) / 60.0)

        for m in range(max(0, s_min), min(1440, e_min)):
            day["concurrency"][m] += headcount

        day["scheduled_hours"] += dur_h * headcount

    def _get_target_days_for_recurring_task(
        self, task: Task, open_days: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Returns the open days on which a recurring task should be generated.
        If task.preferred_day is set (0=Monday..6=Sunday), runs only on that weekday.
        If task.preferred_day is None (flexible), runs on all open days.
        """
        if task.preferred_day is not None:
            matching = [d for d in open_days if d["day_of_week"] == task.preferred_day]
            if not matching:
                day_name = dict(Task.Day.choices).get(task.preferred_day, str(task.preferred_day))
                self.warnings.append(
                    f"Recurring task '{task.name}' preferred day is {day_name}, but company is closed on that day."
                )
            return matching
        return open_days

    def _schedule_non_recurring_task(self, task: Task, open_days: List[Dict[str, Any]]):
        """Schedules a non-recurring task across open days, respecting preferred_day if set,
        balancing load and leveling concurrency."""
        headcount = max(1, task.required_people)
        remaining_dur = float(task.duration_hours)

        candidate_days: List[Dict[str, Any]] = []

        if task.preferred_day is not None:
            # Task has a specific preferred day
            day_name = dict(Task.Day.choices).get(task.preferred_day, str(task.preferred_day))
            pref_day = next((d for d in open_days if d["day_of_week"] == task.preferred_day), None)

            if pref_day:
                # Preferred day is open: place it first
                other_days = [d for d in open_days if d != pref_day]
                other_days.sort(key=lambda d: d["scheduled_hours"])
                candidate_days = [pref_day] + other_days
            else:
                self.warnings.append(
                    f"Task '{task.name}' preferred day is {day_name}, but company is closed on that day. Falling back to load-balanced day."
                )

        if not candidate_days:
            # No preferred day or preferred day was closed: use employee availability and load-balancing
            candidate_days = open_days.copy()
            if task.employee:
                available_days = []
                for d in candidate_days:
                    chunk = min(remaining_dur, d["duration_hours"])
                    start_t, end_t, assigned_emp, warn = self._find_best_slot_times(
                        d, chunk, task.preferred_window, task.employee
                    )
                    if assigned_emp is not None:
                        available_days.append((d["scheduled_hours"], d))
                    else:
                        self.warnings.append(
                            f"Task '{task.name}' pre-assigned to {task.employee}: {warn}"
                        )

                if available_days:
                    available_days.sort(key=lambda x: x[0])
                    candidate_days = [item[1] for item in available_days]
                else:
                    self.warnings.append(
                        f"Task '{task.name}' pre-assigned to {task.employee}: employee has no open days with matching availability during the week. Shifts will be created unassigned."
                    )
                    candidate_days.sort(key=lambda d: d["scheduled_hours"])
            else:
                candidate_days.sort(key=lambda d: d["scheduled_hours"])

        day_index = 0
        while remaining_dur > 0 and day_index < len(candidate_days):
            curr_day = candidate_days[day_index]
            day_capacity = curr_day["duration_hours"]

            if task.preferred_window == Task.PreferredWindow.OPEN_TO_CLOSE:
                chunk_dur = day_capacity
                remaining_dur = 0.0
            else:
                chunk_dur = min(remaining_dur, day_capacity)
                remaining_dur -= chunk_dur

            start_t, end_t, assigned_emp, warn = self._find_best_slot_times(
                curr_day, chunk_dur, task.preferred_window, task.employee
            )
            if warn and task.employee and assigned_emp is None:
                self.warnings.append(
                    f"Task '{task.name}' on {curr_day['date']} ({start_t:%H:%M}-{end_t:%H:%M}): {warn} Shift created unassigned for smart scheduler."
                )

            self._create_schedule_slots(task, curr_day["date"], start_t, end_t, assigned_emp)
            self._record_day_usage(curr_day, start_t, end_t, headcount)
            day_index += 1

        if remaining_dur > 0:
            self.warnings.append(
                f"Task '{task.name}' could not be fully scheduled ({remaining_dur:.1f} hours unscheduled due to open hours capacity)."
            )

    def generate(self) -> Dict[str, Any]:
        """Executes the shift generation and persists to DB in an atomic transaction."""
        days_meta = self._build_days_meta()
        open_days = [d for d in days_meta if d["is_open"]]

        if not open_days:
            raise ValidationError(
                f"Company '{self.company.name}' has no open hours during week {self.week_start} to {self.week_end}."
            )

        # 1. Fetch active tasks for active projects (or tasks with no project)
        tasks_qs = Task.objects.filter(company=self.company)
        if self.department:
            tasks_qs = tasks_qs.filter(department=self.department)

        tasks = [t for t in tasks_qs.select_related("project", "department", "employee") if not t.project or t.project.is_active]

        # Partition tasks:
        # Phase 1: Fixed-window tasks (anchors)
        # Phase 2: Flexible-window tasks (concurrency leveling into valleys)
        fixed_recurring = [t for t in tasks if t.is_recurring and t.preferred_window != Task.PreferredWindow.FLEXIBLE]
        fixed_non_recurring = [t for t in tasks if not t.is_recurring and t.preferred_window != Task.PreferredWindow.FLEXIBLE]
        flexible_recurring = [t for t in tasks if t.is_recurring and t.preferred_window == Task.PreferredWindow.FLEXIBLE]
        flexible_non_recurring = [t for t in tasks if not t.is_recurring and t.preferred_window == Task.PreferredWindow.FLEXIBLE]

        # Sort non-recurring tasks by priority descending
        fixed_non_recurring.sort(key=self._task_priority_key, reverse=True)
        flexible_non_recurring.sort(key=self._task_priority_key, reverse=True)

        # Phase 1A: Fixed Recurring Tasks
        for task in fixed_recurring:
            headcount = max(1, task.required_people)
            target_days = self._get_target_days_for_recurring_task(task, open_days)
            for day in target_days:
                dur = day["duration_hours"] if task.preferred_window == Task.PreferredWindow.OPEN_TO_CLOSE else float(task.duration_hours)
                start_t, end_t, assigned_emp, warn = self._find_best_slot_times(
                    day, dur, task.preferred_window, task.employee
                )
                if warn and task.employee and assigned_emp is None:
                    self.warnings.append(
                        f"Task '{task.name}' on {day['date']} ({start_t:%H:%M}-{end_t:%H:%M}): {warn} Shift created unassigned for smart scheduler."
                    )
                self._create_schedule_slots(task, day["date"], start_t, end_t, assigned_emp)
                self._record_day_usage(day, start_t, end_t, headcount)

        # Phase 1B: Fixed Non-Recurring Tasks
        for task in fixed_non_recurring:
            self._schedule_non_recurring_task(task, open_days)

        # Phase 2A: Flexible Recurring Tasks
        for task in flexible_recurring:
            headcount = max(1, task.required_people)
            target_days = self._get_target_days_for_recurring_task(task, open_days)
            for day in target_days:
                dur = float(task.duration_hours)
                start_t, end_t, assigned_emp, warn = self._find_best_slot_times(
                    day, dur, task.preferred_window, task.employee
                )
                if warn and task.employee and assigned_emp is None:
                    self.warnings.append(
                        f"Task '{task.name}' on {day['date']} ({start_t:%H:%M}-{end_t:%H:%M}): {warn} Shift created unassigned for smart scheduler."
                    )
                self._create_schedule_slots(task, day["date"], start_t, end_t, assigned_emp)
                self._record_day_usage(day, start_t, end_t, headcount)

        # Phase 2B: Flexible Non-Recurring Tasks
        for task in flexible_non_recurring:
            self._schedule_non_recurring_task(task, open_days)

        # 4. Atomic Database Transaction
        with transaction.atomic():
            if self.clear_existing:
                # Remove previously generated scheduled entries in this week range for this company
                qs_to_delete = Schedule.objects.filter(
                    shift_date__gte=self.week_start,
                    shift_date__lte=self.week_end,
                    status=Schedule.Status.SCHEDULED,
                )
                if self.department:
                    qs_to_delete = qs_to_delete.filter(
                        Q(task__department=self.department) | Q(department=self.department)
                    )
                else:
                    qs_to_delete = qs_to_delete.filter(
                        Q(task__company=self.company) | Q(company=self.company)
                    )
                qs_to_delete.delete()

            created = Schedule.objects.bulk_create(self.schedules_to_create)

        pre_assigned = sum(1 for s in created if s.employee_id is not None)
        unassigned = sum(1 for s in created if s.employee_id is None)
        unique_dates = sorted({s.shift_date.isoformat() for s in created})

        return {
            "company_id": self.company.id,
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "total_shifts_generated": len(created),
            "pre_assigned_shifts": pre_assigned,
            "unassigned_shifts": unassigned,
            "days_with_shifts": unique_dates,
            "warnings": self.warnings,
        }
