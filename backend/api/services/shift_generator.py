import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction

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

    # Default / FLEXIBLE: starts at opening of day
    start_min = open_min
    end_min = min(close_min, open_min + dur_min)
    return minutes_to_time(start_min), minutes_to_time(end_min)


class ShiftGeneratorService:
    """
    Generates weekly shift schedules for a company based on:
    - Company operating hours (from CompanyHours)
    - Active projects and tasks
    - Task priority, duration, preferred window, and headcount
    - Pre-assigned employees and their availability / approved time-off
    """

    PRIORITY_WEIGHTS = {
        Project.Priority.HIGH: 3,
        Project.Priority.MEDIUM: 2,
        Project.Priority.LOW: 1,
    }

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

        self.warnings: List[str] = []
        self.schedules_to_create: List[Schedule] = []

    def _get_company_hours_map(self) -> Dict[int, Tuple[Optional[datetime.time], Optional[datetime.time]]]:
        """Returns a dict mapping day_of_week (0=Monday..6=Sunday) to (start_time, end_time)."""
        ch = CompanyHours.objects.filter(company=self.company).first()
        if not ch:
            raise ValidationError(
                f"No CompanyHours configured for company '{self.company.name}'. Cannot generate shifts."
            )

        return {
            0: (ch.monday_start, ch.monday_end),
            1: (ch.tuesday_start, ch.tuesday_end),
            2: (ch.wednesday_start, ch.wednesday_end),
            3: (ch.thursday_start, ch.thursday_end),
            4: (ch.friday_start, ch.friday_end),
            5: (ch.saturday_start, ch.saturday_end),
            6: (ch.sunday_start, ch.sunday_end),
        }

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
            if start_t is not None and end_t is not None:
                start_min = time_to_minutes(start_t)
                end_min = time_to_minutes(end_t)
                if end_min > start_min:
                    is_open = True
                    duration_hours = (end_min - start_min) / 60.0

            days.append(
                {
                    "date": current_date,
                    "day_of_week": dow,
                    "is_open": is_open,
                    "open_time": start_t,
                    "close_time": end_t,
                    "duration_hours": duration_hours,
                    "scheduled_hours": 0.0,
                }
            )
        return days

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

    def _task_priority_key(self, task: Task) -> Tuple[int, int, float]:
        """Sorting key to prioritize high-priority projects and tasks first."""
        proj_prio = self.PRIORITY_WEIGHTS.get(
            task.project.priority if task.project else Project.Priority.MEDIUM, 2
        )
        task_prio = self.PRIORITY_WEIGHTS.get(task.priority, 2)
        dur = float(task.duration_hours or 1.0)
        return (proj_prio, task_prio, -dur)

    def _create_schedule_slots(
        self,
        task: Task,
        shift_date: datetime.date,
        start_time: datetime.time,
        end_time: datetime.time,
    ):
        """
        Creates the required headcount Schedule slots for a task block.
        If task has a pre-assigned employee, their exact hours and time-off are validated.
        If unavailable, Slot 1 is left unassigned (None) with a warning.
        """
        headcount = max(1, task.required_people)
        assigned_emp = None

        if task.employee:
            is_avail, reason = self._is_employee_available(
                task.employee, shift_date, start_time, end_time
            )
            if is_avail:
                assigned_emp = task.employee
            else:
                self.warnings.append(
                    f"Task '{task.name}' on {shift_date} ({start_time:%H:%M}-{end_time:%H:%M}): {reason} Shift created unassigned for smart scheduler."
                )

        # Slot 1: pre-assigned employee if available, otherwise unassigned
        self.schedules_to_create.append(
            Schedule(
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

        # Exclude tasks linked to inactive projects
        tasks = [t for t in tasks_qs.select_related("project", "department", "employee") if not t.project or t.project.is_active]

        # Separate recurring vs. non-recurring
        recurring_tasks = [t for t in tasks if t.is_recurring]
        non_recurring_tasks = [t for t in tasks if not t.is_recurring]

        # Sort non-recurring tasks by priority descending
        non_recurring_tasks.sort(key=self._task_priority_key, reverse=True)

        # 2. Process Recurring Tasks: repeat on EVERY open day
        for task in recurring_tasks:
            for day in open_days:
                dur = day["duration_hours"] if task.preferred_window == Task.PreferredWindow.OPEN_TO_CLOSE else float(task.duration_hours)
                start_t, end_t = calculate_slot_times(
                    day["open_time"], day["close_time"], dur, task.preferred_window
                )
                self._create_schedule_slots(task, day["date"], start_t, end_t)
                day["scheduled_hours"] += dur

        # 3. Process Non-Recurring Tasks (with multi-day splitting and employee availability checking)
        for task in non_recurring_tasks:
            remaining_dur = float(task.duration_hours)

            # Determine candidate open days
            candidate_days = open_days.copy()
            if task.employee:
                # Filter/sort open days by employee availability for the required window
                available_days = []
                for d in candidate_days:
                    chunk = min(remaining_dur, d["duration_hours"])
                    st, et = calculate_slot_times(
                        d["open_time"], d["close_time"], chunk, task.preferred_window
                    )
                    is_avail, reason = self._is_employee_available(task.employee, d["date"], st, et)
                    if is_avail:
                        available_days.append((d["scheduled_hours"], d))
                    else:
                        self.warnings.append(
                            f"Task '{task.name}' pre-assigned to {task.employee}: {reason}"
                        )

                if available_days:
                    # Sort by least scheduled day among days where employee is genuinely available
                    available_days.sort(key=lambda x: x[0])
                    candidate_days = [item[1] for item in available_days]
                else:
                    self.warnings.append(
                        f"Task '{task.name}' pre-assigned to {task.employee}: employee has no open days with matching availability during the week. Shifts will be created unassigned."
                    )
            else:
                # Workload balancing: sort candidate days by lowest scheduled load
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

                start_t, end_t = calculate_slot_times(
                    curr_day["open_time"], curr_day["close_time"], chunk_dur, task.preferred_window
                )
                self._create_schedule_slots(task, curr_day["date"], start_t, end_t)
                curr_day["scheduled_hours"] += chunk_dur
                day_index += 1

            if remaining_dur > 0:
                self.warnings.append(
                    f"Task '{task.name}' could not be fully scheduled ({remaining_dur:.1f} hours unscheduled due to open hours capacity)."
                )

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
                    qs_to_delete = qs_to_delete.filter(task__department=self.department)
                else:
                    qs_to_delete = qs_to_delete.filter(task__company=self.company)
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
