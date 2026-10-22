# Create your views here.


from django.utils.dateparse import parse_date
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from .models import AvailabilitySlot, CompatibilityScore, Project, Schedule, TimeOffRequest, User
from .serializers import (AvailabilitySlotSerializer, CompatibilityScoreSerializer, ProjectSerializer,
                          ScheduleSerializer, TimeOffRequestSerializer, UserSerializer)

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
    Accepts input via GET query parameters: ?email=...&username=...
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

    if not email and not username:
        return Response(
            {'detail': "At least one of 'email' or 'username' must be provided."},
            status=status.HTTP_400_BAD_REQUEST
        )

    query = Q()
    if email:
        query |= Q(email__iexact=email)
    if username:
        query |= Q(username__iexact=username)

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
        qs = Schedule.objects.select_related('employee__user')
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
