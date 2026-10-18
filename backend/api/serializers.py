from datetime import datetime, time, timedelta
from django.utils import timezone
from rest_framework import serializers
from .models import Schedule, Shift, User


class UserSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'date_of_birth']

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

class ShiftSerializer(serializers.ModelSerializer):
    schedule = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Shift
        fields = ['id', 'schedule', 'start', 'end', 'headcount_needed', 'notes']

    def validate_headcount_needed(self, value):
        if value < 1:
            raise serializers.ValidationError('headcount_needed must be at least 1.')
        return value

    def validate(self, attrs):
        # On partial updates fall back to the stored values for whichever side wasn't sent.
        start = attrs.get('start', getattr(self.instance, 'start', None))
        end = attrs.get('end', getattr(self.instance, 'end', None))
        if start and end and end <= start:
            raise serializers.ValidationError({'end': 'end must be after start.'})

        schedule = self.context.get('schedule') or getattr(self.instance, 'schedule', None)
        if schedule and start and end:
            window_start = timezone.make_aware(datetime.combine(schedule.week_start, time.min))
            window_end = window_start + timedelta(days=7)
            if start < window_start or end > window_end:
                raise serializers.ValidationError(
                    f'Shift must fall within the schedule week ({schedule.week_start} to '
                    f'{schedule.week_start + timedelta(days=6)}).')
        return attrs


class ScheduleSerializer(serializers.ModelSerializer):
    """List view: shift_count only. Detail view adds the nested shifts (read-only)."""

    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    shift_count = serializers.IntegerField(source='shifts.count', read_only=True)

    class Meta:
        model = Schedule
        fields = ['id', 'name', 'week_start', 'status', 'created_by', 'shift_count',
                  'date_created', 'date_modified']

    def validate_week_start(self, value):
        if value.weekday() != 0:
            raise serializers.ValidationError('week_start must be a Monday.')
        return value

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('name cannot be blank.')
        return value.strip()

    def validate(self, attrs):
        # Moving the week must not strand existing shifts outside it.
        new_week = attrs.get('week_start')
        if self.instance and new_week and new_week != self.instance.week_start:
            if self.instance.shifts.exists():
                raise serializers.ValidationError(
                    {'week_start': 'Cannot change week_start while the schedule has shifts.'})
        return attrs


class ScheduleDetailSerializer(ScheduleSerializer):
    shifts = ShiftSerializer(many=True, read_only=True)

    class Meta(ScheduleSerializer.Meta):
        fields = ScheduleSerializer.Meta.fields + ['shifts']