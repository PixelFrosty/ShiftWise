# Create your views here.


from django.utils.dateparse import parse_date
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from . import access, projects, publishing, services
from .models import Milestone, MilestoneAssignment, AvailabilitySlot, CompatibilityScore, EmployeeProfile, Project, Schedule, TimeOffRequest, User
from .serializers import (AvailabilitySlotSerializer, CompatibilityScoreSerializer, ProjectSerializer,
                          ScheduleSerializer, TimeOffRequestSerializer)


def require_manage_scope(profile, employee):
    """403 unless `profile` may edit rows that belong to the employee profile `employee`."""
    if employee.company_id != profile.company_id or not access.can_manage_department(profile, employee.department_id):
        raise PermissionDenied('You do not manage that employee\'s department.')


@api_view(['GET'])
def test(request):
    data = {
        'message': 'Hello World! - This is a test API endpoint.',
    }
    return Response(data)


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
    permission_classes = [IsAuthenticated, access.StaffWritesOnly]

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
        profile = access.get_profile(self.request.user)
        qs = access.scope_by_employee(Schedule.objects.select_related('employee__user'), profile)
        if profile and not access.is_staff_role(profile):
            qs = publishing.published_schedules(qs)  # employees do not see weeks that are still drafts
        params = self.request.query_params
        if 'employee' in params:
            qs = qs.filter(employee_id=self._int(params, 'employee'))
        if 'department' in params:
            qs = qs.filter(employee__department_id=self._int(params, 'department'))
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

    def perform_create(self, serializer):
        require_manage_scope(access.get_profile(self.request.user), serializer.validated_data['employee'])
        serializer.save()

    def perform_update(self, serializer):
        profile = access.get_profile(self.request.user)
        require_manage_scope(profile, serializer.instance.employee)
        if 'employee' in serializer.validated_data:
            require_manage_scope(profile, serializer.validated_data['employee'])
        serializer.save()


class CompatibilityScoreViewSet(viewsets.ModelViewSet):
    """
    CRUD for pairwise compatibility ratings.
    Optional list filter: ?employee=<id> returns every rating that involves that employee (either side).
    """
    serializer_class = CompatibilityScoreSerializer
    permission_classes = [IsAuthenticated, access.StaffOnly]

    def get_queryset(self):
        profile = access.get_profile(self.request.user)
        qs = CompatibilityScore.objects.select_related('employee_a__user', 'employee_b__user').filter(
            employee_a__company_id=profile.company_id,
            employee_a__department_id__in=access.visible_department_ids(profile),
            employee_b__department_id__in=access.visible_department_ids(profile))
        if 'employee' in self.request.query_params:
            try:
                employee_id = int(self.request.query_params['employee'])
            except ValueError:
                raise serializers.ValidationError({'employee': 'Must be a whole number.'})
            qs = qs.filter(Q(employee_a_id=employee_id) | Q(employee_b_id=employee_id))
        return qs

    def perform_create(self, serializer):
        profile = access.get_profile(self.request.user)
        for key in ('employee_a', 'employee_b'):
            require_manage_scope(profile, serializer.validated_data[key])
        serializer.save(rated_by=self.request.user)

    def perform_update(self, serializer):
        require_manage_scope(access.get_profile(self.request.user), serializer.instance.employee_a)
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
    permission_classes = [IsAuthenticated, access.HasProfile]

    def get_queryset(self):
        profile = access.get_profile(self.request.user)
        qs = AvailabilitySlot.objects.select_related('employee__user')
        qs = access.scope_by_employee(qs, profile) if access.is_staff_role(profile) else qs.filter(employee=profile)
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

    def _check_employee(self, employee):
        profile = access.get_profile(self.request.user)
        if employee.pk == profile.pk:
            return  # everyone manages their own availability
        if not access.is_staff_role(profile):
            raise PermissionDenied('You can only change your own availability.')
        require_manage_scope(profile, employee)

    def perform_create(self, serializer):
        self._check_employee(serializer.validated_data['employee'])
        serializer.save()
        self._alert(serializer.validated_data['employee'])

    def _alert(self, employee):
        """Managers hear about it when the employee changes their own availability (not when a manager edits it)."""
        if employee.pk == access.get_profile(self.request.user).pk:
            services.notify_availability_change(employee)

    @action(detail=False, methods=['get', 'put'], url_path='days')
    def days(self, request):
        """The weekdays marked "not available". GET/PUT body {employee?: id, unavailable_days: [0-6, ...]}.

        Every day that is not ticked here and has no slots counts as available all day.
        """
        profile = access.get_profile(request.user)
        raw = request.data.get('employee') if request.method == 'PUT' else request.query_params.get('employee')
        target = profile
        if raw not in (None, ''):
            try:
                target = EmployeeProfile.objects.get(pk=int(raw))
            except (TypeError, ValueError, EmployeeProfile.DoesNotExist):
                raise serializers.ValidationError({'employee': 'Choose an employee.'})
            if target.pk != profile.pk:
                if target.company_id != profile.company_id:
                    raise serializers.ValidationError({'employee': 'Choose an employee.'})
                self._check_employee(target)
        if request.method == 'PUT':
            days = request.data.get('unavailable_days')
            if (not isinstance(days, list) or any(isinstance(d, bool) or not isinstance(d, int) or d not in AvailabilitySlot.Day.values
                                                  for d in days)):
                raise serializers.ValidationError({'unavailable_days': 'Send a list of days from 0 (Monday) to 6 (Sunday).'})
            changed = sorted(set(days)) != sorted(target.unavailable_days or [])
            target.unavailable_days = sorted(set(days))
            target.save(update_fields=['unavailable_days'])
            if changed and target.pk == profile.pk:
                services.notify_availability_change(target)
        return Response({'employee': target.pk, 'unavailable_days': list(target.unavailable_days or [])})

    def perform_update(self, serializer):
        self._check_employee(serializer.instance.employee)
        if 'employee' in serializer.validated_data:
            self._check_employee(serializer.validated_data['employee'])
        serializer.save()
        self._alert(serializer.instance.employee)

    def perform_destroy(self, instance):
        self._check_employee(instance.employee)
        employee = instance.employee
        instance.delete()
        self._alert(employee)


class TimeOffRequestViewSet(viewsets.ModelViewSet):
    """
    CRUD for time-off requests. New requests are always "pending"; approve or deny with a PATCH on status.
    Optional list filters: ?employee=<id> ?department=<id> ?status=pending|approved|denied
                           ?date_from=YYYY-MM-DD ?date_to=YYYY-MM-DD  (requests that overlap that window)
    """
    serializer_class = TimeOffRequestSerializer
    permission_classes = [IsAuthenticated, access.HasProfile]

    def get_queryset(self):
        profile = access.get_profile(self.request.user)
        qs = TimeOffRequest.objects.select_related('employee__user')
        qs = access.scope_by_employee(qs, profile) if access.is_staff_role(profile) else qs.filter(employee=profile)
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

    def create(self, request, *args, **kwargs):
        # Requests are always for yourself; the employee id may be left out.
        profile = access.get_profile(request.user)
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        data.setdefault('employee', profile.pk)
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data['employee'].pk != profile.pk:
            raise PermissionDenied('You can only request time off for yourself.')
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def _check_decider(self, instance):
        """Approve/reject/edit: managers of the employee's department or the General Manager (never your own request)."""
        profile = access.get_profile(self.request.user)
        if not access.is_staff_role(profile):
            raise PermissionDenied('Only managers and the General Manager can answer time-off requests.')
        require_manage_scope(profile, instance.employee)
        if instance.employee_id == profile.pk and not access.is_ceo(profile):
            raise PermissionDenied('You cannot answer your own request.')

    def perform_update(self, serializer):
        self._check_decider(serializer.instance)
        if 'employee' in serializer.validated_data and serializer.validated_data['employee'] != serializer.instance.employee:
            raise PermissionDenied('The employee on a request cannot be changed.')
        serializer.save()

    def perform_destroy(self, instance):
        profile = access.get_profile(self.request.user)
        if instance.employee_id == profile.pk and instance.status == TimeOffRequest.Status.PENDING:
            instance.delete()  # withdraw your own pending request
            return
        self._check_decider(instance)
        instance.delete()


class ProjectViewSet(viewsets.ModelViewSet):
    """
    CRUD for projects.
    Optional list filters: ?company=<id> ?department=<id> ?priority=low|medium|high ?is_active=true|false
    """
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, access.StaffWritesOnly]

    def get_queryset(self):
        profile = access.get_profile(self.request.user)
        qs = projects.visible_projects(Project.objects.all(), profile).prefetch_related(
            'milestones__assignments__employee__user').select_related('department')
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

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, access.StaffOnly])
    def people(self, request):
        """Who can be assigned to milestones: ?department=<id> (its people) or none for a company-wide project."""
        profile = access.get_profile(request.user)
        raw = request.query_params.get('department')
        if raw:
            department_id = int_param(request.query_params, 'department')
            if not access.can_manage_department(profile, department_id):
                raise PermissionDenied('You do not manage that department.')
            pool = access.members_of(department_id)
        elif access.is_ceo(profile):
            pool = EmployeeProfile.objects.filter(company_id=profile.company_id)
        else:
            raise PermissionDenied('Only the General Manager can manage company-wide projects.')
        pool = pool.filter(company_id=profile.company_id).select_related('user')
        return Response([{'id': p.pk, 'name': services.display_name(p.user)}
                         for p in pool if not services.is_roster_user(p.user)])

    def _check_scope(self, company, department):
        profile = access.get_profile(self.request.user)
        if company.pk != profile.company_id:
            raise PermissionDenied('That company is not yours.')
        if department is not None:
            if not access.can_manage_department(profile, department.pk):
                raise PermissionDenied('You do not manage that department.')
        elif not access.is_ceo(profile):
            raise PermissionDenied('Only the General Manager can create company-wide projects.')

    def perform_create(self, serializer):
        self._check_scope(serializer.validated_data['company'], serializer.validated_data.get('department'))
        serializer.save()

    def perform_update(self, serializer):
        self._check_scope(serializer.instance.company, serializer.instance.department)
        company = serializer.validated_data.get('company', serializer.instance.company)
        department = serializer.validated_data.get('department', serializer.instance.department)
        self._check_scope(company, department)
        serializer.save()

    def perform_destroy(self, instance):
        self._check_scope(instance.company, instance.department)
        instance.delete()


class MilestoneViewSet(viewsets.GenericViewSet):
    """Create / edit / delete the milestones of a project. Managers (of the project's department; the General Manager
    for company-wide projects) change anything and assign people; an assigned person may only change the status of
    their own milestone."""
    permission_classes = [IsAuthenticated, access.HasProfile]
    ASSIGNEE_FIELDS = {'title', 'description', 'due_date', 'status', 'assignee_ids'}

    def get_queryset(self):
        profile = access.get_profile(self.request.user)
        return Milestone.objects.filter(project__in=projects.visible_projects(Project.objects.all(), profile))

    def _body(self, request, partial):
        data = request.data
        out = {}
        if 'title' in data or not partial:
            title = str(data.get('title') or '').strip()
            if not title:
                raise serializers.ValidationError({'title': 'Give the milestone a title.'})
            out['title'] = title[:200]
        if 'description' in data:
            out['description'] = str(data.get('description') or '')
        if 'due_date' in data:
            raw = data.get('due_date')
            if raw in (None, ''):
                out['due_date'] = None
            else:
                out['due_date'] = parse_date(str(raw))
                if out['due_date'] is None:
                    raise serializers.ValidationError({'due_date': 'Use a date like 2026-12-31.'})
        if 'status' in data:
            out['status'] = choice_param(data, 'status', Milestone.Status.values)
        return out

    def _assignees(self, project, ids):
        try:
            ids = {int(i) for i in (ids or [])}
        except (TypeError, ValueError):
            raise serializers.ValidationError({'assignee_ids': 'Pick people from the list.'})
        pool = (EmployeeProfile.objects.filter(company_id=project.company_id) if project.department_id is None
                else access.members_of(project.department_id))
        people = list(pool.filter(pk__in=ids).select_related('user'))
        if len(people) != len(ids):
            raise serializers.ValidationError({'assignee_ids': 'You can only assign people who can see this project.'})
        return people

    def _set_assignees(self, milestone, people):
        have = {a.employee_id for a in milestone.assignments.all()}
        want = {p.pk for p in people}
        milestone.assignments.exclude(employee_id__in=want).delete()
        due = f' (due {milestone.due_date:%b %d})' if milestone.due_date else ''
        for p in people:
            if p.pk not in have:
                MilestoneAssignment.objects.create(milestone=milestone, employee=p)
                services.notify(p.user, 'info', f'You were assigned to "{milestone.title}" on the project '
                                f'"{milestone.project.name}"{due}.')

    def _respond(self, milestone, status_code=200):
        milestone = Milestone.objects.prefetch_related('assignments__employee__user').get(pk=milestone.pk)
        return Response(projects.milestone_data(milestone, access.get_profile(self.request.user)), status=status_code)

    def create(self, request):
        profile = access.get_profile(request.user)
        try:
            project_id = int(request.data.get('project'))
        except (TypeError, ValueError):
            project_id = None
        project = projects.visible_projects(Project.objects.all(), profile).filter(pk=project_id).first()
        if project is None:
            raise serializers.ValidationError({'project': 'Pick one of your projects.'})
        if not projects.can_edit_project(profile, project):
            raise PermissionDenied('You do not manage this project.')
        body = self._body(request, partial=False)
        people = self._assignees(project, request.data.get('assignee_ids'))
        milestone = Milestone.objects.create(project=project, **body)
        self._set_assignees(milestone, people)
        return self._respond(milestone, 201)

    def partial_update(self, request, pk=None):
        profile = access.get_profile(request.user)
        milestone = self.get_queryset().select_related('project').filter(pk=pk).first()
        if milestone is None:
            return Response({'detail': 'Not found.'}, status=404)
        if projects.can_edit_project(profile, milestone.project):
            body = self._body(request, partial=True)
            people = self._assignees(milestone.project, request.data['assignee_ids']) if 'assignee_ids' in request.data else None
        elif milestone.assignments.filter(employee=profile).exists():
            if set(request.data) - {'status'}:
                raise PermissionDenied('You can only change the status of your own milestone.')
            body, people = self._body(request, partial=True), None
        else:
            raise PermissionDenied('You do not manage this project.')
        for field, value in body.items():
            setattr(milestone, field, value)
        milestone.save()
        if people is not None:
            self._set_assignees(milestone, people)
        return self._respond(milestone)

    def destroy(self, request, pk=None):
        profile = access.get_profile(request.user)
        milestone = self.get_queryset().select_related('project').filter(pk=pk).first()
        if milestone is None:
            return Response({'detail': 'Not found.'}, status=404)
        if not projects.can_edit_project(profile, milestone.project):
            raise PermissionDenied('You do not manage this project.')
        milestone.delete()
        return Response(status=204)
