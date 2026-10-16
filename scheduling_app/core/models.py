from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
import datetime

class User(AbstractUser):
    class Role(models.TextChoices):
        CEO = 'CEO', 'CEO'
        MANAGER = 'MANAGER', 'Manager'
        EMPLOYEE = 'EMPLOYEE', 'Employee'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE,
        help_text="Role determining user scoping and authorization"
    )

    @property
    def is_ceo(self):
        return self.role == self.Role.CEO or self.is_superuser

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_employee(self):
        return self.role == self.Role.EMPLOYEE

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Employee(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_profile'
    )
    name = models.CharField(max_length=150)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='employees'
    )
    position = models.CharField(max_length=100)
    contact_info = models.CharField(max_length=255, blank=True)
    productivity_score = models.FloatField(
        default=5.0,
        help_text="Productivity score e.g. 1.0 to 10.0"
    )
    pay_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Hourly pay rate (nullable)"
    )
    max_hours_per_week = models.PositiveIntegerField(
        default=40,
        help_text="Maximum hours allowed per week"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.position} ({self.department.name})"

    def has_approved_time_off(self, start_dt, end_dt):
        """Check if employee has approved time-off overlapping with the given range."""
        start_d = start_dt.date() if isinstance(start_dt, datetime.datetime) else start_dt
        end_d = end_dt.date() if isinstance(end_dt, datetime.datetime) else end_dt
        return self.time_off_requests.filter(
            status=TimeOffRequest.Status.APPROVED,
            start_date__lte=end_d,
            end_date__gte=start_d
        ).exists()


class EmployeeCompatibility(models.Model):
    employee_a = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='compatibility_a'
    )
    employee_b = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='compatibility_b'
    )
    score = models.FloatField(
        default=5.0,
        help_text="Score from 1 (hostile/friction) to 10 (high synergy). 5 is neutral."
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Employee compatibilities"
        constraints = [
            models.UniqueConstraint(
                fields=['employee_a', 'employee_b'],
                name='unique_employee_compatibility_pair'
            ),
        ]

    def clean(self):
        if self.employee_a_id and self.employee_b_id and self.employee_a_id == self.employee_b_id:
            raise ValidationError("An employee cannot have a compatibility score with themselves.")

    def save(self, *args, **kwargs):
        # Canonicalize order so (A, B) and (B, A) are stored uniformly as (min, max)
        if self.employee_a_id and self.employee_b_id:
            if self.employee_a_id > self.employee_b_id:
                self.employee_a, self.employee_b = self.employee_b, self.employee_a
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee_a.name} & {self.employee_b.name}: {self.score}/10"

    @classmethod
    def get_score(cls, emp1_id, emp2_id, default=5.0):
        if emp1_id == emp2_id:
            return default
        a, b = min(emp1_id, emp2_id), max(emp1_id, emp2_id)
        pair = cls.objects.filter(employee_a_id=a, employee_b_id=b).first()
        return pair.score if pair else default

    @classmethod
    def get_compatibility_matrix(cls):
        """Returns a dict mapping (min_id, max_id) -> score"""
        return {
            (obj.employee_a_id, obj.employee_b_id): obj.score
            for obj in cls.objects.all()
        }


class ScheduleQuerySet(models.QuerySet):
    def for_user(self, user):
        """Role-based and object-level scoping for schedules."""
        if not user.is_authenticated:
            return self.none()
        if user.is_ceo:
            return self.all()
        if user.is_manager:
            # Manager sees schedules they created or shifts in their department or where they appear
            return self.filter(
                Q(created_by=user) |
                Q(department__employees__user=user)
            ).distinct()
        if user.is_employee:
            # Employee sees published schedules they belong to
            return self.filter(
                status=Schedule.Status.PUBLISHED,
                shifts__assignments__employee__user=user
            ).distinct()
        return self.none()


class Schedule(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        ARCHIVED = 'ARCHIVED', 'Archived'

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='schedules'
    )
    title = models.CharField(max_length=200)
    week_start_date = models.DateField(
        help_text="Monday of the schedule week"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_schedules'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ScheduleQuerySet.as_manager()

    class Meta:
        ordering = ['-week_start_date', 'title']

    def __str__(self):
        return f"{self.title} ({self.department.name}) - {self.week_start_date}"

    @property
    def week_end_date(self):
        return self.week_start_date + datetime.timedelta(days=6)

    def total_shifts(self):
        return self.shifts.count()

    def total_headcount_needed(self):
        return sum(s.headcount_needed for s in self.shifts.all())

    def total_assignments(self):
        return sum(s.assignments.count() for s in self.shifts.all())


class Shift(models.Model):
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.CASCADE,
        related_name='shifts'
    )
    role_title = models.CharField(
        max_length=100,
        default="General Shift",
        help_text="Role or title for this shift e.g. Cashier, Floor Lead"
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    headcount_needed = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['start_time', 'end_time']

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("Shift start time must be before end time.")

    def __str__(self):
        return f"{self.role_title}: {self.start_time.strftime('%a %b %d, %H:%M')}-{self.end_time.strftime('%H:%M')} (Need {self.headcount_needed})"

    @property
    def duration_hours(self):
        if self.start_time and self.end_time:
            return round((self.end_time - self.start_time).total_seconds() / 3600.0, 2)
        return 0.0

    @property
    def assigned_count(self):
        return self.assignments.count()

    @property
    def is_filled(self):
        return self.assigned_count >= self.headcount_needed


class ShiftAssignment(models.Model):
    shift = models.ForeignKey(
        Shift,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='assignments'
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_auto_scheduled = models.BooleanField(
        default=False,
        help_text="Whether this assignment was created by the AI auto-scheduler"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['shift', 'employee'],
                name='unique_shift_employee_assignment'
            )
        ]
        ordering = ['shift__start_time']

    def clean(self):
        # Validate that employee doesn't have an approved time-off overlapping with this shift
        if self.employee_id and self.shift_id and hasattr(self, 'shift') and self.shift:
            if self.employee.has_approved_time_off(self.shift.start_time, self.shift.end_time):
                raise ValidationError(
                    f"{self.employee.name} has approved time-off covering this shift!"
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.name} -> {self.shift}"


class TimeOffRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        DENIED = 'DENIED', 'Denied'

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='time_off_requests'
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_time_offs'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date', '-created_at']

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Start date cannot be after end date.")

    def approve(self, user, notes=""):
        self.status = self.Status.APPROVED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.decision_notes = notes
        self.save()

        # If approved, remove any existing shift assignments in this range as required by Phase 3
        overlapping_assignments = ShiftAssignment.objects.filter(
            employee=self.employee,
            shift__start_time__date__lte=self.end_date,
            shift__end_time__date__gte=self.start_date
        )
        removed_count = overlapping_assignments.count()
        overlapping_assignments.delete()
        return removed_count

    def deny(self, user, notes=""):
        self.status = self.Status.DENIED
        self.reviewed_by = user
        self.reviewed_at = timezone.now()
        self.decision_notes = notes
        self.save()

    def __str__(self):
        return f"{self.employee.name}: {self.start_date} to {self.end_date} [{self.status}]"
