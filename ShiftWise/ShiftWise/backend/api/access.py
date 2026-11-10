"""
Who can see and change what.

Roles (EmployeeProfile.role):
  ceo      - (shown as "General Manager") covers every department of their company and has every permission.
  manager  - covers the departments in `managed_departments` (plus their own department).
  employee - read-only access to their own department's schedule and their own requests.
"""
from django.db.models import Q
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Department, EmployeeProfile

CEO = EmployeeProfile.Role.CEO
MANAGER = EmployeeProfile.Role.MANAGER
EMPLOYEE = EmployeeProfile.Role.EMPLOYEE


def get_profile(user):
    """The user's employee profile (their first one), or None if they have not joined a company."""
    if user is None or not user.is_authenticated:
        return None
    return user.employee_profiles.select_related('company', 'department').order_by('id').first()


def is_ceo(profile):
    return profile is not None and profile.role == CEO


def is_manager(profile):
    return profile is not None and profile.role == MANAGER


def is_staff_role(profile):
    """General Manager or manager."""
    return is_ceo(profile) or is_manager(profile)


def managed_department_ids(profile):
    """Departments this person may edit: all of the company for a General Manager, their assigned ones for a manager."""
    if profile is None:
        return set()
    if is_ceo(profile):
        return set(Department.objects.filter(company_id=profile.company_id).values_list('id', flat=True))
    if is_manager(profile):
        ids = set(profile.managed_departments.values_list('id', flat=True))
        ids.add(profile.department_id)
        return ids
    return set()


def member_department_ids(profile):
    """The home department plus any extra departments the person also works in."""
    if profile is None:
        return set()
    return {profile.department_id, *profile.extra_departments.values_list('id', flat=True)}


def visible_department_ids(profile):
    ids = managed_department_ids(profile)
    if profile is not None:
        ids |= member_department_ids(profile)
    return ids


def members_of(department_id):
    """Everyone who works in a department: its own people and those who also work there."""
    return EmployeeProfile.objects.filter(Q(department_id=department_id) | Q(extra_departments=department_id)).distinct()


def can_manage_department(profile, department_id):
    return department_id in managed_department_ids(profile)


def can_manage_employee(profile, target):
    """May `profile` edit/remove/transfer the employee `target`?"""
    if profile is None or target.company_id != profile.company_id:
        return False
    if is_ceo(profile):
        return True
    if is_manager(profile):
        return target.role == EMPLOYEE and target.department_id in managed_department_ids(profile)
    return False


def scope_by_employee(queryset, profile, field='employee'):
    """Limit rows to employees whose department the person can see (General Manager: company, manager: theirs)."""
    if profile is None:
        return queryset.none()
    queryset = queryset.filter(**{f'{field}__company_id': profile.company_id})
    if is_staff_role(profile):
        return queryset.filter(**{f'{field}__department_id__in': visible_department_ids(profile)})
    return queryset.filter(**{f'{field}__department_id': profile.department_id})


class HasProfile(BasePermission):
    message = 'Join a company first.'

    def has_permission(self, request, view):
        return get_profile(request.user) is not None


class StaffOnly(HasProfile):
    message = 'Only managers and the General Manager can do this.'

    def has_permission(self, request, view):
        return is_staff_role(get_profile(request.user))


class StaffWritesOnly(HasProfile):
    """Anyone in a company may read; only managers and the General Manager may change things."""
    message = 'Only managers and the General Manager can change this.'

    def has_permission(self, request, view):
        profile = get_profile(request.user)
        if profile is None:
            return False
        return request.method in SAFE_METHODS or is_staff_role(profile)


class CEOWritesOnly(HasProfile):
    message = 'Only the General Manager can change this.'

    def has_permission(self, request, view):
        profile = get_profile(request.user)
        if profile is None:
            return False
        return request.method in SAFE_METHODS or is_ceo(profile)
