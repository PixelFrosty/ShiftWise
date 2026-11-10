"""Business rules for notifications, transfers, joining and leaving a company."""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import access
from .models import (Department, EmployeeProfile, JoinCode, Notification, Schedule, TransferRequest, User)

ROSTER_DOMAIN = '@roster.invalid'


def display_name(user):
    return user.get_full_name() or user.email


def is_roster_user(user):
    """Roster-only employees are added by a manager for scheduling and have no login."""
    return user.email.endswith(ROSTER_DOMAIN) and not user.has_usable_password()


# --- notifications ---------------------------------------------------------------------------

def notify(user, kind, message, transfer_request=None):
    if is_roster_user(user):
        return None
    return Notification.objects.create(recipient=user, kind=kind, message=message[:500],
                                       transfer_request=transfer_request)


def notify_availability_change(employee):
    """Tell the employee's department managers and the General Manager that they changed their availability.
    Repeated edits in a row (ticking several days, adding several slots) keep one unread alert instead of piling up."""
    message = f'{display_name(employee.user)} changed their availability.'
    recipients = {}
    for department in [employee.department, *employee.extra_departments.all()]:   # whoever schedules them
        recipients.update({m.user_id: m.user for m in department_manager_profiles(department).select_related('user')})
    recipients.update({u.pk: u for u in ceo_users(employee.company_id)})
    recipients.pop(employee.user_id, None)
    for user in recipients.values():
        unread = Notification.objects.filter(recipient=user, kind=Notification.Kind.INFO, message=message, is_read=False)
        if unread.exists():
            unread.update(created_at=timezone.now())   # same alert, bumped to the top
        else:
            notify(user, Notification.Kind.INFO, message)


def ceo_users(company_id):
    return User.objects.filter(employee_profiles__company_id=company_id,
                               employee_profiles__role=EmployeeProfile.Role.CEO).distinct()


def department_manager_profiles(department):
    return EmployeeProfile.objects.filter(
        company_id=department.company_id, role=EmployeeProfile.Role.MANAGER,
    ).filter(Q(managed_departments=department) | Q(department=department)).distinct()


def notify_if_unmanaged(department, who_left):
    """Tell the General Manager when a department is left without any manager."""
    if department_manager_profiles(department).exists():
        return
    for ceo in ceo_users(department.company_id):
        notify(ceo, Notification.Kind.NO_MANAGER,
               f'The "{department.name}" department has no manager now ({who_left} left or was removed).')


# --- joining ---------------------------------------------------------------------------------

def normalise_code(raw):
    cleaned = ''.join(ch for ch in str(raw or '').upper() if ch.isalnum())
    return f'{cleaned[:4]}-{cleaned[4:]}' if len(cleaned) > 4 else cleaned


def find_join_code(raw, role=None, lock=False):
    """Returns (code, error message). `role` (optional) must match the code's role."""
    code_text = normalise_code(raw)
    if not code_text:
        return None, 'Enter a join code.'
    queryset = JoinCode.objects.select_related('company')
    if lock:
        queryset = queryset.select_for_update()
    code = queryset.filter(code=code_text).first()
    if code is None:
        return None, 'That code does not exist. Check it and try again.'
    if code.is_used:
        return None, 'That code has already been used.'
    if role and code.role != role:
        article = lambda r: 'an' if r == 'employee' else 'a'
        return None, f'That code is for {article(code.role)} {code.role} account, not {article(role)} {role} account.'
    return code, None


def create_profile_from_code(user, code):
    """Consume a (locked, unused) code and give `user` the matching employee profile."""
    departments = list(code.departments.order_by('id'))
    if not departments:
        raise ValidationError({'join_code': ['That code is no longer valid.']})
    profile = EmployeeProfile.objects.create(
        user=user, company=code.company, department=departments[0], role=code.role)
    if code.role == JoinCode.Role.MANAGER:
        profile.managed_departments.set(departments)
    code.used_by = user
    code.used_at = timezone.now()
    code.save(update_fields=['used_by', 'used_at'])
    return profile


# --- removing / leaving ----------------------------------------------------------------------

@transaction.atomic
def remove_profile(profile):
    """Take someone out of their company. Their account stays (roster-only people are deleted)."""
    user = profile.user
    name = display_name(user)
    affected = []
    if profile.role == EmployeeProfile.Role.MANAGER:
        affected = list(Department.objects.filter(
            Q(managers=profile) | Q(pk=profile.department_id)).distinct())
    profile.delete()
    if is_roster_user(user):
        user.delete()
    for department in affected:
        notify_if_unmanaged(department, name)


def leave_company(profile):
    if profile.role == EmployeeProfile.Role.CEO:
        raise ValidationError({'detail': 'The General Manager cannot leave the company in this version.'})
    remove_profile(profile)


# --- transfers -------------------------------------------------------------------------------

@transaction.atomic
def drop_old_department_shifts(employee):
    """After a move, take the person off upcoming shifts of departments they no longer belong to."""
    Schedule.objects.filter(employee=employee, shift__isnull=False, shift_date__gte=timezone.localdate()
                            ).exclude(shift__department_id__in=access.member_department_ids(employee)).delete()


def start_transfer(actor, employee, to_department):
    """
    Move an employee, or ask the receiving department's managers to approve the move.
    Returns ('done', None) or ('pending', TransferRequest).
    """
    if employee.role != EmployeeProfile.Role.EMPLOYEE:
        raise ValidationError({'detail': 'Only employees can be transferred.'})
    if to_department.company_id != employee.company_id:
        raise ValidationError({'department': ['That department belongs to another company.']})
    if to_department.pk == employee.department_id:
        raise ValidationError({'department': ['The employee is already in that department.']})
    if TransferRequest.objects.filter(employee=employee, status=TransferRequest.Status.PENDING).exists():
        raise ValidationError({'detail': 'There is already a pending transfer request for this employee.'})

    employee_name = display_name(employee.user)
    # The General Manager, or a manager who runs both departments, can move people straight away.
    if access.is_ceo(actor) or access.can_manage_department(actor, to_department.pk):
        old_department = employee.department
        employee.department = to_department
        employee.save()
        employee.extra_departments.remove(to_department)   # it is their home now
        drop_old_department_shifts(employee)
        notify(employee.user, Notification.Kind.INFO,
               f'You were moved from {old_department.name} to {to_department.name}.')
        return 'done', None

    request = TransferRequest.objects.create(
        employee=employee, from_department=employee.department, to_department=to_department,
        requested_by=actor.user)
    recipients = [p.user for p in department_manager_profiles(to_department)] or list(
        ceo_users(employee.company_id))
    for user in recipients:
        notify(user, Notification.Kind.TRANSFER_REQUEST,
               f'{display_name(actor.user)} asks to transfer {employee_name} from '
               f'{employee.department.name} to {to_department.name}.', transfer_request=request)
    return 'pending', request


@transaction.atomic
def resolve_transfer(actor, request, accept):
    if request.status != TransferRequest.Status.PENDING:
        raise ValidationError({'detail': 'This request has already been answered.'})
    if not (access.is_ceo(actor) and actor.company_id == request.to_department.company_id) \
            and not access.can_manage_department(actor, request.to_department_id):
        raise PermissionDenied('Only a manager of the receiving department or the General Manager can answer this.')

    employee = request.employee
    if accept and employee.department_id != request.from_department_id:
        raise ValidationError({'detail': "The employee's department has changed since this was requested."})

    request.status = TransferRequest.Status.ACCEPTED if accept else TransferRequest.Status.REJECTED
    request.resolved_by = actor.user
    request.resolved_at = timezone.now()
    request.save()
    if accept:
        employee.department = request.to_department
        employee.save()
        employee.extra_departments.remove(request.to_department)
        drop_old_department_shifts(employee)

    verb = 'accepted' if accept else 'declined'
    if request.requested_by_id:
        notify(request.requested_by, Notification.Kind.TRANSFER_RESULT,
               f'{display_name(actor.user)} {verb} the transfer of {display_name(employee.user)} '
               f'to {request.to_department.name}.', transfer_request=request)
    if accept:
        notify(employee.user, Notification.Kind.INFO,
               f'You were moved from {request.from_department.name} to {request.to_department.name}.')
    request.notifications.filter(kind=Notification.Kind.TRANSFER_REQUEST).update(is_read=True)
    return request
