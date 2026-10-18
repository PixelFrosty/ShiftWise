from django.contrib.auth.models import AbstractUser
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


class Schedule(models.Model):
    """A weekly schedule. `week_start` is the Monday of the week it covers."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    name = models.CharField(max_length=100)
    week_start = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey('api.User', on_delete=models.PROTECT, related_name='schedules_created')
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-week_start', 'name']

    def __str__(self):
        return f'{self.name} ({self.week_start})'


class Shift(models.Model):
    """A block of time within a schedule that needs `headcount_needed` people."""

    schedule = models.ForeignKey(Schedule, on_delete=models.CASCADE, related_name='shifts')
    start = models.DateTimeField()
    end = models.DateTimeField()
    headcount_needed = models.PositiveSmallIntegerField(default=1)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['start', 'end']

    def __str__(self):
        return f'{self.schedule_id}: {self.start} - {self.end}'