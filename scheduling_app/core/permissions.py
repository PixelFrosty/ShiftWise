from django.core.exceptions import PermissionDenied
from functools import wraps
from .models import User, Schedule, TimeOffRequest, Employee


def role_required(*allowed_roles):
    """
    Decorator for views checking if the authenticated user has one of the allowed roles.
    CEO/Superusers always bypass role checks.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.shortcuts import redirect
                return redirect('login')
            if request.user.is_superuser or request.user.role == User.Role.CEO:
                return view_func(request, *args, **kwargs)
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("You do not have the required role to access this resource.")
        return _wrapped_view
    return decorator


def can_view_schedule(user: User, schedule: Schedule) -> bool:
    """Backend object-level permission check for viewing a schedule."""
    if not user.is_authenticated:
        return False
    if user.is_ceo or user.is_superuser:
        return True
    if user.is_manager:
        # Manager can view if created by them or if in their department
        if schedule.created_by_id == user.id:
            return True
        if hasattr(user, 'employee_profile') and user.employee_profile:
            return schedule.department_id == user.employee_profile.department_id
        return True # General manager viewing
    if user.is_employee:
        # Employee can only view published schedules where they have an assignment
        if schedule.status != Schedule.Status.PUBLISHED:
            return False
        return schedule.shifts.filter(assignments__employee__user=user).exists()
    return False


def can_edit_schedule(user: User, schedule: Schedule) -> bool:
    """Backend object-level permission check for modifying a schedule or its shifts."""
    if not user.is_authenticated:
        return False
    if user.is_ceo or user.is_superuser:
        return True
    if user.is_manager:
        if schedule.created_by_id == user.id:
            return True
        if hasattr(user, 'employee_profile') and user.employee_profile:
            return schedule.department_id == user.employee_profile.department_id
        return True
    return False


def can_manage_time_off(user: User, time_off: TimeOffRequest) -> bool:
    """Backend check: can user approve/deny this time-off request?"""
    if not user.is_authenticated:
        return False
    if user.is_ceo or user.is_superuser:
        return True
    if user.is_manager:
        # A manager cannot approve their own request unless CEO
        if hasattr(user, 'employee_profile') and user.employee_profile and user.employee_profile.id == time_off.employee_id:
            return False
        return True
    return False


def check_schedule_access(request, schedule, edit=False):
    """Enforces backend permission check, raising PermissionDenied if unauthorized."""
    allowed = can_edit_schedule(request.user, schedule) if edit else can_view_schedule(request.user, schedule)
    if not allowed:
        raise PermissionDenied("You do not have backend permission for this schedule.")
