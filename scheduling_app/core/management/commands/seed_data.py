from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import (
    User, Department, Employee, EmployeeCompatibility,
    Schedule, Shift, ShiftAssignment, TimeOffRequest
)
import datetime


class Command(BaseCommand):
    help = "Seeds the database with test users, departments, employees, compatibility ratings, schedules, and shifts."

    def handle(self, *args, **options):
        self.stdout.write("Clearing existing data...")
        ShiftAssignment.objects.all().delete()
        Shift.objects.all().delete()
        Schedule.objects.all().delete()
        TimeOffRequest.objects.all().delete()
        EmployeeCompatibility.objects.all().delete()
        Employee.objects.all().delete()
        Department.objects.all().delete()
        User.objects.all().delete()

        self.stdout.write("Creating Users...")
        # CEO
        ceo = User.objects.create_superuser(
            username='ceo',
            email='ceo@example.com',
            password='password123',
            role=User.Role.CEO,
            first_name='Evelyn',
            last_name='Vance'
        )

        # Managers
        mgr1 = User.objects.create_user(
            username='manager1',
            email='mgr1@example.com',
            password='password123',
            role=User.Role.MANAGER,
            first_name='Marcus',
            last_name='Brody'
        )
        mgr2 = User.objects.create_user(
            username='manager2',
            email='mgr2@example.com',
            password='password123',
            role=User.Role.MANAGER,
            first_name='Sarah',
            last_name='Connor'
        )

        self.stdout.write("Creating Departments...")
        dept_front = Department.objects.create(name='Customer Experience', code='CX', description='Front-of-house operations and support')
        dept_ops = Department.objects.create(name='Logistics & Fulfillment', code='LOG', description='Inventory management and distribution')

        # Link Manager 1 to Customer Experience
        Employee.objects.create(
            user=mgr1,
            name='Marcus Brody',
            department=dept_front,
            position='Store Manager',
            contact_info='marcus@example.com / 555-0101',
            productivity_score=8.5,
            pay_rate=32.00,
            max_hours_per_week=40
        )

        # Create Employees in Customer Experience
        employees_data = [
            ('emp1', 'Alice Johnson', 'Senior Specialist', 9.2, 24.50, 40),
            ('emp2', 'Bob Smith', 'Floor Associate', 6.0, 19.00, 35),
            ('emp3', 'Carol Danvers', 'Customer Lead', 8.8, 26.00, 40),
            ('emp4', 'David Miller', 'Team Member', 7.5, 20.00, 30),
            ('emp5', 'Elena Rostova', 'Inventory Tech', 8.1, 21.00, 40),
            ('emp6', 'Frank Castle', 'Night Operations', 5.5, 18.50, 25),
        ]

        emp_objs = {}
        for uname, name, pos, score, pay, max_h in employees_data:
            user = User.objects.create_user(
                username=uname,
                email=f'{uname}@example.com',
                password='password123',
                role=User.Role.EMPLOYEE,
                first_name=name.split()[0],
                last_name=name.split()[1] if len(name.split()) > 1 else ''
            )
            emp = Employee.objects.create(
                user=user,
                name=name,
                department=dept_front,
                position=pos,
                contact_info=f'{uname}@example.com / 555-01{len(emp_objs)+10:02d}',
                productivity_score=score,
                pay_rate=pay,
                max_hours_per_week=max_h
            )
            emp_objs[uname] = emp

        self.stdout.write("Creating Pairwise Compatibility Ratings...")
        # Low compatibility friction pair (Alice Johnson & Bob Smith -> score 1.5/10)
        # The AI Auto-Scheduler will actively avoid pairing them on the same shift!
        EmployeeCompatibility.objects.create(
            employee_a=emp_objs['emp1'],
            employee_b=emp_objs['emp2'],
            score=1.5,
            notes='Interpersonal friction observed during Q3; avoid co-assignment.'
        )

        # High synergy pair (Carol Danvers & David Miller -> score 9.5/10)
        # The AI Auto-Scheduler will actively favor pairing them together!
        EmployeeCompatibility.objects.create(
            employee_a=emp_objs['emp3'],
            employee_b=emp_objs['emp4'],
            score=9.5,
            notes='Exceptional collaborative chemistry, improves customer CSAT.'
        )

        # Another friction pair (Bob Smith & Frank Castle -> score 2.0/10)
        EmployeeCompatibility.objects.create(
            employee_a=emp_objs['emp2'],
            employee_b=emp_objs['emp6'],
            score=2.0,
            notes='Communication breakdown on closing tasks.'
        )

        self.stdout.write("Creating Sample Schedule & Shifts...")
        # Current Monday
        today = timezone.now().date()
        monday = today + datetime.timedelta(days=(0 - today.weekday()) % 7)

        sched = Schedule.objects.create(
            department=dept_front,
            title=f"Week of {monday.strftime('%b %d')} - Frontline Coverage",
            week_start_date=monday,
            status=Schedule.Status.DRAFT,
            created_by=mgr1
        )

        # Helper for timezone-aware datetimes
        def make_dt(d, h, m):
            dt = datetime.datetime.combine(d, datetime.time(h, m))
            return timezone.make_aware(dt)

        # Create Shifts across the week (Monday through Friday)
        # Monday: Morning Shift (Needs 2 people), Evening Shift (Needs 1 person)
        Shift.objects.create(
            schedule=sched,
            role_title='Morning Floor Team',
            start_time=make_dt(monday, 8, 0),
            end_time=make_dt(monday, 16, 0),
            headcount_needed=2
        )
        Shift.objects.create(
            schedule=sched,
            role_title='Evening Closer',
            start_time=make_dt(monday, 15, 0),
            end_time=make_dt(monday, 22, 0),
            headcount_needed=1
        )

        # Tuesday: Morning (2 people), Evening (1 person)
        tue = monday + datetime.timedelta(days=1)
        Shift.objects.create(
            schedule=sched,
            role_title='Morning Floor Team',
            start_time=make_dt(tue, 8, 0),
            end_time=make_dt(tue, 16, 0),
            headcount_needed=2
        )
        Shift.objects.create(
            schedule=sched,
            role_title='Evening Closer',
            start_time=make_dt(tue, 15, 0),
            end_time=make_dt(tue, 22, 0),
            headcount_needed=1
        )

        # Wednesday: Mid-day Rush (Needs 2 people)
        wed = monday + datetime.timedelta(days=2)
        Shift.objects.create(
            schedule=sched,
            role_title='Mid-day Rush Team',
            start_time=make_dt(wed, 11, 0),
            end_time=make_dt(wed, 19, 0),
            headcount_needed=2
        )

        # Thursday: Full Day Lead (Needs 1 person)
        thu = monday + datetime.timedelta(days=3)
        Shift.objects.create(
            schedule=sched,
            role_title='Floor Lead',
            start_time=make_dt(thu, 9, 0),
            end_time=make_dt(thu, 17, 0),
            headcount_needed=1
        )

        # Friday: Weekend Kickoff (Needs 2 people)
        fri = monday + datetime.timedelta(days=4)
        Shift.objects.create(
            schedule=sched,
            role_title='Weekend Prep Team',
            start_time=make_dt(fri, 10, 0),
            end_time=make_dt(fri, 18, 0),
            headcount_needed=2
        )

        self.stdout.write("Creating Time-Off Requests (Approved & Pending)...")
        # emp2 (Bob Smith) has approved time-off on Wednesday & Thursday -> Hard constraint test!
        tor1 = TimeOffRequest.objects.create(
            employee=emp_objs['emp2'],
            start_date=wed,
            end_date=thu,
            reason='Family dental appointment and travel',
            status=TimeOffRequest.Status.APPROVED,
            reviewed_by=mgr1,
            reviewed_at=timezone.now(),
            decision_notes='Approved. Adequate coverage present.'
        )

        # emp5 (Elena Rostova) has a pending request for Friday
        tor2 = TimeOffRequest.objects.create(
            employee=emp_objs['emp5'],
            start_date=fri,
            end_date=fri,
            reason='Personal day off',
            status=TimeOffRequest.Status.PENDING
        )

        self.stdout.write(self.style.SUCCESS(
            "\nDatabase successfully seeded!\n"
            "--------------------------------------------------\n"
            "Demo Accounts (Password: 'password123'):\n"
            "  - CEO:       'ceo'\n"
            "  - Manager:   'manager1' (CX Department)\n"
            "  - Employees: 'emp1' (Alice), 'emp2' (Bob), 'emp3' (Carol), etc.\n"
            "--------------------------------------------------\n"
            f"Schedule created: '{sched.title}' with {sched.shifts.count()} shifts.\n"
            "Hard Constraint Test Ready: Bob Smith has approved time off for Wed-Thu.\n"
            "Soft Constraint Test Ready: Alice & Bob rated 1.5/10 (friction), Carol & Dave rated 9.5/10 (synergy).\n"
        ))
