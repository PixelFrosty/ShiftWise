from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class User(AbstractUser):
    email = models.EmailField(unique=True, null=False, blank=False)
    username = models.CharField(max_length=30)
    first_name = models.CharField(max_length=20)
    last_name = models.CharField(max_length=20)
    date_of_birth = models.DateField(auto_now=False)
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name', 'date_of_birth']

    def __str__(self):
        return self.email

    def create_user(self, email, username, first_name, last_name, date_of_birth, password):
        User.objects.create_user(username, email, password, first_name, last_name, date_of_birth)


class Company(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name


class Department(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.company})'


class EmployeeProfile(models.Model):
    class Role(models.TextChoices):
        CEO = 'ceo', 'CEO'
        MANAGER = 'manager', 'Manager'
        EMPLOYEE = 'employee', 'Employee'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.EMPLOYEE)
    position = models.CharField(max_length=255, blank=True)
    productivity_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pay_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.email


class Schedule(models.Model):
    """One scheduled work block for one employee on one day."""

    class Status(models.TextChoices):
        SCHEDULED = 'scheduled', 'Scheduled'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    task_name = models.CharField(max_length=255)
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='schedules')
    shift_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['shift_date', 'start_time', 'id']

    def __str__(self):
        return f'{self.task_name}: {self.employee} {self.shift_date} {self.start_time}-{self.end_time}'


class CompatibilityScore(models.Model):
    """
    "Compatibility Scoring" in the team diagram: how well two employees work together.
    One row per unordered pair. The lower employee id is always stored in `employee_a`, so
    (3, 1) and (1, 3) are the same row. Pairs nobody has rated simply have no row.
    """
    MIN_SCORE = 0
    MAX_SCORE = 10

    employee_a = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='compatibility_as_a')
    employee_b = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='compatibility_as_b')
    score = models.DecimalField(max_digits=4, decimal_places=2,
                                validators=[MinValueValidator(MIN_SCORE), MaxValueValidator(MAX_SCORE)])
    rated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='compatibility_ratings')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['employee_a', 'employee_b'], name='unique_compatibility_pair'),
            models.CheckConstraint(condition=models.Q(employee_a__lt=models.F('employee_b')),
                                   name='compatibility_pair_ordered'),
        ]
        ordering = ['employee_a_id', 'employee_b_id']

    def save(self, *args, **kwargs):
        if self.employee_a_id and self.employee_b_id and self.employee_a_id > self.employee_b_id:
            self.employee_a, self.employee_b = self.employee_b, self.employee_a
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.employee_a} + {self.employee_b}: {self.score}'


class AvailabilitySlot(models.Model):
    """When an employee is available to work, as a recurring weekly slot (day of week + times)."""

    class Day(models.IntegerChoices):
        MONDAY = 0, 'Monday'
        TUESDAY = 1, 'Tuesday'
        WEDNESDAY = 2, 'Wednesday'
        THURSDAY = 3, 'Thursday'
        FRIDAY = 4, 'Friday'
        SATURDAY = 5, 'Saturday'
        SUNDAY = 6, 'Sunday'

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='availability_slots')
    day_of_week = models.SmallIntegerField(choices=Day.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ['employee_id', 'day_of_week', 'start_time']

    def __str__(self):
        return f'{self.employee} {self.get_day_of_week_display()} {self.start_time}-{self.end_time}'


class TimeOffRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        DENIED = 'denied', 'Denied'

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='time_off_requests')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date', 'id']

    def __str__(self):
        return f'{self.employee} off {self.start_date} to {self.end_date} ({self.status})'


class Project(models.Model):
    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='projects')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='projects')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']

    def __str__(self):
        return self.name
