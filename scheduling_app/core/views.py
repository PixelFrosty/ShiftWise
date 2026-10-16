from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count
from django.utils import timezone
import datetime

from .models import (
    User, Department, Employee, EmployeeCompatibility,
    Schedule, Shift, ShiftAssignment, TimeOffRequest
)
from .forms import (
    EmployeeForm, CompatibilityForm, ScheduleForm,
    ShiftForm, ShiftAssignmentForm, TimeOffRequestForm
)
from .permissions import role_required, check_schedule_access, can_manage_time_off
from .scheduler import PriorityScheduler


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username} ({user.get_role_display()})!")
            return redirect('dashboard')
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')


@login_required
def dashboard_view(request):
    user = request.user
    context = {'user': user}

    if user.is_ceo:
        context.update({
            'total_departments': Department.objects.count(),
            'total_employees': Employee.objects.count(),
            'total_schedules': Schedule.objects.count(),
            'pending_time_offs': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
            'recent_schedules': Schedule.objects.all().order_by('-created_at')[:5],
            'pending_requests_list': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING)[:5],
        })
    elif user.is_manager:
        user_emp = getattr(user, 'employee_profile', None)
        dept = user_emp.department if user_emp else None
        schedules_qs = Schedule.objects.for_user(user)
        context.update({
            'my_department': dept,
            'department_employees': Employee.objects.filter(department=dept) if dept else Employee.objects.all(),
            'schedules': schedules_qs.order_by('-week_start_date')[:5],
            'pending_time_offs': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
            'pending_requests_list': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING)[:5],
        })
    else: # Employee
        user_emp = getattr(user, 'employee_profile', None)
        my_shifts = []
        my_requests = []
        if user_emp:
            my_shifts = ShiftAssignment.objects.filter(
                employee=user_emp,
                shift__schedule__status=Schedule.Status.PUBLISHED,
                shift__start_time__gte=timezone.now()
            ).order_by('shift__start_time')[:10]
            my_requests = TimeOffRequest.objects.filter(employee=user_emp).order_by('-created_at')[:5]

        context.update({
            'employee_profile': user_emp,
            'my_shifts': my_shifts,
            'my_requests': my_requests,
        })

    return render(request, 'core/dashboard.html', context)


# ==========================================
# Phase 1: Employee Input & Compatibility
# ==========================================

@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def employee_list_view(request):
    query = request.GET.get('q', '')
    dept_id = request.GET.get('dept', '')
    employees = Employee.objects.select_related('department', 'user').all()

    if query:
        employees = employees.filter(Q(name__icontains=query) | Q(position__icontains=query))
    if dept_id:
        employees = employees.filter(department_id=dept_id)

    departments = Department.objects.all()
    return render(request, 'core/employee_list.html', {
        'employees': employees,
        'departments': departments,
        'query': query,
        'selected_dept': dept_id
    })


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def employee_create_view(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            emp = form.save()
            messages.success(request, f"Employee {emp.name} created successfully.")
            return redirect('employee_list')
    else:
        form = EmployeeForm()
    return render(request, 'core/employee_form.html', {'form': form, 'title': 'Add New Employee'})


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def employee_update_view(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=emp)
        if form.is_valid():
            form.save()
            messages.success(request, f"Employee {emp.name} updated successfully.")
            return redirect('employee_list')
    else:
        form = EmployeeForm(instance=emp)
    return render(request, 'core/employee_form.html', {'form': form, 'title': f'Edit Employee: {emp.name}', 'emp': emp})


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def employee_delete_view(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        name = emp.name
        emp.delete()
        messages.success(request, f"Employee {name} removed.")
        return redirect('employee_list')
    return render(request, 'core/employee_confirm_delete.html', {'employee': emp})


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def compatibility_list_view(request):
    pairs = EmployeeCompatibility.objects.select_related('employee_a', 'employee_b').all()
    if request.method == 'POST':
        form = CompatibilityForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            try:
                instance.save()
                messages.success(request, f"Compatibility rating between {instance.employee_a.name} and {instance.employee_b.name} saved.")
                return redirect('compatibility_list')
            except ValidationError as e:
                form.add_error(None, e.messages if hasattr(e, 'messages') else str(e))
    else:
        form = CompatibilityForm()

    return render(request, 'core/compatibility_list.html', {
        'pairs': pairs,
        'form': form,
    })


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def compatibility_delete_view(request, pk):
    pair = get_object_or_404(EmployeeCompatibility, pk=pk)
    if request.method == 'POST':
        pair.delete()
        messages.success(request, "Pairwise compatibility score removed (reset to neutral).")
        return redirect('compatibility_list')
    return render(request, 'core/compatibility_confirm_delete.html', {'pair': pair})


# ==========================================
# Phase 2: Schedule Model and Manual Editor
# ==========================================

@login_required
def schedule_list_view(request):
    # Enforces role and object scoping in backend
    schedules = Schedule.objects.for_user(request.user).select_related('department', 'created_by')
    return render(request, 'core/schedule_list.html', {'schedules': schedules})


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def schedule_create_view(request):
    if request.method == 'POST':
        form = ScheduleForm(request.POST)
        if form.is_valid():
            sched = form.save(commit=False)
            sched.created_by = request.user
            sched.save()
            messages.success(request, f"Schedule '{sched.title}' created.")
            return redirect('schedule_detail', pk=sched.pk)
    else:
        initial_date = timezone.now().date()
        # default to next Monday
        monday = initial_date + datetime.timedelta(days=(0 - initial_date.weekday()) % 7)
        form = ScheduleForm(initial={'week_start_date': monday})
    return render(request, 'core/schedule_form.html', {'form': form, 'title': 'Create New Schedule'})


@login_required
def schedule_detail_view(request, pk):
    schedule = get_object_or_404(Schedule.objects.select_related('department', 'created_by'), pk=pk)
    check_schedule_access(request, schedule, edit=False)
    can_edit = (request.user.is_ceo or request.user.is_manager)

    # Organize shifts by day of week (0 to 6)
    days_data = []
    base_monday = schedule.week_start_date
    all_shifts = list(schedule.shifts.prefetch_related('assignments__employee').all().order_by('start_time'))

    for offset in range(7):
        day_date = base_monday + datetime.timedelta(days=offset)
        day_shifts = [s for s in all_shifts if s.start_time.date() == day_date]
        days_data.append({
            'date': day_date,
            'day_name': day_date.strftime('%A'),
            'shifts': day_shifts
        })

    eligible_employees = Employee.objects.filter(department=schedule.department).order_by('name')

    shift_form = ShiftForm(initial={
        'start_time': datetime.datetime.combine(base_monday, datetime.time(9, 0)),
        'end_time': datetime.datetime.combine(base_monday, datetime.time(17, 0)),
    })

    return render(request, 'core/schedule_detail.html', {
        'schedule': schedule,
        'days_data': days_data,
        'can_edit': can_edit,
        'shift_form': shift_form,
        'eligible_employees': eligible_employees,
    })


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def schedule_update_status_view(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    check_schedule_access(request, schedule, edit=True)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Schedule.Status.choices):
            schedule.status = new_status
            schedule.save()
            messages.success(request, f"Schedule status updated to {schedule.get_status_display()}.")
    return redirect('schedule_detail', pk=pk)


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def shift_create_view(request, schedule_pk):
    schedule = get_object_or_404(Schedule, pk=schedule_pk)
    check_schedule_access(request, schedule, edit=True)

    if request.method == 'POST':
        form = ShiftForm(request.POST)
        if form.is_valid():
            shift = form.save(commit=False)
            shift.schedule = schedule
            try:
                shift.clean()
                shift.save()
                messages.success(request, f"Shift '{shift.role_title}' added.")
            except ValidationError as e:
                messages.error(request, e.messages[0] if hasattr(e, 'messages') else str(e))
        else:
            messages.error(request, "Invalid shift details provided.")
    return redirect('schedule_detail', pk=schedule_pk)


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def shift_delete_view(request, pk):
    shift = get_object_or_404(Shift, pk=pk)
    schedule_pk = shift.schedule_id
    check_schedule_access(request, shift.schedule, edit=True)

    if request.method == 'POST':
        shift.delete()
        messages.success(request, "Shift removed.")
    return redirect('schedule_detail', pk=schedule_pk)


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def assign_employee_view(request, shift_pk):
    shift = get_object_or_404(Shift.objects.select_related('schedule'), pk=shift_pk)
    check_schedule_access(request, shift.schedule, edit=True)

    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        employee = get_object_or_404(Employee, pk=employee_id)

        # Check time-off blocking (Phase 3 enforcement)
        if employee.has_approved_time_off(shift.start_time, shift.end_time):
            messages.error(
                request,
                f"Cannot assign {employee.name}: They have approved time-off during this period!"
            )
            return redirect('schedule_detail', pk=shift.schedule_id)

        # Check overlapping shifts
        overlapping = ShiftAssignment.objects.filter(
            employee=employee,
            shift__start_time__lt=shift.end_time,
            shift__end_time__gt=shift.start_time
        ).exclude(shift=shift)

        if overlapping.exists():
            conflict = overlapping.first().shift
            messages.warning(
                request,
                f"Notice: {employee.name} already has an overlapping shift ({conflict.role_title} on {conflict.start_time.strftime('%a %H:%M')})."
            )

        # Create assignment
        assignment, created = ShiftAssignment.objects.get_or_create(
            shift=shift,
            employee=employee,
            defaults={'assigned_by': request.user, 'is_auto_scheduled': False}
        )
        if created:
            messages.success(request, f"{employee.name} assigned to {shift.role_title} manually.")
        else:
            messages.info(request, f"{employee.name} is already assigned to this shift.")

    return redirect('schedule_detail', pk=shift.schedule_id)


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def unassign_employee_view(request, assignment_pk):
    assignment = get_object_or_404(ShiftAssignment.objects.select_related('shift__schedule', 'employee'), pk=assignment_pk)
    schedule_pk = assignment.shift.schedule_id
    check_schedule_access(request, assignment.shift.schedule, edit=True)

    if request.method == 'POST':
        name = assignment.employee.name
        assignment.delete()
        messages.success(request, f"Removed {name} from shift.")
    return redirect('schedule_detail', pk=schedule_pk)


# ==========================================
# Phase 3: Request Offs & Pile-up Spotter
# ==========================================

def get_people_off_pileup(start_date, end_date, department=None):
    """
    Returns a per-day count and list of employees with approved (and pending) time off.
    Enables managers to spot pile-ups before approving.
    """
    days = {}
    curr = start_date
    delta = datetime.timedelta(days=1)
    while curr <= end_date:
        qs = TimeOffRequest.objects.filter(
            start_date__lte=curr,
            end_date__gte=curr,
            status=TimeOffRequest.Status.APPROVED
        ).select_related('employee__department')
        if department:
            qs = qs.filter(employee__department=department)

        pending_qs = TimeOffRequest.objects.filter(
            start_date__lte=curr,
            end_date__gte=curr,
            status=TimeOffRequest.Status.PENDING
        ).select_related('employee__department')
        if department:
            pending_qs = pending_qs.filter(employee__department=department)

        days[curr] = {
            'date': curr,
            'approved_count': qs.count(),
            'approved_names': [r.employee.name for r in qs],
            'pending_count': pending_qs.count(),
            'pending_names': [r.employee.name for r in pending_qs],
        }
        curr += delta
    return days


@login_required
def time_off_list_view(request):
    user = request.user
    if user.is_ceo:
        requests = TimeOffRequest.objects.select_related('employee__department', 'reviewed_by').all()
    elif user.is_manager:
        user_emp = getattr(user, 'employee_profile', None)
        if user_emp:
            requests = TimeOffRequest.objects.filter(
                employee__department=user_emp.department
            ).select_related('employee__department', 'reviewed_by')
        else:
            requests = TimeOffRequest.objects.select_related('employee__department', 'reviewed_by').all()
    else: # Employee
        user_emp = getattr(user, 'employee_profile', None)
        if user_emp:
            requests = TimeOffRequest.objects.filter(employee=user_emp).select_related('reviewed_by')
        else:
            requests = TimeOffRequest.objects.none()

    return render(request, 'core/time_off_list.html', {'requests': requests})


@login_required
def time_off_create_view(request):
    user_emp = getattr(request.user, 'employee_profile', None)
    if not user_emp and not request.user.is_superuser:
        messages.error(request, "Your account does not have an associated Employee profile.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = TimeOffRequestForm(request.POST)
        if form.is_valid():
            tor = form.save(commit=False)
            tor.employee = user_emp
            tor.status = TimeOffRequest.Status.PENDING
            try:
                tor.clean()
                tor.save()
                messages.success(request, "Time-off request submitted (status: Pending review).")
                return redirect('time_off_list')
            except ValidationError as e:
                form.add_error(None, e.messages[0] if hasattr(e, 'messages') else str(e))
    else:
        form = TimeOffRequestForm(initial={'start_date': timezone.now().date(), 'end_date': timezone.now().date() + datetime.timedelta(days=1)})

    return render(request, 'core/time_off_form.html', {'form': form, 'title': 'Request Time Off'})


@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def time_off_review_view(request, pk):
    tor = get_object_or_404(TimeOffRequest.objects.select_related('employee__department'), pk=pk)

    if not can_manage_time_off(request.user, tor):
        raise PermissionDenied("You cannot approve your own time-off request.")

    # Calculate per-day "people off" pile-up for this range
    pileup_data = get_people_off_pileup(tor.start_date, tor.end_date, department=tor.employee.department)

    if request.method == 'POST':
        action = request.POST.get('action')
        notes = request.POST.get('decision_notes', '').strip()

        if action == 'APPROVE':
            removed_shifts = tor.approve(request.user, notes=notes)
            msg = f"Time-off request approved for {tor.employee.name}. Logged decision by {request.user.username}."
            if removed_shifts > 0:
                msg += f" {removed_shifts} overlapping shift assignment(s) were automatically unassigned."
            messages.success(request, msg)
            return redirect('time_off_list')
        elif action == 'DENY':
            tor.deny(request.user, notes=notes)
            messages.warning(request, f"Time-off request for {tor.employee.name} was denied. Decision logged.")
            return redirect('time_off_list')

    return render(request, 'core/time_off_review.html', {
        'request_obj': tor,
        'pileup_data': pileup_data,
    })


# ==========================================
# Phase 5: Priority Scheduling (Solver)
# ==========================================

@login_required
@role_required(User.Role.CEO, User.Role.MANAGER)
def schedule_run_solver_view(request, pk):
    schedule = get_object_or_404(Schedule, pk=pk)
    check_schedule_access(request, schedule, edit=True)

    if request.method == 'POST':
        keep_manual = request.POST.get('keep_manual') == 'true'
        scheduler = PriorityScheduler(schedule=schedule)
        result = scheduler.solve(keep_manual=keep_manual)

        if result['success']:
            applied = scheduler.apply_solution(result['assignments'], user=request.user)
            messages.success(
                request,
                f"AI Auto-Scheduler generated {len(applied)} assignments in {result['solve_time_ms']}ms! "
                f"Objective Value: {result['stats'].get('objective_value')}. Ready for manager review before publishing."
            )
        else:
            diag_str = " ".join(result.get('diagnosis', []))
            messages.error(
                request,
                f"Scheduler could not find a feasible solution: {result['message']} {diag_str}"
            )

    return redirect('schedule_detail', pk=pk)
