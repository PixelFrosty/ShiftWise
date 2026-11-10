"""
Wipe the database and fill it with mock data for testing.

    python manage.py reset_demo_data --yes

DELETES EVERY account, company, department, schedule, request and code. Local testing only.
"""
import datetime
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.admin.models import LogEntry
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from api import services
from api.models import (AvailabilitySlot, Company, CompatibilityGroup, CompatibilityScore, Department, EmployeeProfile, JoinCode,
                        Notification, Project, Schedule, SchedulePublication, Shift, ShiftRequest, ShiftTemplate, TimeOffRequest,
                        TransferRequest, User)

PASSWORD = 'ShiftWise123!'

# (first, last, email or None for roster-only, role, department, position, productivity, pay)
PEOPLE = [
    ('Frank', 'Lee', 'ceo@example.com', 'ceo', 'Engineering', 'General Manager', None, None),
    ('Carol', 'Williams', 'manager@example.com', 'manager', 'Operations', 'Operations Manager', '9.0', '62.00'),
    ('Bob', 'Martinez', 'manager2@example.com', 'manager', 'Marketing', 'Marketing Lead', '7.2', '48.00'),
    ('Alice', 'Johnson', 'employee@example.com', 'employee', 'Engineering', 'Senior Developer', '8.5', '55.00'),
    ('Dana', 'Brooks', 'employee2@example.com', 'employee', 'Engineering', 'QA Engineer', '7.5', '45.00'),
    ('David', 'Chen', None, 'employee', 'Engineering', 'Junior Developer', '6.0', '35.00'),
    ('Eva', 'Thompson', None, 'employee', 'Human Resources', 'HR Coordinator', '7.8', '42.00'),
    ('Grace', 'Kim', None, 'employee', 'Marketing', 'Content Strategist', '8.0', '40.00'),
    ('Henry', 'Patel', None, 'employee', 'Engineering', 'DevOps Engineer', '9.3', '58.00'),
]


class Command(BaseCommand):
    help = 'Delete ALL data and load mock data (company, departments, people, shifts, codes). Needs --yes.'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Confirm that everything should be deleted.')

    @transaction.atomic
    def handle(self, *args, **options):
        if not options['yes']:
            raise CommandError('This deletes ALL data. Run again with --yes to confirm.')

        for model in (Notification, ShiftRequest, CompatibilityGroup, TransferRequest, ShiftTemplate, Shift, JoinCode, Schedule, CompatibilityScore, AvailabilitySlot,
                      TimeOffRequest, Project, EmployeeProfile, Department, Company, BlacklistedToken,
                      OutstandingToken, LogEntry, Session, User):
            model.objects.all().delete()

        company = Company.objects.create(name='Demo Company', open_time=datetime.time(8, 0),
                                         close_time=datetime.time(18, 0))
        departments = {name: Department.objects.create(company=company, name=name)
                       for name in ('Engineering', 'Marketing', 'Operations', 'Human Resources')}

        profiles = {}
        for first, last, email, role, dept, position, productivity, pay in PEOPLE:
            if email:
                user = User.objects.create_user(
                    username=f'{first}.{last}'.lower(), email=email, first_name=first, last_name=last,
                    password=PASSWORD, date_of_birth='1990-01-01')
            else:  # roster-only: no login
                user = User(username=f'{first}.{last}'.lower(), email=f'{first}.{last}{services.ROSTER_DOMAIN}'.lower(),
                            first_name=first, last_name=last, date_of_birth='1990-01-01')
                user.set_unusable_password()
                user.save()
            profiles[first] = EmployeeProfile.objects.create(
                user=user, company=company, department=departments[dept], role=role, position=position,
                productivity_score=Decimal(productivity) if productivity else None,
                pay_rate=Decimal(pay) if pay else None)

        # Full time / part time, and one demo minor (David is 17; roster people have no birth date unless entered).
        for first in ('Dana', 'David', 'Grace'):
            profiles[first].employment_type = EmployeeProfile.EmploymentType.PART_TIME
            profiles[first].save()
        profiles['Alice'].allow_overtime = True
        profiles['Alice'].save()
        david = profiles['David'].user
        david.date_of_birth = date.today() - timedelta(days=17 * 365 + 60)
        david.save()

        # Carol runs Operations and Engineering; Bob runs Marketing; Human Resources has no manager (General Manager covers it).
        profiles['Carol'].managed_departments.set([departments['Operations'], departments['Engineering']])
        profiles['Bob'].managed_departments.set([departments['Marketing']])

        monday = date.today() - timedelta(days=date.today().weekday())

        # Time off first, so the shifts below skip anyone who is off that day.
        # Henry is approved off next Wednesday: assigning him to a shift that day shows the warning.
        TimeOffRequest.objects.create(employee=profiles['Henry'], start_date=monday + timedelta(days=9),
                                      end_date=monday + timedelta(days=9), reason='Dentist',
                                      status=TimeOffRequest.Status.APPROVED)

        # Reusable shift templates, and shifts for this week and next (some left partly open).
        templates = [('Morning', '08:00', '12:00', 2), ('Afternoon', '12:00', '18:00', 2), ('Full day', '08:00', '18:00', 1)]
        for name, start, end, count in templates:
            ShiftTemplate.objects.create(company=company, name=name, start_time=start, end_time=end, headcount=count,
                                         created_by=profiles['Frank'].user)
        # A couple of compatibility ratings (1-10) for groups of people who work together.
        for names, score in ((('Alice', 'Dana'), 9), (('Alice', 'Dana', 'Henry'), 7), (('David', 'Henry'), 2)):
            group = CompatibilityGroup.objects.create(company=company, score=score, rated_by=profiles['Frank'].user)
            group.members.set([profiles[n] for n in names])
        members = {dept: [p for p in profiles.values() if p.department_id == departments[dept].id and p.role == 'employee']
                   for dept in departments}
        members['Operations'] = [profiles['Carol']]
        members['Marketing'] = [profiles['Bob'], profiles['Grace']]
        off_days = {(p.pk, r.start_date) for r in TimeOffRequest.objects.filter(status='approved')
                    for p in [r.employee]}
        for week in (0, 1):
            for dept_name, department in departments.items():
                people = members[dept_name]
                if not people:
                    continue
                for day in range(5):
                    shift_day = monday + timedelta(days=7 * week + day)
                    for index, (name, start, end, count) in enumerate(templates[:2]):
                        need = min(count, 2) if dept_name == 'Engineering' else 1
                        shift = Shift.objects.create(department=department, name=name, shift_date=shift_day,
                                                     start_time=start, end_time=end, headcount=need,
                                                     created_by=profiles['Frank'].user)
                        # Leave some shifts short-handed so there are open spots to fill.
                        fill = need - 1 if (day + index + week) % 3 == 0 else need
                        pool = [p for p in people if (p.pk, shift_day) not in off_days]
                        for k in range(fill):
                            if not pool:
                                break
                            person = pool[(day + index + k) % len(pool)]
                            pool.remove(person)
                            Schedule.objects.create(task_name=name, employee=person, shift_date=shift_day,
                                                    start_time=start, end_time=end, shift=shift)
                Shift.objects.create(department=department, name='Morning', shift_date=monday + timedelta(days=7 * week + 5),
                                     start_time='09:00', end_time='13:00', headcount=1, created_by=profiles['Frank'].user)
                if week == 0:  # this week is posted; next week stays a draft so the post flow can be tried
                    SchedulePublication.objects.create(department=department, week_start=monday,
                                                       published_by=profiles['Frank'].user)

        next_thursday = monday + timedelta(days=10)
        TimeOffRequest.objects.create(employee=profiles['Alice'], start_date=next_thursday,
                                      end_date=next_thursday + timedelta(days=1), reason='Family trip')
        TimeOffRequest.objects.create(employee=profiles['Grace'], start_date=monday + timedelta(days=8),
                                      end_date=monday + timedelta(days=8), reason='Appointment')
        TimeOffRequest.objects.create(employee=profiles['David'], start_date=monday + timedelta(days=16),
                                      end_date=monday + timedelta(days=17), reason='Moving',
                                      status=TimeOffRequest.Status.APPROVED)
        TimeOffRequest.objects.create(employee=profiles['Eva'], start_date=monday + timedelta(days=9),
                                      end_date=monday + timedelta(days=9), reason='Training day')

        # A pending transfer: Bob (Marketing) asks to move Grace to Operations, which Carol runs.
        services.start_transfer(profiles['Bob'], profiles['Grace'], departments['Operations'])

        codes = []
        for creator, role, dept in (('Carol', 'employee', 'Engineering'), ('Bob', 'employee', 'Marketing'),
                                    ('Frank', 'employee', 'Human Resources'), ('Frank', 'manager', 'Human Resources')):
            code = JoinCode.objects.create(company=company, role=role, created_by=profiles[creator].user)
            code.departments.set([departments[dept]])
            codes.append((code.code, role, dept))

        out = self.stdout.write
        out(self.style.SUCCESS('Done. Everything was deleted and mock data was loaded.'))
        out('')
        out(f'Test logins (password for all: {PASSWORD})')
        for first, last, email, role, dept, *_ in PEOPLE:
            if email:
                out(f'  {role.upper():9} {email:24} {first} {last} ({dept})')
        out('  Roster-only (no login): David Chen, Eva Thompson, Grace Kim, Henry Patel')
        out('')
        out('Unused single-use join codes:')
        for code, role, dept in codes:
            out(f'  {code}  {role:9} {dept}')
