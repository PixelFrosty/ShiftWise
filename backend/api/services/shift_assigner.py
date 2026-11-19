import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from ortools.sat.python import cp_model

from ..models import (
    AvailabilitySlot,
    Company,
    CompatibilityScore,
    Department,
    EmployeeProfile,
    Schedule,
    Task,
    TimeOffRequest,
)


def time_to_minutes(t: datetime.time) -> int:
    return t.hour * 60 + t.minute


def shift_duration_minutes(start: datetime.time, end: datetime.time) -> int:
    return max(0, time_to_minutes(end) - time_to_minutes(start))


class SmartShiftAssignerService:
    """
    Optimally assigns employees to unassigned Schedule shift slots using OR-Tools CP-SAT.
    Enforces:
    - Skill requirements (hard constraint)
    - Availability slots & approved time-off (hard constraint)
    - No double-booking / concurrency overlap (hard constraint)
    - Configurable max weekly hours per employee (hard constraint)
    - Multi-person task headcount uniqueness (hard constraint)
    - Ad-hoc forced groupings (hard constraint)
    Maximizes:
    - Total shifts filled (top priority)
    - Pairwise compatibility scores on multi-person shifts
    - Fair workload distribution across available staff
    """

    def __init__(
        self,
        company: Company,
        week_start: datetime.date,
        department: Optional[Department] = None,
        forced_groups: Optional[List[List[int]]] = None,
    ):
        self.company = company
        # Normalize to Monday
        self.week_start = week_start - datetime.timedelta(days=week_start.weekday())
        self.week_end = self.week_start + datetime.timedelta(days=6)
        self.department = department
        self.forced_groups: List[List[int]] = forced_groups or []

    def _is_employee_available(
        self,
        employee_id: int,
        shift_date: datetime.date,
        start_time: datetime.time,
        end_time: datetime.time,
        time_off_map: Dict[int, List[Tuple[datetime.date, datetime.date]]],
        slots_map: Dict[int, Dict[int, List[Tuple[datetime.time, datetime.time]]]],
        has_any_slots_map: Dict[int, bool],
    ) -> bool:
        """Checks if employee is available for the exact shift window."""
        # 1. Approved time-off check
        for start_d, end_d in time_off_map.get(employee_id, []):
            if start_d <= shift_date <= end_d:
                return False

        # 2. Availability slots check
        if has_any_slots_map.get(employee_id, False):
            dow = shift_date.weekday()
            emp_dow_slots = slots_map.get(employee_id, {}).get(dow, [])
            if not emp_dow_slots:
                return False

            covered = any(st <= start_time and et >= end_time for st, et in emp_dow_slots)
            if not covered:
                return False

        return True

    def assign(self) -> Dict[str, Any]:
        # 1. Fetch schedules in the week window
        schedules_qs = Schedule.objects.filter(
            shift_date__gte=self.week_start,
            shift_date__lte=self.week_end,
            status=Schedule.Status.SCHEDULED,
        )
        if self.department:
            schedules_qs = schedules_qs.filter(
                Q(task__department=self.department) | Q(department=self.department)
            )
        else:
            schedules_qs = schedules_qs.filter(
                Q(task__company=self.company) | Q(company=self.company)
            )

        all_schedules = list(
            schedules_qs.select_related("task", "employee", "employee__user").prefetch_related("task__skills")
        )

        unassigned_shifts = [s for s in all_schedules if s.employee_id is None]
        pre_assigned_shifts = [s for s in all_schedules if s.employee_id is not None]

        if not unassigned_shifts:
            return {
                "company_id": self.company.id,
                "week_start": self.week_start.isoformat(),
                "week_end": self.week_end.isoformat(),
                "status": "NO_OP",
                "message": "No unassigned shifts to schedule for this week.",
                "total_unassigned_slots": 0,
                "slots_filled": 0,
                "unfillable_slots": 0,
                "assigned_shifts": [],
            }

        # 2. Fetch eligible employees
        emp_qs = EmployeeProfile.objects.filter(company=self.company)
        if self.department:
            emp_qs = emp_qs.filter(department=self.department)
        employees = list(emp_qs.prefetch_related("skills").select_related("user"))

        if not employees:
            raise ValidationError("No eligible employees found for this company/department.")

        emp_ids = [e.id for e in employees]
        emp_by_id = {e.id: e for e in employees}
        emp_skills: Dict[int, Set[int]] = {e.id: {sk.id for sk in e.skills.all()} for e in employees}
        emp_max_hours: Dict[int, float] = {e.id: float(e.max_weekly_hours or 40.0) for e in employees}

        # 3. Pre-fetch availability slots and time-off requests
        time_off_qs = TimeOffRequest.objects.filter(
            employee_id__in=emp_ids,
            status=TimeOffRequest.Status.APPROVED,
            end_date__gte=self.week_start,
            start_date__lte=self.week_end,
        )
        time_off_map: Dict[int, List[Tuple[datetime.date, datetime.date]]] = {}
        for req in time_off_qs:
            time_off_map.setdefault(req.employee_id, []).append((req.start_date, req.end_date))

        slots_qs = AvailabilitySlot.objects.filter(employee_id__in=emp_ids)
        slots_map: Dict[int, Dict[int, List[Tuple[datetime.time, datetime.time]]]] = {}
        has_any_slots_map: Dict[int, bool] = {eid: False for eid in emp_ids}
        for sl in slots_qs:
            has_any_slots_map[sl.employee_id] = True
            slots_map.setdefault(sl.employee_id, {}).setdefault(sl.day_of_week, []).append(
                (sl.start_time, sl.end_time)
            )

        # 4. Pre-assigned shifts load and interval tracking
        pre_assigned_minutes: Dict[int, int] = {eid: 0 for eid in emp_ids}
        pre_assigned_intervals: Dict[int, List[Tuple[datetime.date, datetime.time, datetime.time]]] = {
            eid: [] for eid in emp_ids
        }
        for s in pre_assigned_shifts:
            dur = shift_duration_minutes(s.start_time, s.end_time)
            if s.employee_id in pre_assigned_minutes:
                pre_assigned_minutes[s.employee_id] += dur
                pre_assigned_intervals[s.employee_id].append((s.shift_date, s.start_time, s.end_time))

        # 5. Fetch compatibility scores
        compat_qs = CompatibilityScore.objects.filter(
            employee_a_id__in=emp_ids, employee_b_id__in=emp_ids
        )
        compat_map: Dict[Tuple[int, int], float] = {}
        for cs in compat_qs:
            a, b = min(cs.employee_a_id, cs.employee_b_id), max(cs.employee_a_id, cs.employee_b_id)
            compat_map[(a, b)] = float(cs.score)

        # 6. Group shifts into task events (for multi-person coordination)
        # An event is defined by (task_id, shift_date, start_time, end_time)
        events_map: Dict[Tuple[Any, datetime.date, datetime.time, datetime.time], Dict[str, Any]] = {}
        for s in all_schedules:
            key = (s.task_id if s.task_id else s.task_name, s.shift_date, s.start_time, s.end_time)
            if key not in events_map:
                events_map[key] = {
                    "task": s.task,
                    "shift_date": s.shift_date,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "unassigned_slots": [],
                    "pre_assigned_employees": [],
                }
            if s.employee_id is not None:
                events_map[key]["pre_assigned_employees"].append(s.employee_id)
            else:
                events_map[key]["unassigned_slots"].append(s)

        # 7. Build CP-SAT Model
        model = cp_model.CpModel()

        # Decision variables: x[e_id, s_id] = 1 if employee e works unassigned shift s
        x: Dict[Tuple[int, int], cp_model.BoolVar] = {}
        unfilled: Dict[int, cp_model.BoolVar] = {}
        shift_durations: Dict[int, int] = {}
        eligible_employees_for_shift: Dict[int, List[int]] = {}

        for s in unassigned_shifts:
            dur_min = shift_duration_minutes(s.start_time, s.end_time)
            shift_durations[s.id] = dur_min
            unfilled[s.id] = model.NewBoolVar(f"unfilled_{s.id}")
            eligible_employees_for_shift[s.id] = []

            req_skills = {sk.id for sk in s.task.skills.all()} if s.task else set()

            for e in employees:
                # Condition 1: Skill alignment - employee must possess all required skills
                if req_skills and not req_skills.issubset(emp_skills[e.id]):
                    continue

                # Condition 2: Exact availability and no time-off
                if not self._is_employee_available(
                    e.id, s.shift_date, s.start_time, s.end_time, time_off_map, slots_map, has_any_slots_map
                ):
                    continue

                # Condition 3: Overlap check with employee's own pre-assigned shifts
                has_pre_overlap = any(
                    pad == s.shift_date and max(past, s.start_time) < min(paet, s.end_time)
                    for pad, past, paet in pre_assigned_intervals.get(e.id, [])
                )
                if has_pre_overlap:
                    continue

                var = model.NewBoolVar(f"x_{e.id}_{s.id}")
                x[(e.id, s.id)] = var
                eligible_employees_for_shift[s.id].append(e.id)

            # Slot filling constraint: sum(x[e, s]) + unfilled[s] == 1
            slot_vars = [x[(e_id, s.id)] for e_id in eligible_employees_for_shift[s.id]]
            model.Add(sum(slot_vars) + unfilled[s.id] == 1)

        # 8. Constraints within each Task Event (Headcount & Multi-person uniqueness)
        event_employee_in_event: Dict[Tuple[int, int], Any] = {}  # (event_idx, emp_id) -> bool expr

        for ev_idx, (ev_key, ev_data) in enumerate(events_map.items()):
            unassigned_in_ev = ev_data["unassigned_slots"]
            pre_in_ev = ev_data["pre_assigned_employees"]

            for e_id in emp_ids:
                if e_id in pre_in_ev:
                    # Already pre-assigned to this event -> cannot be assigned to another slot in same event
                    for s in unassigned_in_ev:
                        if (e_id, s.id) in x:
                            model.Add(x[(e_id, s.id)] == 0)
                    # Constant indicator 1
                    event_employee_in_event[(ev_idx, e_id)] = 1
                else:
                    slots_active_for_e = [x[(e_id, s.id)] for s in unassigned_in_ev if (e_id, s.id) in x]
                    if slots_active_for_e:
                        # Cannot fill more than 1 slot in the same event
                        model.Add(sum(slots_active_for_e) <= 1)
                        # Boolean variable for whether e is in this event
                        in_ev_var = model.NewBoolVar(f"in_ev_{ev_idx}_{e_id}")
                        model.Add(in_ev_var == sum(slots_active_for_e))
                        event_employee_in_event[(ev_idx, e_id)] = in_ev_var
                    else:
                        event_employee_in_event[(ev_idx, e_id)] = 0

        # 9. Concurrency / Overlap Constraints between Unassigned Shifts
        # If two unassigned shifts s1 and s2 overlap in time on the same date: an employee can work at most one
        for i in range(len(unassigned_shifts)):
            s1 = unassigned_shifts[i]
            for j in range(i + 1, len(unassigned_shifts)):
                s2 = unassigned_shifts[j]
                if s1.shift_date == s2.shift_date:
                    # Check time overlap
                    if max(s1.start_time, s2.start_time) < min(s1.end_time, s2.end_time):
                        for e_id in emp_ids:
                            if (e_id, s1.id) in x and (e_id, s2.id) in x:
                                model.Add(x[(e_id, s1.id)] + x[(e_id, s2.id)] <= 1)

        # 10. Max Weekly Hours Constraints
        for e in employees:
            max_mins = int(emp_max_hours[e.id] * 60)
            emp_shift_vars = [
                shift_durations[s.id] * x[(e.id, s.id)]
                for s in unassigned_shifts
                if (e.id, s.id) in x
            ]
            if emp_shift_vars:
                model.Add(sum(emp_shift_vars) + pre_assigned_minutes[e.id] <= max_mins)

        # 11. Ad-Hoc Forced Groupings (Option C)
        for group in self.forced_groups:
            valid_group = [gid for gid in group if gid in emp_by_id]
            if len(valid_group) < 2:
                continue

            for ev_idx, (ev_key, ev_data) in enumerate(events_map.items()):
                total_event_slots = len(ev_data["unassigned_slots"]) + len(ev_data["pre_assigned_employees"])
                if total_event_slots < 2:
                    continue  # Forced grouping applies to multi-person tasks

                lead = valid_group[0]
                for partner in valid_group[1:]:
                    lead_in = event_employee_in_event.get((ev_idx, lead), 0)
                    partner_in = event_employee_in_event.get((ev_idx, partner), 0)
                    model.Add(lead_in == partner_in)

        # 12. Objective Terms
        objective_terms = []

        # Term A: Filling Shifts (Highest weight: 100,000 penalty per unfilled slot)
        W_UNFILLED = 100_000
        for s in unassigned_shifts:
            objective_terms.append(-W_UNFILLED * unfilled[s.id])

        # Term B: Compatibility Maximization on Multi-Person Task Events
        pair_compat_vars = []
        for ev_idx, (ev_key, ev_data) in enumerate(events_map.items()):
            total_event_slots = len(ev_data["unassigned_slots"]) + len(ev_data["pre_assigned_employees"])
            if total_event_slots < 2:
                continue

            for i in range(len(emp_ids)):
                e1 = emp_ids[i]
                e1_in = event_employee_in_event.get((ev_idx, e1), 0)
                if isinstance(e1_in, int) and e1_in == 0:
                    continue

                for j in range(i + 1, len(emp_ids)):
                    e2 = emp_ids[j]
                    e2_in = event_employee_in_event.get((ev_idx, e2), 0)
                    if isinstance(e2_in, int) and e2_in == 0:
                        continue

                    # Score from 0 to 10 scaled to integer (0 to 100)
                    pair_key = (min(e1, e2), max(e1, e2))
                    raw_score = compat_map.get(pair_key, 5.0)  # neutral default 5.0
                    score_int = int(round(raw_score * 10))

                    if isinstance(e1_in, int) and e1_in == 1 and isinstance(e2_in, int) and e2_in == 1:
                        # Both fixed pre-assigned
                        objective_terms.append(score_int)
                    elif isinstance(e1_in, int) and e1_in == 1:
                        # e1 fixed, e2 is variable
                        objective_terms.append(score_int * e2_in)
                    elif isinstance(e2_in, int) and e2_in == 1:
                        # e2 fixed, e1 is variable
                        objective_terms.append(score_int * e1_in)
                    else:
                        # Both are variables: pair_active = e1_in AND e2_in
                        pair_var = model.NewBoolVar(f"pair_{ev_idx}_{e1}_{e2}")
                        model.AddBoolAnd([e1_in, e2_in]).OnlyEnforceIf(pair_var)
                        model.AddBoolOr([e1_in.Not(), e2_in.Not()]).OnlyEnforceIf(pair_var.Not())
                        objective_terms.append(score_int * pair_var)

        # Term C: Workload Fairness (Minimize deviation from target minutes)
        total_demand_minutes = sum(shift_durations.values()) + sum(pre_assigned_minutes.values())
        target_minutes_per_emp = total_demand_minutes // max(1, len(employees))

        fairness_penalties = []
        for e in employees:
            emp_vars = [
                shift_durations[s.id] * x[(e.id, s.id)]
                for s in unassigned_shifts
                if (e.id, s.id) in x
            ]
            total_emp_mins = sum(emp_vars) + pre_assigned_minutes[e.id]
            dev = model.NewIntVar(0, 100_000, f"dev_{e.id}")
            model.Add(dev >= total_emp_mins - target_minutes_per_emp)
            model.Add(dev >= target_minutes_per_emp - total_emp_mins)
            fairness_penalties.append(dev)

        # Multi-objective: fill shifts (weight 100,000) + compatibility (weight 10) - fairness (weight 1)
        model.Maximize(sum(objective_terms) - sum(fairness_penalties))

        # 13. Solve Model
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        solver.parameters.num_workers = 4

        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return {
                "company_id": self.company.id,
                "week_start": self.week_start.isoformat(),
                "week_end": self.week_end.isoformat(),
                "solver_status": "INFEASIBLE",
                "message": "Could not find a feasible schedule satisfying all hard constraints.",
                "total_unassigned_slots": len(unassigned_shifts),
                "slots_filled": 0,
                "unfillable_slots": len(unassigned_shifts),
                "assigned_shifts": [],
            }

        # 14. Extract Solution
        assigned_shifts_records = []
        unfillable_shifts = []

        with transaction.atomic():
            for s in unassigned_shifts:
                is_unfilled = solver.Value(unfilled[s.id]) == 1
                if is_unfilled:
                    shift_req_skills = {sk.id for sk in s.task.skills.all()} if s.task else set()
                    if shift_req_skills and not any(shift_req_skills.issubset(emp_skills[e.id]) for e in employees):
                        skill_names = [sk.name for sk in s.task.skills.all()]
                        reason = f"No employee has the required skill(s): {', '.join(skill_names)}."
                    else:
                        reason = "No eligible or available employee found within hours cap."
                    unfillable_shifts.append(
                        {
                            "schedule_id": s.id,
                            "task_name": s.task_name,
                            "shift_date": s.shift_date.isoformat(),
                            "start_time": s.start_time.strftime("%H:%M"),
                            "end_time": s.end_time.strftime("%H:%M"),
                            "reason": reason,
                        }
                    )
                else:
                    assigned_emp_id = None
                    for e_id in eligible_employees_for_shift[s.id]:
                        if solver.Value(x[(e_id, s.id)]) == 1:
                            assigned_emp_id = e_id
                            break

                    if assigned_emp_id is not None:
                        s.employee_id = assigned_emp_id
                        assigned_shifts_records.append(s)

            if assigned_shifts_records:
                Schedule.objects.bulk_update(assigned_shifts_records, ["employee"])

        # 15. Calculate Metrics
        total_filled = len(assigned_shifts_records)
        assigned_output = [
            {
                "schedule_id": s.id,
                "task_name": s.task_name,
                "shift_date": s.shift_date.isoformat(),
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
                "employee_id": s.employee_id,
                "employee_name": emp_by_id[s.employee_id].user.get_full_name()
                or emp_by_id[s.employee_id].user.email,
            }
            for s in assigned_shifts_records
        ]

        # Calculate average compatibility for co-assigned multi-person shifts
        pair_scores = []
        for ev_idx, (ev_key, ev_data) in enumerate(events_map.items()):
            co_assigned = []
            for s in ev_data["unassigned_slots"]:
                if s.employee_id:
                    co_assigned.append(s.employee_id)
            co_assigned.extend(ev_data["pre_assigned_employees"])
            co_assigned = list(set(co_assigned))

            for i in range(len(co_assigned)):
                for j in range(i + 1, len(co_assigned)):
                    pair = (min(co_assigned[i], co_assigned[j]), max(co_assigned[i], co_assigned[j]))
                    pair_scores.append(compat_map.get(pair, 5.0))

        avg_compat = (
            round(sum(pair_scores) / len(pair_scores), 2) if pair_scores else None
        )

        return {
            "company_id": self.company.id,
            "week_start": self.week_start.isoformat(),
            "week_end": self.week_end.isoformat(),
            "solver_status": "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            "total_unassigned_slots": len(unassigned_shifts),
            "slots_filled": total_filled,
            "unfillable_slots": len(unfillable_shifts),
            "average_compatibility_score": avg_compat,
            "assigned_shifts": assigned_output,
            "unfillable_details": unfillable_shifts,
        }
