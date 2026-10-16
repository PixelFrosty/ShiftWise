from ortools.sat.python import cp_model
from django.utils import timezone
from .models import Schedule, Shift, Employee, ShiftAssignment, EmployeeCompatibility, TimeOffRequest
import time
import datetime


class PriorityScheduler:
    """
    Automated Priority Scheduler utilizing Google OR-Tools CP-SAT.
    
    Hard constraints:
    1. Shift coverage met: Each shift gets its required headcount.
    2. No approved time-off violated: Block employees with approved time-off for overlapping dates.
    3. No overlapping shifts: An employee cannot work two shifts that overlap in time.
    4. Max hours per week: Total assigned hours per employee across the schedule <= employee.max_hours_per_week.

    Soft constraints:
    1. Maximize summed productivity score per shift.
    2. Penalize any low-compatibility pair on the same shift, weighted by how low the score is below neutral.
    """

    def __init__(self, schedule: Schedule, employees=None, neutral_score=5.0, time_limit_seconds=10.0):
        self.schedule = schedule
        self.department = schedule.department
        if employees is not None:
            self.employees = list(employees)
        else:
            self.employees = list(Employee.objects.filter(department=self.department))
        self.shifts = list(schedule.shifts.all().order_by('start_time'))
        self.neutral_score = neutral_score
        self.time_limit_seconds = time_limit_seconds

    def solve(self, clear_existing_auto=True, keep_manual=False):
        """
        Solves the shift assignment problem using CP-SAT.
        Returns a result dictionary with status, assignments, stats, and explanations.
        """
        start_time_bench = time.perf_counter()

        if not self.shifts:
            return {
                'success': False,
                'status': 'NO_SHIFTS',
                'message': 'No shifts defined in this schedule to solve.',
                'assignments': [],
                'stats': {}
            }

        if not self.employees:
            return {
                'success': False,
                'status': 'NO_EMPLOYEES',
                'message': f'No employees found in department "{self.department.name}".',
                'assignments': [],
                'stats': {}
            }

        model = cp_model.CpModel()

        # Decision variables: x[shift_id, emp_id] = 1 if emp is assigned to shift, else 0
        x = {}
        for s in self.shifts:
            for e in self.employees:
                x[s.id, e.id] = model.NewBoolVar(f"x_s{s.id}_e{e.id}")

        # If keeping manual assignments, fix pre-existing manual assignments to 1
        manual_assigned_keys = set()
        if keep_manual:
            existing_manual = ShiftAssignment.objects.filter(
                shift__in=self.shifts,
                is_auto_scheduled=False
            )
            for asgn in existing_manual:
                if (asgn.shift_id, asgn.employee_id) in x:
                    model.Add(x[asgn.shift_id, asgn.employee_id] == 1)
                    manual_assigned_keys.add((asgn.shift_id, asgn.employee_id))

        # --- Hard Constraint 1: Shift Coverage Met ---
        # For each shift, sum(x[s, e] for all e) == s.headcount_needed
        # (or <= if headcount_needed exceeds total eligible employees)
        for s in self.shifts:
            model.Add(sum(x[s.id, e.id] for e in self.employees) == s.headcount_needed)

        # --- Hard Constraint 2: No Approved Time-Off Violated ---
        # Look up approved time-off requests for all employees in this schedule window
        schedule_start = min(s.start_time.date() for s in self.shifts)
        schedule_end = max(s.end_time.date() for s in self.shifts)

        approved_time_offs = TimeOffRequest.objects.filter(
            employee__in=self.employees,
            status=TimeOffRequest.Status.APPROVED,
            start_date__lte=schedule_end,
            end_date__gte=schedule_start
        )

        time_off_map = set() # (employee_id, date)
        for tor in approved_time_offs:
            curr = tor.start_date
            while curr <= tor.end_date:
                time_off_map.add((tor.employee_id, curr))
                curr += datetime.timedelta(days=1)

        for s in self.shifts:
            shift_dates = {s.start_time.date(), s.end_time.date()}
            for e in self.employees:
                if any((e.id, d) in time_off_map for d in shift_dates):
                    # Forbid this assignment
                    model.Add(x[s.id, e.id] == 0)

        # --- Hard Constraint 3: No Overlapping Shifts for the Same Employee ---
        # For any two shifts s1, s2 that overlap in time: x[s1, e] + x[s2, e] <= 1
        num_shifts = len(self.shifts)
        for i in range(num_shifts):
            for j in range(i + 1, num_shifts):
                s1 = self.shifts[i]
                s2 = self.shifts[j]
                # Check if s1 and s2 overlap: s1.start < s2.end and s2.start < s1.end
                if s1.start_time < s2.end_time and s2.start_time < s1.end_time:
                    for e in self.employees:
                        model.Add(x[s1.id, e.id] + x[s2.id, e.id] <= 1)

        # --- Hard Constraint 4: Max Hours Per Week Per Employee ---
        # sum(duration_minutes(s) * x[s, e]) <= e.max_hours_per_week * 60
        shift_durations_minutes = {
            s.id: int(round((s.end_time - s.start_time).total_seconds() / 60))
            for s in self.shifts
        }

        for e in self.employees:
            max_minutes = int(e.max_hours_per_week * 60)
            model.Add(
                sum(shift_durations_minutes[s.id] * x[s.id, e.id] for s in self.shifts) <= max_minutes
            )

        # --- Soft Constraints: Objective Function ---
        # 1. Maximize summed productivity score per shift:
        #    reward: sum(x[s, e] * int(e.productivity_score * 100))
        # 2. Penalize any low-compatibility pair on the same shift, weighted by how low score is below threshold:
        #    score < 5.0 -> penalty = int((5.0 - score) * 100) * y[s, e1, e2]
        objective_terms = []

        # Productivity terms (Weight = 10)
        PROD_WEIGHT = 10
        for s in self.shifts:
            for e in self.employees:
                score_scaled = int(round(e.productivity_score * 100))
                objective_terms.append(PROD_WEIGHT * score_scaled * x[s.id, e.id])

        # Compatibility terms (Weight = 25)
        COMPAT_PENALTY_WEIGHT = 25
        compat_matrix = EmployeeCompatibility.get_compatibility_matrix()
        emp_ids = [e.id for e in self.employees]
        emp_dict = {e.id: e for e in self.employees}

        for s in self.shifts:
            # Pairwise compatibility only relevant if shift needs >= 2 people
            if s.headcount_needed >= 2:
                for i in range(len(emp_ids)):
                    for j in range(i + 1, len(emp_ids)):
                        id1, id2 = emp_ids[i], emp_ids[j]
                        pair_key = (min(id1, id2), max(id1, id2))
                        pair_score = compat_matrix.get(pair_key, self.neutral_score)

                        # If compatibility is below neutral (e.g. friction / toxic pair), apply penalty
                        if pair_score < self.neutral_score:
                            deficit = self.neutral_score - pair_score
                            penalty_scaled = int(round(deficit * 100))
                            # y is 1 if both id1 and id2 are assigned to shift s
                            y_pair = model.NewBoolVar(f"pair_s{s.id}_e{id1}_e{id2}")
                            model.AddBoolAnd([x[s.id, id1], x[s.id, id2]]).OnlyEnforceIf(y_pair)
                            model.AddBoolOr([x[s.id, id1].Not(), x[s.id, id2].Not()]).OnlyEnforceIf(y_pair.Not())

                            objective_terms.append(-COMPAT_PENALTY_WEIGHT * penalty_scaled * y_pair)

                        # Bonus for synergy (> 5.0)
                        elif pair_score > self.neutral_score:
                            surplus = pair_score - self.neutral_score
                            bonus_scaled = int(round(surplus * 50))
                            y_pair = model.NewBoolVar(f"pair_bonus_s{s.id}_e{id1}_e{id2}")
                            model.AddBoolAnd([x[s.id, id1], x[s.id, id2]]).OnlyEnforceIf(y_pair)
                            model.AddBoolOr([x[s.id, id1].Not(), x[s.id, id2].Not()]).OnlyEnforceIf(y_pair.Not())

                            objective_terms.append(COMPAT_PENALTY_WEIGHT * bonus_scaled * y_pair)

        model.Maximize(sum(objective_terms))

        # Solve
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_search_workers = 4
        status = solver.Solve(model)

        elapsed = round((time.perf_counter() - start_time_bench) * 1000, 2)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            # Diagnose reason for infeasibility
            total_needed_hours = sum(s.duration_hours * s.headcount_needed for s in self.shifts)
            total_avail_hours = sum(e.max_hours_per_week for e in self.employees)

            diag = []
            if total_needed_hours > total_avail_hours:
                diag.append(f"Shift headcount requires {total_needed_hours:.1f} hrs, but all {len(self.employees)} employees combined max out at {total_avail_hours:.1f} hrs.")
            if approved_time_offs.exists():
                diag.append(f"{approved_time_offs.count()} approved time-off request(s) reduce availability for some dates.")
            
            return {
                'success': False,
                'status': 'INFEASIBLE' if status == cp_model.INFEASIBLE else 'UNKNOWN',
                'message': 'No valid schedule found satisfying all hard constraints (coverage, time-off, non-overlapping shifts, max weekly hours).',
                'diagnosis': diag,
                'solve_time_ms': elapsed,
                'assignments': [],
                'stats': {}
            }

        # Extract assignments
        planned_assignments = []
        assigned_hours_per_emp = {e.id: 0.0 for e in self.employees}
        shift_obj_map = {s.id: s for s in self.shifts}
        total_prod_sum = 0.0
        total_compat_penalties = 0

        for s in self.shifts:
            shift_assigned_emps = []
            for e in self.employees:
                if solver.Value(x[s.id, e.id]) == 1:
                    is_manual = (s.id, e.id) in manual_assigned_keys
                    planned_assignments.append({
                        'shift': s,
                        'shift_id': s.id,
                        'employee': e,
                        'employee_id': e.id,
                        'is_manual': is_manual
                    })
                    shift_assigned_emps.append(e)
                    assigned_hours_per_emp[e.id] += s.duration_hours
                    total_prod_sum += e.productivity_score

            # Check compatibility friction on this shift
            for i in range(len(shift_assigned_emps)):
                for j in range(i + 1, len(shift_assigned_emps)):
                    e1, e2 = shift_assigned_emps[i], shift_assigned_emps[j]
                    pair_score = compat_matrix.get((min(e1.id, e2.id), max(e1.id, e2.id)), self.neutral_score)
                    if pair_score < self.neutral_score:
                        total_compat_penalties += 1

        return {
            'success': True,
            'status': 'OPTIMAL' if status == cp_model.OPTIMAL else 'FEASIBLE',
            'message': f"Schedule generated successfully ({'Optimal' if status == cp_model.OPTIMAL else 'Feasible'}).",
            'solve_time_ms': elapsed,
            'assignments': planned_assignments,
            'stats': {
                'total_shifts': len(self.shifts),
                'total_assignments': len(planned_assignments),
                'total_headcount_needed': sum(s.headcount_needed for s in self.shifts),
                'assigned_hours_per_emp': {
                    emp_dict[eid].name: round(hrs, 2)
                    for eid, hrs in assigned_hours_per_emp.items()
                },
                'total_productivity_sum': round(total_prod_sum, 1),
                'low_compat_pairs_on_shift': total_compat_penalties,
                'objective_value': solver.ObjectiveValue()
            }
        }

    def apply_solution(self, planned_assignments, user=None, clear_existing_auto=True):
        """
        Commits planned assignments to database for manager review in Phase 2 editor.
        """
        if clear_existing_auto:
            ShiftAssignment.objects.filter(
                shift__in=self.shifts,
                is_auto_scheduled=True
            ).delete()

        created_objs = []
        for item in planned_assignments:
            if item.get('is_manual'):
                continue
            asgn, created = ShiftAssignment.objects.update_or_create(
                shift=item['shift'],
                employee=item['employee'],
                defaults={
                    'assigned_by': user,
                    'is_auto_scheduled': True
                }
            )
            created_objs.append(asgn)
        return created_objs
