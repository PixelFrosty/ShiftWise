import datetime
import secrets

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
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

    @property
    def employee_profile(self):
        """Backwards compatibility helper: returns the first employee profile if one exists."""
        return self.employee_profiles.first()

    def create_user(self, email, username, first_name, last_name, date_of_birth, password):
        User.objects.create_user(username, email, password, first_name, last_name, date_of_birth)


class Company(models.Model):
    name = models.CharField(max_length=255)
    # Hours of operation: the same open/close time every day. Set by the General Manager.
    open_time = models.TimeField(default=datetime.time(8, 0))
    close_time = models.TimeField(default=datetime.time(18, 0))
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
        CEO = 'ceo', 'General Manager'
        MANAGER = 'manager', 'Manager'
        EMPLOYEE = 'employee', 'Employee'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='employee_profiles')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='employees')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees')
    # Departments a manager is responsible for (the General Manager implicitly covers every department).
    managed_departments = models.ManyToManyField(Department, blank=True, related_name='managers')
    # Other departments an employee also works in. `department` stays their home department: the automatic
    # scheduler only fills that one, so a manager has to schedule them in these by hand.
    extra_departments = models.ManyToManyField(Department, blank=True, related_name='extra_members')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.EMPLOYEE)

    class EmploymentType(models.TextChoices):
        FULL_TIME = 'full_time', 'Full time'
        PART_TIME = 'part_time', 'Part time'

    employment_type = models.CharField(max_length=10, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME)
    # Full-time people are limited to 40 hours a week unless this is ticked.
    allow_overtime = models.BooleanField(default=False)
    # Weekdays (0 = Monday ... 6 = Sunday) the person ticked "not available" for. Days that are not
    # ticked and have no availability slots count as available all day.
    unavailable_days = models.JSONField(default=list, blank=True)
    position = models.CharField(max_length=255, blank=True)
    productivity_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    pay_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.pk:
            orig_company_id = EmployeeProfile.objects.filter(pk=self.pk).values_list('company_id', flat=True).first()
            if orig_company_id is not None and self.company_id and orig_company_id != self.company_id:
                raise ValidationError(
                    {'company': 'Company cannot be changed once assigned. Create a new employee profile instead.'}
                )
        if self.company_id and self.department_id:
            if self.department.company_id != self.company_id:
                raise ValidationError({'department': 'Department does not belong to the selected company.'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.get_full_name() or self.user.email


class Shift(models.Model):
    """A block of work a department needs covered on one day, and how many people it needs."""
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='shifts')
    name = models.CharField(max_length=100, blank=True)
    shift_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    headcount = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(100)])
    # True when a manager/General Manager deliberately placed the shift outside the hours of operation.
    outside_hours = models.BooleanField(default=False)
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    # Monday of the week the shift is in; kept in step with shift_date by save(). Posting works per department and week.
    week_start = models.DateField(editable=False, db_index=True)

    class Meta:
        ordering = ['shift_date', 'start_time', 'id']

    def save(self, *args, **kwargs):
        day = self.shift_date
        if isinstance(day, str):
            day = datetime.date.fromisoformat(day)
        self.week_start = day - datetime.timedelta(days=day.weekday())
        update_fields = kwargs.get('update_fields')
        if update_fields is not None and 'shift_date' in update_fields:
            kwargs['update_fields'] = {*update_fields, 'week_start'}
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.department} {self.shift_date} {self.start_time}-{self.end_time} x{self.headcount}'


class SchedulePublication(models.Model):
    """
    A department's week that a manager has posted. Until it exists the week is a draft: only managers and the
    General Manager can see its shifts. Posting is not undone, later edits show up straight away.
    """
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='publications')
    week_start = models.DateField()  # a Monday
    published_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-week_start', 'department_id']
        constraints = [models.UniqueConstraint(fields=['department', 'week_start'], name='one_publication_per_week')]

    def __str__(self):
        return f'{self.department} week of {self.week_start}'


class ShiftTemplate(models.Model):
    """A reusable shift ("Morning, 8-12, needs 2 people") that can be applied to days of a week."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='shift_templates')
    name = models.CharField(max_length=100)
    start_time = models.TimeField()
    end_time = models.TimeField()
    headcount = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(100)])
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_time', 'name', 'id']

    def __str__(self):
        return f'{self.name} {self.start_time}-{self.end_time} x{self.headcount}'


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
    # When set, this row is one person filling a spot on a department Shift.
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, null=True, blank=True, related_name='assignments')
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


class CompatibilityGroup(models.Model):
    """
    One 1-10 rating of how well a group of 2 or more employees work together.
    A given set of people has at most one group (rating it again updates it).
    Only managers and the General Manager can see or change these.
    """
    MIN_SCORE = 1
    MAX_SCORE = 10

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='compatibility_groups')
    members = models.ManyToManyField(EmployeeProfile, related_name='compatibility_groups')
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(MIN_SCORE), MaxValueValidator(MAX_SCORE)])
    rated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='compatibility_groups_rated')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']

    def __str__(self):
        return f'Group {self.pk}: {self.score}/10'


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


class Milestone(models.Model):
    """A step of a project. Managers set them up and assign people; everyone who can see the project sees the
    milestone, but only the people assigned to it (and managers) see who that is."""
    class Status(models.TextChoices):
        TODO = 'todo', 'To do'
        IN_PROGRESS = 'in_progress', 'In progress'
        DONE = 'done', 'Done'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.project}: {self.title}'


class MilestoneAssignment(models.Model):
    milestone = models.ForeignKey(Milestone, on_delete=models.CASCADE, related_name='assignments')
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='milestone_assignments')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['milestone', 'employee'], name='one_assignment_per_person')]

    def __str__(self):
        return f'{self.employee} on {self.milestone}'


def generate_join_code():
    """Random 8-character code like "K7QF-2MXA" (no look-alike characters)."""
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    raw = ''.join(secrets.choice(alphabet) for _ in range(8))
    return f'{raw[:4]}-{raw[4:]}'


class JoinCode(models.Model):
    """
    Single-use invitation. An employee code puts the new user in exactly one department;
    a manager code makes them a manager of one or more departments.
    """
    class Role(models.TextChoices):
        MANAGER = 'manager', 'Manager'
        EMPLOYEE = 'employee', 'Employee'

    code = models.CharField(max_length=12, unique=True, default=generate_join_code)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='join_codes')
    role = models.CharField(max_length=10, choices=Role.choices)
    departments = models.ManyToManyField(Department, related_name='join_codes')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_join_codes')
    created_at = models.DateTimeField(auto_now_add=True)
    used_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='used_join_codes')
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    @property
    def is_used(self):
        return self.used_at is not None

    def __str__(self):
        return f'{self.code} ({self.role})'


class TransferRequest(models.Model):
    """A manager asking for an employee to move to a department the manager does not manage."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='transfer_requests')
    from_department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='+')
    to_department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='incoming_transfers')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='+')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.employee} -> {self.to_department} ({self.status})'


class Notification(models.Model):
    class Kind(models.TextChoices):
        TRANSFER_REQUEST = 'transfer_request', 'Transfer request'
        TRANSFER_RESULT = 'transfer_result', 'Transfer result'
        NO_MANAGER = 'no_manager', 'Department has no manager'
        INFO = 'info', 'Info'
        SHIFT_REQUEST = 'shift_request', 'Shift request'

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INFO)
    message = models.CharField(max_length=500)
    transfer_request = models.ForeignKey(TransferRequest, on_delete=models.CASCADE, null=True, blank=True,
                                         related_name='notifications')
    shift_request = models.ForeignKey('ShiftRequest', on_delete=models.CASCADE, null=True, blank=True,
                                      related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.recipient}: {self.message}'


class ShiftRequest(models.Model):
    """
    One employee asking a coworker about a shift. Only the coworker (`target`) has to accept.
      give: requester asks `target` to take requester's `schedule`.
      take: requester asks to take `schedule`, which belongs to `target`.
      swap: requester's `schedule` is traded for target's `other_schedule`.
      offer: requester offers `schedule` to everyone in the department; the first to accept gets it.
    """
    class Kind(models.TextChoices):
        GIVE = 'give', 'Give my shift away'
        TAKE = 'take', 'Take their shift'
        SWAP = 'swap', 'Swap shifts'
        OFFER = 'offer', 'Offer my shift to the whole department'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        DECLINED = 'declined', 'Declined'
        CANCELLED = 'cancelled', 'Cancelled'

    kind = models.CharField(max_length=5, choices=Kind.choices)
    requester = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='shift_requests_made')
    # Who has to answer. Empty for an "offer" to the whole department until someone accepts it (then it is them).
    target = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, null=True, blank=True,
                               related_name='shift_requests_received')
    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='+')
    other_schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
