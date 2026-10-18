# Create your views here.

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from .models import Schedule, Shift


from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from .serializers import (ScheduleDetailSerializer, ScheduleSerializer, ShiftSerializer,
                          UserSerializer)

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

"""
expects a JSON payload with the following attributes:
{ username, email, first_name, last_name, password, date_of_birth}
date of birth should be formatted as: YYYY-MM-DD
"""

class ScheduleViewSet(viewsets.ModelViewSet):
    """CRUD for schedules. Optional list filters: ?week_start=YYYY-MM-DD, ?status=draft|published."""

    def get_queryset(self):
        qs = Schedule.objects.prefetch_related('shifts')
        week_start = self.request.query_params.get('week_start')
        status_filter = self.request.query_params.get('status')
        if week_start:
            qs = qs.filter(week_start=week_start)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_serializer_class(self):
        return ScheduleDetailSerializer if self.action == 'retrieve' else ScheduleSerializer

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except DjangoValidationError:
            return Response({'week_start': 'Enter a valid date in YYYY-MM-DD format.'},
                            status=status.HTTP_400_BAD_REQUEST)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ShiftViewSet(viewsets.ModelViewSet):
    """CRUD for shifts nested under /schedules/<schedule_pk>/shifts/."""
    serializer_class = ShiftSerializer

    def get_schedule(self):
        return get_object_or_404(Schedule, pk=self.kwargs['schedule_pk'])

    def get_queryset(self):
        return Shift.objects.filter(schedule_id=self.kwargs['schedule_pk'])

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['schedule'] = self.get_schedule()
        return context

    def perform_create(self, serializer):
        serializer.save(schedule=self.get_schedule())