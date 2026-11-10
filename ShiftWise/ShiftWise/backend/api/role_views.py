"""Sign-up with roles, the current-user endpoint, join codes, employees, departments, transfers, notifications."""
import datetime
import re
import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from . import access, scheduling, services
from .models import (Company, Department, EmployeeProfile, JoinCode, Notification, Schedule, TransferRequest, User)
from .serializers import UserSerializer
from .shift_views import hhmm, request_data as shift_request_data

ROLES = ('ceo', 'manager', 'employee')


def dept_data(department):
    return {'id': department.id, 'name': department.name}


# --- sign-up, join-code check, current user --------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])  # anonymous requests are throttled by settings.py
def sign_up(request):
    """
    Body: { username, email, first_name, last_name, password, date_of_birth (YYYY-MM-DD), role,
            company_name (+ optional department_name)  when role = "ceo",
            join_code                                   when role = "manager" or "employee" }
    """
    data = request.data
    role = str(data.get('role') or '').strip().lower()
    if role not in ROLES:
        return Response({'role': ['Choose General Manager, manager or employee.']}, status=status.HTTP_400_BAD_REQUEST)

    user_serializer = UserSerializer(data=data)
    errors = {}
    if not user_serializer.is_valid():
        errors.update(user_serializer.errors)

    company_name = department_name = ''
    if role == 'ceo':
        company_name = str(data.get('company_name') or '').strip()
        department_name = str(data.get('department_name') or '').strip() or 'General'
        if not company_name:
            errors['company_name'] = ['Company name is required.']
        elif len(company_name) > 255:
            errors['company_name'] = ['Company name is too long.']
        if len(department_name) > 255:
            errors['department_name'] = ['Department name is too long.']
    else:
        _, message = services.find_join_code(data.get('join_code'), role)
        if message:
            errors['join_code'] = [message]

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        code = None
        if role != 'ceo':  # re-check under a row lock so a code cannot be used twice at once
            code, message = services.find_join_code(data.get('join_code'), role, lock=True)
            if message:
                return Response({'join_code': [message]}, status=status.HTTP_400_BAD_REQUEST)
        user = user_serializer.save()
        if role == 'ceo':
            company = Company.objects.create(name=company_name)
            department = Department.objects.create(company=company, name=department_name)
            EmployeeProfile.objects.create(user=user, company=company, department=department,
                                           role=EmployeeProfile.Role.CEO)
        else:
            services.create_profile_from_code(user, code)
    return Response({**user_serializer.data, 'role': role}, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([AllowAny])
def join_code_check(request):
    """?code=XXXX-XXXX[&role=manager|employee] - lets the sign-up page validate a code before continuing."""
    role = request.query_params.get('role') or None
    code, message = services.find_join_code(request.query_params.get('code'), role)
    if message:
        return Response({'valid': False, 'detail': message}, status=status.HTTP_404_NOT_FOUND)
    return Response({'valid': True, 'role': code.role, 'company': code.company.name,
                     'departments': [d.name for d in code.departments.order_by('id')]})


def profile_data(profile):
    if profile is None:
        return None
    if access.is_ceo(profile):
        departments = Department.objects.filter(company_id=profile.company_id).order_by('name')
    elif access.is_manager(profile):
        departments = Department.objects.filter(pk__in=access.managed_department_ids(profile)).order_by('name')
    else:
        departments = Department.objects.none()  # employees edit nothing; their own department is "department"
    return {
        'id': profile.id,
        'role': profile.role,
        'company': {'id': profile.company_id, 'name': profile.company.name,
                    'open_time': hhmm(profile.company.open_time), 'close_time': hhmm(profile.company.close_time)},
        'department': dept_data(profile.department),
        'extra_departments': [dept_data(d) for d in profile.extra_departments.order_by('name')],
        'managed_departments': [dept_data(d) for d in departments],
        'can_edit_schedule': access.is_staff_role(profile),
        'unavailable_days': list(profile.unavailable_days or []),
    }


def me_data(user):
    profile = access.get_profile(user)
    return {
        'id': user.id, 'email': user.email, 'username': user.username,
        'first_name': user.first_name, 'last_name': user.last_name,
        'profile': profile_data(profile),
        'unread_notifications': user.notifications.filter(is_read=False).count(),
    }


@api_view(['GET'])
def me(request):
    return Response(me_data(request.user))


@api_view(['POST'])
def me_leave(request):
    profile = access.get_profile(request.user)
    if profile is None:
        return Response({'detail': 'You are not in a company.'}, status=status.HTTP_400_BAD_REQUEST)
    services.leave_company(profile)
    return Response(me_data(request.user))


@api_view(['POST'])
def me_join(request):
    """Join a company with a code (for accounts that are not in one, e.g. after leaving)."""
    if access.get_profile(request.user) is not None:
        return Response({'detail': 'You already belong to a company. Leave it first.'},
                        status=status.HTTP_400_BAD_REQUEST)
    with transaction.atomic():
        code, message = services.find_join_code(request.data.get('join_code'), lock=True)
        if message:
            return Response({'join_code': [message]}, status=status.HTTP_400_BAD_REQUEST)
        services.create_profile_from_code(request.user, code)
    return Response(me_data(request.user), status=status.HTTP_201_CREATED)


# --- employees -------------------------------------------------------------------------------

def transfer_data(tr):
    return {
        'id': tr.id, 'status': tr.status,
        'employee': {'id': tr.employee_id, 'name': services.display_name(tr.employee.user)},
        'from_department': dept_data(tr.from_department), 'to_department': dept_data(tr.to_department),
        'requested_by': services.display_name(tr.requested_by) if tr.requested_by else None,
        'created_at': tr.created_at, 'resolved_at': tr.resolved_at,
    }


PLACEHOLDER_DOB = datetime.date(1990, 1, 1)


def dob_shown(profile):
    """Roster-only people start with a placeholder birth date; treat that as 'not entered'."""
    dob = profile.user.date_of_birth
    if services.is_roster_user(profile.user) and dob == PLACEHOLDER_DOB:
        return None
    return dob


def employee_data(profile):
    user = profile.user
    pending = next((t for t in profile.transfer_requests.all() if t.status == TransferRequest.Status.PENDING), None)
    return {
        'id': profile.id, 'user_id': user.id,
        'first_name': user.first_name, 'last_name': user.last_name, 'name': services.display_name(user),
        'email': None if services.is_roster_user(user) else user.email,
        'position': profile.position, 'department': dept_data(profile.department), 'role': profile.role,
        'extra_departments': [dept_data(d) for d in sorted(profile.extra_departments.all(), key=lambda d: d.name)],
        'productivity_score': float(profile.productivity_score) if profile.productivity_score is not None else None,
        'pay_rate': float(profile.pay_rate) if profile.pay_rate is not None else None,
        'managed_department_ids': sorted(d.id for d in profile.managed_departments.all())
        if profile.role == EmployeeProfile.Role.MANAGER else [],
        'is_roster': services.is_roster_user(user),
        'employment_type': profile.employment_type, 'allow_overtime': profile.allow_overtime,
        'unavailable_days': list(profile.unavailable_days or []),
        'date_of_birth': dob_shown(profile).isoformat() if dob_shown(profile) else None,
        'age': scheduling.age_of(profile) if dob_shown(profile) else None,
        'is_minor': scheduling.is_minor(profile),
        'pending_transfer': ({'id': pending.id, 'to_department': dept_data(pending.to_department)}
                             if pending else None),
    }


class EmployeeWriteSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=20)
    last_name = serializers.CharField(max_length=20)
    position = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())
    productivity_score = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=Decimal('0'),
                                                  max_value=Decimal('10'), required=False, allow_null=True)
    pay_rate = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal('0'),
                                        required=False, allow_null=True)
    employment_type = serializers.ChoiceField(choices=EmployeeProfile.EmploymentType.choices, required=False,
                                              default=EmployeeProfile.EmploymentType.FULL_TIME)
    allow_overtime = serializers.BooleanField(required=False, default=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)

    def validate_date_of_birth(self, value):
        return check_birth_date(value)

    def validate(self, attrs):
        if attrs.get('allow_overtime') and attrs.get('employment_type') == EmployeeProfile.EmploymentType.PART_TIME:
            raise serializers.ValidationError({'allow_overtime': 'Only full-time employees can be allowed overtime.'})
        return attrs


def check_birth_date(value):
    if value is None:
        return value
    today = datetime.date.today()
    if value > today:
        raise serializers.ValidationError('The birth date cannot be in the future.')
    if scheduling.age_on(value, today) > 110:
        raise serializers.ValidationError('Enter a real birth date.')
    return value


class EmployeeViewSet(viewsets.ViewSet):
    """
    Managers see/manage employees in their departments; the General Manager sees everyone in the company.
    POST creates a roster-only employee (no login). Departments change only via transfer/.
    """
    permission_classes = [IsAuthenticated, access.StaffOnly]

    def _profile(self, request):
        return access.get_profile(request.user)

    def _queryset(self, request):
        profile = self._profile(request)
        queryset = (EmployeeProfile.objects.filter(company_id=profile.company_id)
                    .select_related('user', 'department')
                    .prefetch_related('managed_departments', 'extra_departments', 'transfer_requests__to_department')
                    .order_by('user__first_name', 'user__last_name', 'id'))
        if access.is_ceo(profile):
            return queryset
        managed = access.managed_department_ids(profile)
        # people who also work in a department a manager runs are listed too (to be scheduled), but only
        # their home department's manager can edit them
        return queryset.filter(Q(department_id__in=managed) | Q(extra_departments__in=managed)).distinct()

    def _target(self, request, pk):
        return get_object_or_404(self._queryset(request), pk=pk)

    def list(self, request):
        return Response([employee_data(p) for p in self._queryset(request)])

    def retrieve(self, request, pk=None):
        return Response(employee_data(self._target(request, pk)))

    def create(self, request):
        profile = self._profile(request)
        serializer = EmployeeWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        department = v['department']
        if department.company_id != profile.company_id or not access.can_manage_department(profile, department.pk):
            raise PermissionDenied('You do not manage that department.')
        base = re.sub(r'[^a-z0-9]', '', f"{v['first_name']}{v['last_name']}".lower())[:20] or 'employee'
        token = uuid.uuid4().hex[:8]
        with transaction.atomic():
            user = User(username=f'{base}{token[:4]}', email=f'roster.{token}{services.ROSTER_DOMAIN}',
                        first_name=v['first_name'].strip(), last_name=v['last_name'].strip(),
                        date_of_birth=v.get('date_of_birth') or PLACEHOLDER_DOB)
            user.set_unusable_password()
            user.save()
            created = EmployeeProfile.objects.create(
                user=user, company=profile.company, department=department, role=EmployeeProfile.Role.EMPLOYEE,
                position=v.get('position', '').strip(), productivity_score=v.get('productivity_score'),
                pay_rate=v.get('pay_rate'), employment_type=v['employment_type'],
                allow_overtime=v['allow_overtime'])
        return Response(employee_data(created), status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        actor = self._profile(request)
        target = self._target(request, pk)
        data = request.data
        if 'department' in data or 'role' in data:
            return Response({'detail': 'Use the transfer action to change a department.'},
                            status=status.HTTP_400_BAD_REQUEST)

        departments_given = 'managed_department_ids' in data
        if departments_given:
            if not access.is_ceo(actor):
                raise PermissionDenied('Only the General Manager can assign departments to managers.')
            if target.role != EmployeeProfile.Role.MANAGER:
                return Response({'detail': 'Only managers can be assigned departments.'},
                                status=status.HTTP_400_BAD_REQUEST)
        other_fields = [k for k in data if k != 'managed_department_ids']   # includes extra_department_ids
        if other_fields and not access.can_manage_employee(actor, target):
            raise PermissionDenied('You cannot edit this person.')

        errors = {}
        if 'first_name' in data or 'last_name' in data:
            if not services.is_roster_user(target.user):
                errors['name'] = ['Only roster-only employees can be renamed.']
        for name, limit in (('first_name', 20), ('last_name', 20)):
            if name in data and (not str(data[name]).strip() or len(str(data[name])) > limit):
                errors[name] = [f'Enter 1-{limit} characters.']
        if 'position' in data and len(str(data['position'])) > 255:
            errors['position'] = ['Too long.']
        scores = {}
        for name, digits, places, maxv in (('productivity_score', 5, 2, Decimal('10')),
                                           ('pay_rate', 8, 2, None)):
            if name in data:
                field = serializers.DecimalField(max_digits=digits, decimal_places=places, min_value=Decimal('0'),
                                                 max_value=maxv, allow_null=True)
                try:
                    scores[name] = field.run_validation(data[name])
                except serializers.ValidationError as exc:
                    errors[name] = exc.detail
        extra = {}
        if 'employment_type' in data:
            if data['employment_type'] not in EmployeeProfile.EmploymentType.values:
                errors['employment_type'] = ['Choose full time or part time.']
            else:
                extra['employment_type'] = data['employment_type']
        if 'allow_overtime' in data:
            if not isinstance(data['allow_overtime'], bool):
                errors['allow_overtime'] = ['Must be true or false.']
            else:
                extra['allow_overtime'] = data['allow_overtime']
        final_type = extra.get('employment_type', target.employment_type)
        if final_type == EmployeeProfile.EmploymentType.PART_TIME:
            if extra.get('allow_overtime'):
                errors['allow_overtime'] = ['Only full-time employees can be allowed overtime.']
            extra['allow_overtime'] = False  # moving to part time clears overtime
        new_dob = None
        if 'date_of_birth' in data:
            if not services.is_roster_user(target.user):
                errors['date_of_birth'] = ['This person entered their own birth date when they signed up.']
            else:
                try:
                    new_dob = check_birth_date(serializers.DateField().run_validation(data['date_of_birth']))
                except serializers.ValidationError as exc:
                    errors['date_of_birth'] = exc.detail
        extras = None
        if 'extra_department_ids' in data:
            if target.role != EmployeeProfile.Role.EMPLOYEE:
                errors['extra_department_ids'] = ['Only employees can work in extra departments.']
            else:
                try:
                    ids = {int(i) for i in data['extra_department_ids']}
                except (TypeError, ValueError):
                    ids = None
                found = list(Department.objects.filter(company_id=actor.company_id, pk__in=ids)) if ids is not None else []
                if ids is None or len(found) != len(ids) or target.department_id in ids:
                    errors['extra_department_ids'] = ['Choose departments of this company other than their home department.']
                else:
                    extras = found
                    dropped = set(target.extra_departments.values_list('id', flat=True)) - ids
                    busy = Schedule.objects.filter(employee=target, shift__department_id__in=dropped,
                                                   shift_date__gte=timezone.localdate()).select_related('shift__department')
                    names = sorted({s.shift.department.name for s in busy})
                    if names:
                        errors['extra_department_ids'] = [
                            f'{services.display_name(target.user)} still has upcoming shifts in {", ".join(names)}. '
                            'Take them off those shifts first.']
        new_departments = None
        if departments_given:
            try:
                ids = {int(i) for i in data['managed_department_ids']}
            except (TypeError, ValueError):
                ids = None
            valid = Department.objects.filter(company_id=actor.company_id, pk__in=ids or []) if ids else []
            if ids is None or not ids or len(valid) != len(ids):
                errors['managed_department_ids'] = ['Choose at least one department from this company.']
            else:
                new_departments = list(valid)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user = target.user
            if 'first_name' in data:
                user.first_name = str(data['first_name']).strip()
            if 'last_name' in data:
                user.last_name = str(data['last_name']).strip()
            if new_dob is not None:
                user.date_of_birth = new_dob
            if 'first_name' in data or 'last_name' in data or new_dob is not None:
                user.save()
            for name, value in extra.items():
                setattr(target, name, value)
            if 'position' in data:
                target.position = str(data['position']).strip()
            for name, value in scores.items():
                setattr(target, name, value)
            target.save()
            if extras is not None:
                added = [d for d in extras if d.pk not in set(target.extra_departments.values_list('id', flat=True))]
                target.extra_departments.set(extras)
                for department in added:
                    services.notify(user, Notification.Kind.INFO,
                                    f'You can now also work in the {department.name} department. '
                                    'A manager there can schedule you.')
            if new_departments is not None:
                before = set(target.managed_departments.values_list('id', flat=True))
                target.managed_departments.set(new_departments)
                for department in Department.objects.filter(pk__in=before - {d.pk for d in new_departments}):
                    services.notify_if_unmanaged(department, services.display_name(user))
        return Response(employee_data(self._target(request, pk)))

    def destroy(self, request, pk=None):
        actor = self._profile(request)
        target = self._target(request, pk)
        if target.pk == actor.pk:
            return Response({'detail': 'Use "Leave company" to remove yourself.'}, status=status.HTTP_400_BAD_REQUEST)
        if target.role == EmployeeProfile.Role.CEO:
            raise PermissionDenied('The General Manager cannot be removed.')
        if not access.can_manage_employee(actor, target):
            raise PermissionDenied('You cannot remove this person.')
        services.remove_profile(target)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        actor = self._profile(request)
        target = self._target(request, pk)
        if not access.can_manage_employee(actor, target):
            raise PermissionDenied('You cannot transfer this person.')
        try:
            department = Department.objects.get(pk=int(request.data.get('department')),
                                                company_id=actor.company_id)
        except (TypeError, ValueError, Department.DoesNotExist):
            return Response({'department': ['Choose a department from this company.']},
                            status=status.HTTP_400_BAD_REQUEST)
        outcome, transfer_request = services.start_transfer(actor, target, department)
        fresh = (EmployeeProfile.objects.select_related('user', 'department')
                 .prefetch_related('managed_departments', 'transfer_requests__to_department').get(pk=target.pk))
        body = {'outcome': outcome, 'employee': employee_data(fresh)}
        if transfer_request:
            body['request'] = transfer_data(transfer_request)
        return Response(body, status=status.HTTP_202_ACCEPTED if outcome == 'pending' else status.HTTP_200_OK)


# --- departments -----------------------------------------------------------------------------

class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.IntegerField(read_only=True)
    managers = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ['id', 'name', 'employee_count', 'managers']

    def get_managers(self, obj):
        return [services.display_name(p.user) for p in
                services.department_manager_profiles(obj).select_related('user')]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Enter a department name.')
        company_id = self.context['company_id']
        clash = Department.objects.filter(company_id=company_id, name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError('This company already has a department with that name.')
        return value


class DepartmentViewSet(viewsets.ModelViewSet):
    """Everyone in a company can list its departments; only the General Manager creates, renames or deletes them."""
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, access.CEOWritesOnly]

    def get_queryset(self):
        profile = access.get_profile(self.request.user)
        return (Department.objects.filter(company_id=profile.company_id)
                .annotate(employee_count=Count('employees', distinct=True)).order_by('name', 'id'))

    def get_serializer_context(self):
        context = super().get_serializer_context()
        profile = access.get_profile(self.request.user)
        context['company_id'] = profile.company_id if profile else None
        return context

    def perform_create(self, serializer):
        serializer.save(company_id=access.get_profile(self.request.user).company_id)

    def destroy(self, request, *args, **kwargs):
        department = self.get_object()
        if EmployeeProfile.objects.filter(department=department).exists() or department.extra_members.exists():
            return Response({'detail': 'Move or remove the people in this department first.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)


# --- join codes ------------------------------------------------------------------------------

def code_data(code):
    return {
        'id': code.id, 'code': code.code, 'role': code.role,
        'departments': [dept_data(d) for d in code.departments.all()],
        'status': 'used' if code.is_used else 'unused',
        'created_by': services.display_name(code.created_by) if code.created_by else None,
        'used_by': services.display_name(code.used_by) if code.used_by else None,
        'created_at': code.created_at, 'used_at': code.used_at,
    }


class JoinCodeViewSet(viewsets.ViewSet):
    """
    The General Manager makes manager or employee codes; managers make employee codes for departments they run.
    Each code works once. Unused codes can be revoked (deleted).
    """
    permission_classes = [IsAuthenticated, access.StaffOnly]

    def _queryset(self, request):
        profile = access.get_profile(request.user)
        queryset = JoinCode.objects.filter(company_id=profile.company_id).select_related(
            'created_by', 'used_by').prefetch_related('departments')
        if not access.is_ceo(profile):
            queryset = queryset.filter(created_by=request.user)
        return queryset

    def list(self, request):
        return Response([code_data(c) for c in self._queryset(request)])

    def create(self, request):
        profile = access.get_profile(request.user)
        role = str(request.data.get('role') or '')
        if role not in JoinCode.Role.values:
            return Response({'role': ['Choose manager or employee.']}, status=status.HTTP_400_BAD_REQUEST)
        if role == JoinCode.Role.MANAGER and not access.is_ceo(profile):
            raise PermissionDenied('Only the General Manager can create manager codes.')
        raw_ids = request.data.get('departments', request.data.get('department_ids', []))
        try:
            ids = {int(i) for i in raw_ids}
        except (TypeError, ValueError):
            ids = set()
        departments = list(Department.objects.filter(company_id=profile.company_id, pk__in=ids))
        if not ids or len(departments) != len(ids):
            return Response({'departments': ['Choose at least one department from this company.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if role == JoinCode.Role.EMPLOYEE and len(departments) != 1:
            return Response({'departments': ['An employee code is for exactly one department.']},
                            status=status.HTTP_400_BAD_REQUEST)
        if any(not access.can_manage_department(profile, d.pk) for d in departments):
            raise PermissionDenied('You do not manage that department.')
        code = JoinCode.objects.create(company=profile.company, role=role, created_by=request.user)
        code.departments.set(departments)
        return Response(code_data(self._queryset(request).get(pk=code.pk)), status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        code = get_object_or_404(self._queryset(request), pk=pk)
        if code.is_used:
            return Response({'detail': 'This code was already used.'}, status=status.HTTP_400_BAD_REQUEST)
        code.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- transfer requests and notifications -----------------------------------------------------

class TransferRequestViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, access.StaffOnly]

    def _queryset(self, request):
        profile = access.get_profile(request.user)
        queryset = TransferRequest.objects.filter(from_department__company_id=profile.company_id).select_related(
            'employee__user', 'from_department', 'to_department', 'requested_by')
        if access.is_ceo(profile):
            return queryset
        from django.db.models import Q
        return queryset.filter(Q(to_department_id__in=access.managed_department_ids(profile))
                               | Q(requested_by=request.user))

    def list(self, request):
        return Response([transfer_data(t) for t in self._queryset(request)[:100]])

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        tr = get_object_or_404(self._queryset(request), pk=pk)
        services.resolve_transfer(access.get_profile(request.user), tr, accept=True)
        return Response(transfer_data(tr))

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        tr = get_object_or_404(self._queryset(request), pk=pk)
        services.resolve_transfer(access.get_profile(request.user), tr, accept=False)
        return Response(transfer_data(tr))


class NotificationViewSet(viewsets.ViewSet):
    """Your in-app inbox."""

    def _queryset(self, request):
        return request.user.notifications.select_related(
            'transfer_request__employee__user', 'transfer_request__from_department',
            'transfer_request__to_department', 'transfer_request__requested_by',
            'shift_request__requester__user', 'shift_request__target__user', 'shift_request__schedule__shift__department',
            'shift_request__other_schedule__shift__department')

    def list(self, request):
        return Response([{
            'id': n.id, 'kind': n.kind, 'message': n.message, 'is_read': n.is_read, 'created_at': n.created_at,
            'transfer_request': transfer_data(n.transfer_request) if n.transfer_request else None,
            'shift_request': shift_request_data(n.shift_request) if n.shift_request else None,
        } for n in self._queryset(request)[:100]])

    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        get_object_or_404(self._queryset(request), pk=pk)
        self._queryset(request).filter(pk=pk).update(is_read=True)
        return Response({'unread_notifications': request.user.notifications.filter(is_read=False).count()})

    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return Response({'unread_notifications': 0})
