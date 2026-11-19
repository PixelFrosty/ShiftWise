from rest_framework import serializers
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

class UserSerializer(serializers.ModelSerializer):

    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'date_of_birth']

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


class EmployeeProfileSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model = EmployeeProfile
        fields = ['id', 'user', 'employee_name', 'name', 'first_name', 'last_name', 'email',
                  'company', 'department', 'department_name', 'role', 'position',
                  'productivity_score', 'pay_rate', 'created_at', 'modified_at']
        read_only_fields = ['created_at', 'modified_at']

    def get_employee_name(self, obj):
        return obj.user.get_full_name() or obj.user.email

    def get_name(self, obj):
        return obj.user.get_full_name() or obj.user.email

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.department:
            ret['department'] = {'id': instance.department.id, 'name': instance.department.name}
        ret['extra_departments'] = []
        ret['is_roster'] = False
        ret['is_minor'] = False
        return ret

    def validate(self, attrs):
        if self.instance and self.instance.pk and 'company' in attrs:
            if attrs['company'].pk != self.instance.company_id:
                raise serializers.ValidationError(
                    {'company': 'Company cannot be changed once assigned. Create a new employee profile instead.'}
                )
        company = attrs.get('company', getattr(self.instance, 'company', None))
        department = attrs.get('department', getattr(self.instance, 'department', None))
        if company and department and department.company_id != company.pk:
            raise serializers.ValidationError({'department': 'Department does not belong to this company.'})
        return attrs


class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.SerializerMethodField()
    managers = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ['id', 'company', 'name', 'employee_count', 'managers', 'created_at', 'modified_at']
        read_only_fields = ['created_at', 'modified_at']

    def get_employee_count(self, obj):
        return obj.employees.count()

    def get_managers(self, obj):
        return [
            e.user.get_full_name() or e.user.email
            for e in obj.employees.filter(role__in=[EmployeeProfile.Role.CEO, EmployeeProfile.Role.MANAGER]).select_related('user')
        ]


class TaskSerializer(serializers.ModelSerializer):
    skills_names = serializers.SerializerMethodField()
    department_name = serializers.CharField(source='department.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'company', 'name', 'description', 'priority', 'preferred_window',
            'is_recurring', 'required_people', 'duration_hours', 'skills', 'skills_names',
            'project', 'project_name', 'department', 'department_name', 'employee'
        ]

    def get_skills_names(self, obj):
        return [s.name for s in obj.skills.all()]


class ScheduleSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    task_required_people = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()

    class Meta:
        model = Schedule
        fields = ['id', 'task', 'task_name', 'employee', 'employee_name', 'shift_date', 'start_time',
                  'end_time', 'status', 'notes', 'task_required_people', 'department', 'created_at', 'modified_at']
        read_only_fields = ['created_at', 'modified_at']
        extra_kwargs = {
            'employee': {'required': True, 'allow_null': True},
        }

    def get_employee_name(self, obj):
        if not obj.employee:
            return None
        return obj.employee.user.get_full_name() or obj.employee.user.email

    def get_task_required_people(self, obj):
        if obj.task:
            return obj.task.required_people
        return None

    def get_department(self, obj):
        if obj.employee and obj.employee.department_id:
            return obj.employee.department_id
        if obj.task and obj.task.department_id:
            return obj.task.department_id
        return None

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
                employee__user=employee.user, shift_date=day, start_time__lt=end, end_time__gt=start,
            ).exclude(status=Schedule.Status.CANCELLED)
            if self.instance:
                clashes = clashes.exclude(pk=self.instance.pk)
            clash = clashes.first()
            if clash:
                raise serializers.ValidationError(
                    f'Overlaps existing schedule #{clash.pk} for this employee '
                    f'({clash.start_time:%H:%M}-{clash.end_time:%H:%M} on {clash.shift_date}).')

        task = current('task')
        if task and employee and status != Schedule.Status.CANCELLED and day and start and end:
            existing = Schedule.objects.filter(
                task=task, shift_date=day, start_time=start, end_time=end, employee__isnull=False
            ).exclude(status=Schedule.Status.CANCELLED)
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.count() >= task.required_people:
                raise serializers.ValidationError(
                    f'Cannot add more than {task.required_people} employee(s) to this schedule (headcount required by task).'
                )

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
            if a.pk == b.pk or a.user_id == b.user_id:
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


class GenerateShiftsSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(required=True)
    week_start = serializers.DateField(required=True)
    department_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    clear_existing = serializers.BooleanField(required=False, default=False)

    def validate_company_id(self, value):
        if not Company.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f"Company #{value} does not exist.")
        return value

    def validate(self, attrs):
        dept_id = attrs.get('department_id')
        comp_id = attrs.get('company_id')
        if dept_id:
            if not Department.objects.filter(pk=dept_id, company_id=comp_id).exists():
                raise serializers.ValidationError(
                    {'department_id': 'Department does not exist or does not belong to this company.'}
                )
        return attrs
        return attrs
