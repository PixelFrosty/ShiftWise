from rest_framework import serializers
from .models import (AvailabilitySlot, CompatibilityScore, Project, Schedule, TimeOffRequest, User)

class UserSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'date_of_birth']

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class ScheduleSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = ['id', 'task_name', 'employee', 'employee_name', 'shift_date', 'start_time',
                  'end_time', 'status', 'notes', 'created_at', 'modified_at']
        read_only_fields = ['created_at', 'modified_at']

    def get_employee_name(self, obj):
        return obj.employee.user.get_full_name() or obj.employee.user.email

    def validate_task_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('task_name cannot be blank.')
        return value.strip()

    def validate(self, attrs):
        # On partial updates fall back to the stored values for fields that weren't sent.
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        start, end = current('start_time'), current('end_time')
        if start and end and end <= start:
            raise serializers.ValidationError(
                {'end_time': 'end_time must be after start_time (overnight shifts are not supported).'})

        employee, day, status = current('employee'), current('shift_date'), current('status')
        if employee and day and start and end and status != Schedule.Status.CANCELLED:
            clashes = Schedule.objects.filter(
                employee=employee, shift_date=day, start_time__lt=end, end_time__gt=start,
            ).exclude(status=Schedule.Status.CANCELLED)
            if self.instance:
                clashes = clashes.exclude(pk=self.instance.pk)
            clash = clashes.first()
            if clash:
                raise serializers.ValidationError(
                    f'Overlaps existing schedule #{clash.pk} for this employee '
                    f'({clash.start_time:%H:%M}-{clash.end_time:%H:%M} on {clash.shift_date}).')
        return attrs


class CompatibilityScoreSerializer(serializers.ModelSerializer):
    employee_a_name = serializers.SerializerMethodField()
    employee_b_name = serializers.SerializerMethodField()

    class Meta:
        model = CompatibilityScore
        fields = ['id', 'employee_a', 'employee_a_name', 'employee_b', 'employee_b_name', 'score', 'rated_by']
        read_only_fields = ['rated_by']
        validators = []  # the pair is normalised and checked for duplicates in validate() below

    @staticmethod
    def _name(employee):
        return employee.user.get_full_name() or employee.user.email

    def get_employee_a_name(self, obj):
        return self._name(obj.employee_a)

    def get_employee_b_name(self, obj):
        return self._name(obj.employee_b)

    def validate(self, attrs):
        a = attrs.get('employee_a', getattr(self.instance, 'employee_a', None))
        b = attrs.get('employee_b', getattr(self.instance, 'employee_b', None))
        if a and b:
            if a.pk == b.pk:
                raise serializers.ValidationError('An employee cannot be rated against themselves.')
            if a.company_id != b.company_id:
                raise serializers.ValidationError('Both employees must belong to the same company.')
            if a.pk > b.pk:  # store the pair in a fixed order
                a, b = b, a
            attrs['employee_a'], attrs['employee_b'] = a, b

            duplicates = CompatibilityScore.objects.filter(employee_a=a, employee_b=b)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
                if (a.pk, b.pk) != (self.instance.employee_a_id, self.instance.employee_b_id):
                    raise serializers.ValidationError(
                        'The pair of employees cannot be changed. Delete this rating and create a new one.')
            if duplicates.exists():
                raise serializers.ValidationError(
                    f'This pair already has a rating (#{duplicates.first().pk}). Update it instead.')
        return attrs


def employee_display_name(employee):
    return employee.user.get_full_name() or employee.user.email


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    day_name = serializers.CharField(source='get_day_of_week_display', read_only=True)

    class Meta:
        model = AvailabilitySlot
        fields = ['id', 'employee', 'employee_name', 'day_of_week', 'day_name', 'start_time', 'end_time']

    def get_employee_name(self, obj):
        return employee_display_name(obj.employee)

    def validate(self, attrs):
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        employee, day = current('employee'), current('day_of_week')
        start, end = current('start_time'), current('end_time')
        if start and end and end <= start:
            raise serializers.ValidationError(
                {'end_time': 'end_time must be after start_time (overnight slots are not supported).'})
        if employee and day is not None and start and end:
            clashes = AvailabilitySlot.objects.filter(
                employee=employee, day_of_week=day, start_time__lt=end, end_time__gt=start)
            if self.instance:
                clashes = clashes.exclude(pk=self.instance.pk)
            clash = clashes.first()
            if clash:
                raise serializers.ValidationError(
                    f'Overlaps existing availability slot #{clash.pk} for this employee '
                    f'({clash.start_time:%H:%M}-{clash.end_time:%H:%M}).')
        return attrs


class TimeOffRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = TimeOffRequest
        fields = ['id', 'employee', 'employee_name', 'start_date', 'end_date', 'reason', 'status',
                  'requested_at']
        read_only_fields = ['requested_at']

    def get_employee_name(self, obj):
        return employee_display_name(obj.employee)

    def validate(self, attrs):
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        if self.instance is None and attrs.get('status', TimeOffRequest.Status.PENDING) != TimeOffRequest.Status.PENDING:
            raise serializers.ValidationError({'status': 'New requests always start as "pending".'})

        employee, start, end = current('employee'), current('start_date'), current('end_date')
        status = current('status') or TimeOffRequest.Status.PENDING
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'end_date cannot be before start_date.'})
        if employee and start and end and status != TimeOffRequest.Status.DENIED:
            clashes = TimeOffRequest.objects.filter(
                employee=employee, start_date__lte=end, end_date__gte=start,
            ).exclude(status=TimeOffRequest.Status.DENIED)
            if self.instance:
                clashes = clashes.exclude(pk=self.instance.pk)
            clash = clashes.first()
            if clash:
                raise serializers.ValidationError(
                    f'Overlaps existing time-off request #{clash.pk} ({clash.start_date} to {clash.end_date}, '
                    f'{clash.status}).')
        return attrs


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'company', 'department', 'name', 'description', 'priority', 'is_active',
                  'created_at', 'modified_at']
        read_only_fields = ['created_at', 'modified_at']

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('name cannot be blank.')
        return value.strip()

    def validate(self, attrs):
        company = attrs.get('company', getattr(self.instance, 'company', None))
        department = attrs.get('department', getattr(self.instance, 'department', None))
        if company and department and department.company_id != company.pk:
            raise serializers.ValidationError({'department': 'Department does not belong to this company.'})
        return attrs
