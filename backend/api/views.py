# Create your views here.


from datetime import date, time, timedelta
import sys
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date, parse_time
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.db.models import Q
from .models import (
    AvailabilitySlot,
    Company,
    CompatibilityScore,
    Department,
    EmployeeProfile,
    Project,
    Schedule,
    Skill,
    Task,
    TimeOffRequest,
    User,
)
from .serializers import (
    AvailabilitySlotSerializer,
    AssignShiftsSerializer,
    CompatibilityScoreSerializer,
    DepartmentSerializer,
    EmployeeProfileSerializer,
    GenerateShiftsSerializer,
    ProjectSerializer,
    ScheduleSerializer,
    SkillSerializer,
    TaskSerializer,
    TimeOffRequestSerializer,
    UserSerializer,
)
from .services.shift_assigner import SmartShiftAssignerService
from .services.shift_generator import ShiftGeneratorService

@api_view(['GET'])
def test(request):
    data = {
        'message': 'Hello World! - This is a test API endpoint.',
    }
    return Response(data)


@api_view(['POST'])
@permission_classes([AllowAny]) # in place because settings.py restricts annonymous users from requesting too often
def sign_up(request):
    serializer = UserSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def signup_check(request):
    """
    Checks if an email or username has already been taken.
    Does not disclose which one is taken to protect user privacy.
    Requires both 'email' and 'username' query parameters.
    """
    email = request.query_params.get('email')
    username = request.query_params.get('username')

    if email is not None:
        email = email.strip() if isinstance(email, str) else str(email).strip()
        if not email:
            email = None

    if username is not None:
        username = username.strip() if isinstance(username, str) else str(username).strip()
        if not username:
            username = None

    if not email or not username:
        return Response(
            {'detail': "Both 'email' and 'username' must be provided."},
            status=status.HTTP_400_BAD_REQUEST
        )

    query = Q(email__iexact=email) | Q(username__iexact=username)
    is_taken = User.objects.filter(query).exists()

    if is_taken:
        return Response(
            {
                'taken': True,
                'message': 'Email or username has already been taken.',
            },
            status=status.HTTP_409_CONFLICT
        )

    return Response(
        {
            'taken': False,
            'message': 'Email and username are available.',
        },
        status=status.HTTP_200_OK
    )

"""
expects a JSON payload with the following attributes:
{ username, email, first_name, last_name, password, date_of_birth}
date of birth should be formatted as: YYYY-MM-DD
"""


class ScheduleViewSet(viewsets.ModelViewSet):
    """
    CRUD for schedule rows (one employee, one day, one time block).
    Optional list filters: ?employee=<id> ?department=<id> ?status=<value>
                           ?shift_date=YYYY-MM-DD ?date_from=YYYY-MM-DD ?date_to=YYYY-MM-DD
    """
    serializer_class = ScheduleSerializer

    @staticmethod
    def _int(params, name):
        try:
            return int(params[name])
        except ValueError:
            raise serializers.ValidationError({name: 'Must be a whole number.'})

    @staticmethod
    def _date(params, name):
        try:
            value = parse_date(params[name])
        except ValueError:  # well-formed but impossible, e.g. 2026-13-45
            value = None
        if value is None:
            raise serializers.ValidationError({name: 'Enter a valid date in YYYY-MM-DD format.'})
        return value

    def get_queryset(self):
        qs = Schedule.objects.select_related('employee__user', 'task__department')
        params = self.request.query_params
        if 'employee' in params:
            qs = qs.filter(employee_id=self._int(params, 'employee'))
        if 'department' in params:
            dept_val = params['department']
            if ',' in str(dept_val):
                dept_ids = [int(x.strip()) for x in str(dept_val).split(',') if x.strip().isdigit()]
                qs = qs.filter(Q(employee__department_id__in=dept_ids) | Q(task__department_id__in=dept_ids) | Q(department_id__in=dept_ids))
            else:
                dept_id = self._int(params, 'department')
                qs = qs.filter(Q(employee__department_id=dept_id) | Q(task__department_id=dept_id) | Q(department_id=dept_id))
        if 'status' in params:
            if params['status'] not in Schedule.Status.values:
                raise serializers.ValidationError({'status': f'Must be one of: {", ".join(Schedule.Status.values)}.'})
            qs = qs.filter(status=params['status'])
        if 'shift_date' in params:
            qs = qs.filter(shift_date=self._date(params, 'shift_date'))
        if 'date_from' in params:
            qs = qs.filter(shift_date__gte=self._date(params, 'date_from'))
        if 'date_to' in params:
            qs = qs.filter(shift_date__lte=self._date(params, 'date_to'))
        return qs

    def create(self, request, *args, **kwargs):
        employees = request.data.get('employees')
        if isinstance(employees, list):
            return self._create_entry_with_employees(request.data)
        return super().create(request, *args, **kwargs)

    def _create_entry_with_employees(self, data):
        task_id = data.get('task')
        task = Task.objects.filter(pk=task_id).first() if task_id else None
        task_name = (data.get('task_name') or (task.name if task else '')).strip()
        if not task_name:
            return Response({'task_name': ['task_name cannot be blank.']}, status=status.HTTP_400_BAD_REQUEST)

        shift_date_val = data.get('shift_date')
        if not shift_date_val:
            return Response({'shift_date': ['shift_date is required.']}, status=status.HTTP_400_BAD_REQUEST)
        shift_date = parse_date(str(shift_date_val))
        if not shift_date:
            return Response({'shift_date': ['Enter a valid date in YYYY-MM-DD format.']}, status=status.HTTP_400_BAD_REQUEST)

        start_time_val = data.get('start_time')
        end_time_val = data.get('end_time')
        if not start_time_val or not end_time_val:
            return Response({'start_time': ['start_time and end_time are required.']}, status=status.HTTP_400_BAD_REQUEST)

        start_time = parse_time(str(start_time_val)) if isinstance(start_time_val, str) else start_time_val
        end_time = parse_time(str(end_time_val)) if isinstance(end_time_val, str) else end_time_val
        if not start_time or not end_time:
            return Response({'time': ['Invalid start_time or end_time format.']}, status=status.HTTP_400_BAD_REQUEST)
        if end_time <= start_time:
            return Response({'end_time': ['end_time must be after start_time (overnight shifts are not supported).']}, status=status.HTTP_400_BAD_REQUEST)

        headcount = task.required_people if task else int(data.get('headcount') or 1)
        employees = data.get('employees', [])
        if len(employees) > headcount:
            return Response(
                {'employees': [f'Cannot add more than {headcount} employees to this schedule (headcount required by task).']},
                status=status.HTTP_400_BAD_REQUEST
            )

        emp_profiles = []
        for emp_id in employees:
            profile = EmployeeProfile.objects.filter(pk=emp_id).first()
            if not profile:
                return Response({'employees': [f'Employee #{emp_id} does not exist.']}, status=status.HTTP_400_BAD_REQUEST)
            clash = Schedule.objects.filter(
                employee__user=profile.user, shift_date=shift_date, start_time__lt=end_time, end_time__gt=start_time
            ).exclude(status=Schedule.Status.CANCELLED).first()
            if clash:
                return Response(
                    {'non_field_errors': [
                        f'Overlaps existing schedule #{clash.pk} for this employee '
                        f'({clash.start_time:%H:%M}-{clash.end_time:%H:%M} on {clash.shift_date}).'
                    ]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            emp_profiles.append(profile)

        notes = data.get('notes', '')
        sched_status = data.get('status', Schedule.Status.SCHEDULED)
        dept_val = data.get('department')
        sched_dept = Department.objects.filter(pk=dept_val).first() if dept_val else None
        comp_val = data.get('company')
        sched_comp = Company.objects.filter(pk=comp_val).first() if comp_val else None

        created_schedules = []
        with transaction.atomic():
            for profile in emp_profiles:
                s = Schedule.objects.create(
                    company=sched_comp,
                    department=sched_dept,
                    task=task,
                    task_name=task_name,
                    employee=profile,
                    shift_date=shift_date,
                    start_time=start_time,
                    end_time=end_time,
                    status=sched_status,
                    notes=notes,
                )
                created_schedules.append(s)

            rem_slots = headcount - len(emp_profiles)
            for _ in range(rem_slots):
                s = Schedule.objects.create(
                    company=sched_comp,
                    department=sched_dept,
                    task=task,
                    task_name=task_name,
                    employee=None,
                    shift_date=shift_date,
                    start_time=start_time,
                    end_time=end_time,
                    status=sched_status,
                    notes=notes,
                )
                created_schedules.append(s)

        serializer = ScheduleSerializer(created_schedules, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='create-entry')
    def create_entry(self, request):
        return self._create_entry_with_employees(request.data)

    @action(detail=False, methods=['post'], url_path='assign-employees')
    def assign_employees(self, request):
        schedule_id = request.data.get('schedule_id')
        task_id = request.data.get('task')
        task = Task.objects.filter(pk=task_id).first() if task_id else None
        shift_date = parse_date(str(request.data.get('shift_date', '')))
        start_time = parse_time(str(request.data.get('start_time', '')))
        end_time = parse_time(str(request.data.get('end_time', '')))
        employees = request.data.get('employees', [])
        if not employees and 'employee' in request.data:
            employees = [request.data['employee']]
        notes = request.data.get('notes', '')

        if schedule_id and not (shift_date and start_time and end_time):
            target = Schedule.objects.filter(pk=schedule_id).first()
            if not target:
                return Response({'schedule_id': 'Schedule does not exist.'}, status=status.HTTP_404_NOT_FOUND)
            task = target.task
            shift_date = target.shift_date
            start_time = target.start_time
            end_time = target.end_time
            task_name = target.task_name
        else:
            task_name = (request.data.get('task_name') or (task.name if task else '')).strip()

        headcount = task.required_people if task else int(request.data.get('headcount') or 1)

        existing_qs = Schedule.objects.filter(
            shift_date=shift_date, start_time=start_time, end_time=end_time
        ).exclude(status=Schedule.Status.CANCELLED)
        if task:
            existing_qs = existing_qs.filter(task=task)
        else:
            existing_qs = existing_qs.filter(task_name=task_name)

        already_assigned = existing_qs.filter(employee__isnull=False).count()
        if already_assigned + len(employees) > headcount:
            return Response(
                {'employees': [f'Cannot add {len(employees)} employee(s): would exceed headcount limit of {headcount} (currently {already_assigned} assigned).']},
                status=status.HTTP_400_BAD_REQUEST
            )

        emp_profiles = []
        for emp_id in employees:
            profile = EmployeeProfile.objects.filter(pk=emp_id).first()
            if not profile:
                return Response({'employees': [f'Employee #{emp_id} does not exist.']}, status=status.HTTP_400_BAD_REQUEST)
            clash = Schedule.objects.filter(
                employee__user=profile.user, shift_date=shift_date, start_time__lt=end_time, end_time__gt=start_time
            ).exclude(status=Schedule.Status.CANCELLED).first()
            if clash:
                return Response(
                    {'non_field_errors': [
                        f'Overlaps existing schedule #{clash.pk} for this employee '
                        f'({clash.start_time:%H:%M}-{clash.end_time:%H:%M} on {clash.shift_date}).'
                    ]},
                    status=status.HTTP_400_BAD_REQUEST
                )
            emp_profiles.append(profile)

        updated_schedules = []
        with transaction.atomic():
            unassigned_slots = list(existing_qs.filter(employee__isnull=True))
            for profile in emp_profiles:
                if unassigned_slots:
                    slot = unassigned_slots.pop(0)
                    slot.employee = profile
                    if notes:
                        slot.notes = notes
                    slot.save()
                    updated_schedules.append(slot)
                else:
                    s = Schedule.objects.create(
                        task=task,
                        task_name=task_name,
                        employee=profile,
                        shift_date=shift_date,
                        start_time=start_time,
                        end_time=end_time,
                        status=Schedule.Status.SCHEDULED,
                        notes=notes,
                    )
                    updated_schedules.append(s)

        return Response(ScheduleSerializer(updated_schedules, many=True).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='delete-entry')
    def delete_entry(self, request):
        schedule_ids = request.data.get('schedule_ids', [])
        if schedule_ids:
            Schedule.objects.filter(pk__in=schedule_ids).delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        task_id = request.data.get('task')
        shift_date = parse_date(str(request.data.get('shift_date', '')))
        start_time = parse_time(str(request.data.get('start_time', '')))
        end_time = parse_time(str(request.data.get('end_time', '')))
        if shift_date and start_time and end_time:
            qs = Schedule.objects.filter(shift_date=shift_date, start_time=start_time, end_time=end_time)
            if task_id:
                qs = qs.filter(task_id=task_id)
            else:
                qs = qs.filter(task_name=request.data.get('task_name', ''))
            qs.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'detail': 'schedule_ids or (task, shift_date, start_time, end_time) required.'}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='unassign')
    def unassign(self, request):
        schedule_id = request.data.get('schedule_id') or request.data.get('assignment')
        if not schedule_id:
            return Response({'detail': 'schedule_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        schedule = get_object_or_404(Schedule, pk=schedule_id)
        schedule.employee = None
        schedule.save()
        return Response(ScheduleSerializer(schedule).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='set-note')
    def set_note(self, request):
        schedule_id = request.data.get('schedule_id') or request.data.get('assignment')
        note = request.data.get('note', '')
        if not schedule_id:
            return Response({'detail': 'schedule_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        schedule = get_object_or_404(Schedule, pk=schedule_id)
        schedule.notes = note
        schedule.save()
        return Response(ScheduleSerializer(schedule).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='generate')
    def generate(self, request):
        """
        POST /api/schedules/generate/
        Body: { "company_id": 1, "week_start": "YYYY-MM-DD", "department_id": null, "clear_existing": false }
        Generates weekly shift slots based on company open hours, projects, and task configurations.
        """
        serializer = GenerateShiftsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        company = Company.objects.get(pk=data['company_id'])
        department = None
        if data.get('department_id'):
            department = Department.objects.get(pk=data['department_id'])

        service = ShiftGeneratorService(
            company=company,
            week_start=data['week_start'],
            department=department,
            clear_existing=data.get('clear_existing', False),
        )
        try:
            result = service.generate()
            return Response(result, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='assign')
    def assign(self, request):
        """
        POST /api/schedules/assign/
        Body: { "company_id": 1, "week_start": "YYYY-MM-DD", "department_id": null, "forced_groups": [[1, 2]] }
        Assigns employees to unassigned schedule slots using OR-Tools CP-SAT.
        """
        serializer = AssignShiftsSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        company = Company.objects.get(pk=data['company_id'])
        department = None
        if data.get('department_id'):
            department = Department.objects.get(pk=data['department_id'])

        service = SmartShiftAssignerService(
            company=company,
            week_start=data['week_start'],
            department=department,
            forced_groups=data.get('forced_groups', []),
        )
        try:
            result = service.assign()
            return Response(result, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='clear-assignments')
    def clear_assignments(self, request):
        """
        POST /api/schedules/clear-assignments/
        Body: { "company_id": 1, "week_start": "YYYY-MM-DD", "department_id": null }
        Unassigns all employees from scheduled shifts in the specified week (leaving shifts as empty slots).
        """
        company_id = request.data.get('company_id')
        dept_id = request.data.get('department_id') or request.data.get('department')
        dept_ids = request.data.get('department_ids')
        week_start_str = request.data.get('week_start') or request.data.get('date_from')

        if not company_id and dept_id:
            dept = Department.objects.filter(pk=dept_id).first()
            if dept:
                company_id = dept.company_id
        if not company_id and request.user.is_authenticated:
            prof = getattr(request.user, 'employee_profiles', None)
            if prof and prof.exists():
                company_id = prof.first().company_id
        if not company_id:
            first_c = Company.objects.first()
            if first_c:
                company_id = first_c.id

        if not week_start_str:
            return Response({'error': 'week_start is required.'}, status=status.HTTP_400_BAD_REQUEST)

        week_start = parse_date(str(week_start_str))
        if not week_start:
            return Response({'error': 'Invalid week_start format.'}, status=status.HTTP_400_BAD_REQUEST)

        monday = week_start - timedelta(days=week_start.weekday())
        sunday = monday + timedelta(days=6)

        qs = Schedule.objects.filter(
            shift_date__gte=monday,
            shift_date__lte=sunday,
            status=Schedule.Status.SCHEDULED,
        )
        if dept_ids and isinstance(dept_ids, list):
            qs = qs.filter(Q(task__department_id__in=dept_ids) | Q(department_id__in=dept_ids) | Q(employee__department_id__in=dept_ids))
        elif dept_id:
            qs = qs.filter(Q(task__department_id=dept_id) | Q(department_id=dept_id) | Q(employee__department_id=dept_id))
        elif company_id:
            qs = qs.filter(Q(task__company_id=company_id) | Q(company_id=company_id) | Q(department__company_id=company_id) | Q(employee__company_id=company_id))

        count_updated = qs.filter(employee__isnull=False).update(employee=None)

        return Response({
            'company_id': company_id,
            'week_start': monday.isoformat(),
            'week_end': sunday.isoformat(),
            'department_id': dept_id,
            'cleared_count': count_updated,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='clear-shifts')
    def clear_shifts(self, request):
        """
        POST /api/schedules/clear-shifts/
        Body: { "company_id": 1, "week_start": "YYYY-MM-DD", "department_id": null }
        Deletes all scheduled shift entries for the specified week (leaving 0 shifts).
        """
        company_id = request.data.get('company_id')
        dept_id = request.data.get('department_id') or request.data.get('department')
        dept_ids = request.data.get('department_ids')
        week_start_str = request.data.get('week_start') or request.data.get('date_from')

        if not company_id and dept_id:
            dept = Department.objects.filter(pk=dept_id).first()
            if dept:
                company_id = dept.company_id
        if not company_id and request.user.is_authenticated:
            prof = getattr(request.user, 'employee_profiles', None)
            if prof and prof.exists():
                company_id = prof.first().company_id
        if not company_id:
            first_c = Company.objects.first()
            if first_c:
                company_id = first_c.id

        if not week_start_str:
            return Response({'error': 'week_start is required.'}, status=status.HTTP_400_BAD_REQUEST)

        week_start = parse_date(str(week_start_str))
        if not week_start:
            return Response({'error': 'Invalid week_start format.'}, status=status.HTTP_400_BAD_REQUEST)

        monday = week_start - timedelta(days=week_start.weekday())
        sunday = monday + timedelta(days=6)

        qs = Schedule.objects.filter(
            shift_date__gte=monday,
            shift_date__lte=sunday,
        )
        if dept_ids and isinstance(dept_ids, list):
            qs = qs.filter(Q(task__department_id__in=dept_ids) | Q(department_id__in=dept_ids) | Q(employee__department_id__in=dept_ids))
        elif dept_id:
            qs = qs.filter(Q(task__department_id=dept_id) | Q(department_id=dept_id) | Q(employee__department_id=dept_id))
        elif company_id:
            qs = qs.filter(Q(task__company_id=company_id) | Q(company_id=company_id) | Q(department__company_id=company_id) | Q(employee__company_id=company_id))

        count_deleted, _ = qs.delete()

        return Response({
            'company_id': company_id,
            'week_start': monday.isoformat(),
            'week_end': sunday.isoformat(),
            'department_id': dept_id,
            'deleted_count': count_deleted,
        }, status=status.HTTP_200_OK)


class CompatibilityScoreViewSet(viewsets.ModelViewSet):
    """
    CRUD for pairwise compatibility ratings.
    Optional list filter: ?employee=<id> returns every rating that involves that employee (either side).
    """
    serializer_class = CompatibilityScoreSerializer

    def get_queryset(self):
        qs = CompatibilityScore.objects.select_related('employee_a__user', 'employee_b__user')
        if 'employee' in self.request.query_params:
            try:
                employee_id = int(self.request.query_params['employee'])
            except ValueError:
                raise serializers.ValidationError({'employee': 'Must be a whole number.'})
            qs = qs.filter(Q(employee_a_id=employee_id) | Q(employee_b_id=employee_id))
        return qs

    def perform_create(self, serializer):
        serializer.save(rated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(rated_by=self.request.user)


# --- query-string helpers shared by the viewsets below -------------------------------------------

def int_param(params, name):
    try:
        return int(params[name])
    except ValueError:
        raise serializers.ValidationError({name: 'Must be a whole number.'})


def date_param(params, name):
    try:
        value = parse_date(params[name])
    except ValueError:  # well-formed but impossible, e.g. 2026-13-45
        value = None
    if value is None:
        raise serializers.ValidationError({name: 'Enter a valid date in YYYY-MM-DD format.'})
    return value


def choice_param(params, name, choices):
    if params[name] not in choices:
        raise serializers.ValidationError({name: f'Must be one of: {", ".join(map(str, choices))}.'})
    return params[name]


def bool_param(params, name):
    value = params[name].lower()
    if value in ('true', '1'):
        return True
    if value in ('false', '0'):
        return False
    raise serializers.ValidationError({name: 'Must be true or false.'})


class AvailabilitySlotViewSet(viewsets.ModelViewSet):
    """
    CRUD for recurring weekly availability slots.
    Optional list filters: ?employee=<id> ?department=<id> ?day_of_week=0-6 (0 = Monday)
    """
    serializer_class = AvailabilitySlotSerializer

    def get_queryset(self):
        qs = AvailabilitySlot.objects.select_related('employee__user')
        params = self.request.query_params
        if 'employee' in params:
            qs = qs.filter(employee_id=int_param(params, 'employee'))
        if 'department' in params:
            qs = qs.filter(employee__department_id=int_param(params, 'department'))
        if 'day_of_week' in params:
            day = int_param(params, 'day_of_week')
            if day not in AvailabilitySlot.Day.values:
                raise serializers.ValidationError({'day_of_week': 'Must be 0 (Monday) to 6 (Sunday).'})
            qs = qs.filter(day_of_week=day)
        return qs


class TimeOffRequestViewSet(viewsets.ModelViewSet):
    """
    CRUD for time-off requests. New requests are always "pending"; approve or deny with a PATCH on status.
    Optional list filters: ?employee=<id> ?department=<id> ?status=pending|approved|denied
                           ?date_from=YYYY-MM-DD ?date_to=YYYY-MM-DD  (requests that overlap that window)
    """
    serializer_class = TimeOffRequestSerializer

    def get_queryset(self):
        qs = TimeOffRequest.objects.select_related('employee__user')
        params = self.request.query_params
        if 'employee' in params:
            qs = qs.filter(employee_id=int_param(params, 'employee'))
        if 'department' in params:
            qs = qs.filter(employee__department_id=int_param(params, 'department'))
        if 'status' in params:
            qs = qs.filter(status=choice_param(params, 'status', TimeOffRequest.Status.values))
        if 'date_from' in params:
            qs = qs.filter(end_date__gte=date_param(params, 'date_from'))
        if 'date_to' in params:
            qs = qs.filter(start_date__lte=date_param(params, 'date_to'))
        return qs


class ProjectViewSet(viewsets.ModelViewSet):
    """
    CRUD for projects.
    Optional list filters: ?company=<id> ?department=<id> ?priority=low|medium|high ?is_active=true|false
    """
    serializer_class = ProjectSerializer

    def get_queryset(self):
        qs = Project.objects.all()
        params = self.request.query_params
        if 'company' in params:
            qs = qs.filter(company_id=int_param(params, 'company'))
        if 'department' in params:
            qs = qs.filter(department_id=int_param(params, 'department'))
        if 'priority' in params:
            qs = qs.filter(priority=choice_param(params, 'priority', Project.Priority.values))
        if 'is_active' in params:
            qs = qs.filter(is_active=bool_param(params, 'is_active'))
        return qs


class TaskViewSet(viewsets.ModelViewSet):
    """
    CRUD for tasks.
    Optional list filters: ?company=<id> ?department=<id>
    """
    serializer_class = TaskSerializer

    def get_queryset(self):
        qs = Task.objects.select_related('company', 'department', 'project').prefetch_related('skills')
        params = self.request.query_params
        if 'company' in params:
            qs = qs.filter(company_id=int_param(params, 'company'))
        if 'department' in params:
            qs = qs.filter(department_id=int_param(params, 'department'))
        return qs


class SkillViewSet(viewsets.ModelViewSet):
    """
    CRUD for company skills.
    Optional list filter: ?company=<id>
    """
    serializer_class = SkillSerializer

    def get_queryset(self):
        qs = Skill.objects.select_related('company')
        if 'company' in self.request.query_params:
            qs = qs.filter(company_id=int_param(self.request.query_params, 'company'))
        elif self.request.user.is_authenticated:
            prof = getattr(self.request.user, 'employee_profiles', None)
            if prof and prof.exists():
                qs = qs.filter(company_id=prof.first().company_id)
        return qs

    def perform_create(self, serializer):
        if 'company' not in serializer.validated_data and self.request.user.is_authenticated:
            prof = getattr(self.request.user, 'employee_profiles', None)
            if prof and prof.exists():
                serializer.save(company=prof.first().company)
                return
        serializer.save()


class DepartmentViewSet(viewsets.ModelViewSet):
    """
    CRUD for departments.
    Optional list filter: ?company=<id>
    """
    serializer_class = DepartmentSerializer

    def get_queryset(self):
        qs = Department.objects.prefetch_related('employees__user')
        if 'company' in self.request.query_params:
            qs = qs.filter(company_id=int_param(self.request.query_params, 'company'))
        return qs


class EmployeeProfileViewSet(viewsets.ModelViewSet):
    """
    CRUD for employee profiles.
    Optional list filters: ?company=<id> ?department=<id>
    """
    serializer_class = EmployeeProfileSerializer

    def get_queryset(self):
        qs = EmployeeProfile.objects.select_related('user', 'company', 'department')
        params = self.request.query_params
        if 'company' in params:
            qs = qs.filter(company_id=int_param(params, 'company'))
        if 'department' in params:
            qs = qs.filter(department_id=int_param(params, 'department'))
        return qs


@api_view(['GET'])
@permission_classes([AllowAny])
def me(request):
    user = request.user
    profile = None
    if user and user.is_authenticated:
        profile = getattr(user, 'employee_profile', None) or user.employee_profiles.select_related('company', 'department').first()

    if not user or not user.is_authenticated:
        return Response({'detail': 'Authentication credentials were not provided.'}, status=status.HTTP_401_UNAUTHORIZED)

    company_data = None
    if profile and profile.company:
        company_data = {
            'id': profile.company.id,
            'name': profile.company.name,
            'open_time': '08:00:00',
            'close_time': '18:00:00',
        }

    department_data = None
    managed_departments = []
    if profile and profile.department:
        department_data = {'id': profile.department.id, 'name': profile.department.name}

    if profile and profile.company:
        all_depts = Department.objects.filter(company=profile.company)
        if profile.role in [EmployeeProfile.Role.CEO, EmployeeProfile.Role.MANAGER]:
            managed_departments = [{'id': d.id, 'name': d.name} for d in all_depts]

    can_edit = False
    if profile:
        can_edit = profile.role in [EmployeeProfile.Role.CEO, EmployeeProfile.Role.MANAGER]

    profile_data = {
        'id': profile.id,
        'role': profile.role,
        'company': company_data,
        'department': department_data,
        'extra_departments': [],
        'managed_departments': managed_departments,
        'can_edit_schedule': can_edit,
    } if profile else None

    return Response({
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'profile': profile_data,
        'unread_notifications': 0
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def shift_publication(request):
    week_start = request.query_params.get('week_start', '')
    return Response({
        'published': True,
        'week_start': week_start,
        'published_by': None,
        'published_at': None
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def shift_review(request):
    dept_id = request.query_params.get('department')
    week_start = request.query_params.get('week_start', '')
    dept = Department.objects.filter(pk=dept_id).first() if dept_id else Department.objects.first()
    return Response({
        'department': {'id': dept.id, 'name': dept.name} if dept else {'id': 1, 'name': 'Operations'},
        'week_label': f'Week of {week_start}' if week_start else 'Current Week',
        'shift_count': Schedule.objects.filter(shift_date__gte=week_start).values('task', 'shift_date', 'start_time').distinct().count() if week_start else Schedule.objects.count(),
        'slots': Schedule.objects.count(),
        'filled': Schedule.objects.filter(employee__isnull=False).count(),
        'open_slots': Schedule.objects.filter(employee__isnull=True).count(),
        'warnings': [],
        'open_shifts': [],
        'people': [],
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def shift_publish(request):
    week_start = request.data.get('week_start', '')
    user_name = request.user.get_full_name() or request.user.email if request.user and request.user.is_authenticated else 'Manager'
    return Response({
        'published': True,
        'week_start': week_start,
        'published_by': user_name,
        'published_at': date.today().isoformat()
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def shift_auto_schedule(request):
    """
    POST /api/shifts/auto-schedule/
    Legacy or direct route: assigns employees to unassigned schedule slots using OR-Tools CP-SAT.
    Accepts { department, date_from, date_to } or { company_id, week_start, department_id }.
    """
    data = dict(request.data)
    if 'date_from' in data and 'week_start' not in data:
        data['week_start'] = data['date_from']
    if 'department' in data and 'department_id' not in data:
        data['department_id'] = data['department']

    serializer = AssignShiftsSerializer(data=data, context={'request': request})
    if serializer.is_valid():
        valid_data = serializer.validated_data
        company = Company.objects.get(pk=valid_data['company_id'])
        department = None
        if valid_data.get('department_id'):
            department = Department.objects.get(pk=valid_data['department_id'])

        service = SmartShiftAssignerService(
            company=company,
            week_start=valid_data['week_start'],
            department=department,
            forced_groups=valid_data.get('forced_groups', []),
        )
        try:
            res = service.assign()
            return Response({
                'created': res['slots_filled'],
                'open_before': res['total_unassigned_slots'],
                'open_after': res['unfillable_slots'],
                'notes': [f"Assigned {res['slots_filled']} shifts using smart scheduler (Status: {res['solver_status']})."],
                **res,
            }, status=status.HTTP_200_OK)
        except DjangoValidationError as exc:
            msg = exc.message if hasattr(exc, 'message') else str(exc)
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

    return Response({
        'created': 0,
        'open_before': 0,
        'open_after': 0,
        'notes': ['Auto-schedule completed.'],
    })


