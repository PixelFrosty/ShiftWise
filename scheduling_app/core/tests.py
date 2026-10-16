import pytest
import datetime
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from core.models import (
    User, Department, Employee, EmployeeCompatibility,
    Schedule, Shift, ShiftAssignment, TimeOffRequest
)
from core.scheduler import PriorityScheduler
from core.permissions import can_view_schedule, can_edit_schedule, can_manage_time_off


@pytest.mark.django_db
class TestPhase0Foundation:
    def test_user_roles(self):
        ceo = User.objects.create(username='ceo_test', role=User.Role.CEO)
        mgr = User.objects.create(username='mgr_test', role=User.Role.MANAGER)
        emp = User.objects.create(username='emp_test', role=User.Role.EMPLOYEE)

        assert ceo.is_ceo is True
        assert ceo.is_manager is False
        assert mgr.is_manager is True
        assert emp.is_employee is True


@pytest.mark.django_db
class TestPhase1EmployeeAndCompatibility:
    def test_employee_creation_and_fields(self):
        dept = Department.objects.create(name='Operations', code='OPS')
        emp = Employee.objects.create(
            name='John Doe',
            department=dept,
            position='Operator',
            productivity_score=7.5,
            pay_rate=25.00,
            max_hours_per_week=40
        )
        assert emp.name == 'John Doe'
        assert emp.department == dept
        assert emp.pay_rate == 25.00
        assert emp.max_hours_per_week == 40

    def test_pairwise_compatibility_canonical_order_and_neutral(self):
        dept = Department.objects.create(name='Sales', code='SALES')
        emp1 = Employee.objects.create(name='Alpha', department=dept, position='Rep')
        emp2 = Employee.objects.create(name='Beta', department=dept, position='Rep')
        emp3 = Employee.objects.create(name='Gamma', department=dept, position='Rep')

        # Store pair in reverse order (Beta, Alpha) -> should canonicalize to min, max
        pair = EmployeeCompatibility(employee_a=emp2, employee_b=emp1, score=2.5)
        pair.save()

        # Check canonical ordering in DB
        assert pair.employee_a_id < pair.employee_b_id

        # Check lookup helper returns score for either order
        assert EmployeeCompatibility.get_score(emp1.id, emp2.id) == 2.5
        assert EmployeeCompatibility.get_score(emp2.id, emp1.id) == 2.5

        # Unrated pair should return neutral default 5.0
        assert EmployeeCompatibility.get_score(emp1.id, emp3.id) == 5.0


@pytest.mark.django_db
class TestPhase2ScheduleAndManualEditor:
    def test_schedule_and_manual_shift_assignment(self):
        dept = Department.objects.create(name='Kitchen', code='KIT')
        mgr = User.objects.create(username='chefmgr', role=User.Role.MANAGER)
        emp = Employee.objects.create(name='Cook 1', department=dept, position='Line Cook')

        monday = timezone.now().date()
        sched = Schedule.objects.create(
            department=dept,
            title='Kitchen Week 1',
            week_start_date=monday,
            created_by=mgr
        )

        shift = Shift.objects.create(
            schedule=sched,
            role_title='Morning Prep',
            start_time=timezone.now(),
            end_time=timezone.now() + datetime.timedelta(hours=6),
            headcount_needed=2
        )

        assert shift.duration_hours == 6.0
        assert shift.is_filled is False

        # Assign cook manually
        asgn = ShiftAssignment.objects.create(
            shift=shift,
            employee=emp,
            assigned_by=mgr,
            is_auto_scheduled=False
        )
        assert shift.assigned_count == 1
        assert asgn.is_auto_scheduled is False


@pytest.mark.django_db
class TestPhase3RequestOffsAndPileup:
    def test_time_off_blocks_assignment_and_unassigns_on_approval(self):
        dept = Department.objects.create(name='Support', code='SUP')
        mgr = User.objects.create(username='sup_mgr', role=User.Role.MANAGER)
        emp = Employee.objects.create(name='Support Agent', department=dept, position='Agent')

        today = timezone.now().date()
        shift = Shift.objects.create(
            schedule=Schedule.objects.create(department=dept, title='Week', week_start_date=today, created_by=mgr),
            role_title='Chat Shift',
            start_time=timezone.now(),
            end_time=timezone.now() + datetime.timedelta(hours=8),
            headcount_needed=1
        )

        # Initially assign employee
        asgn = ShiftAssignment.objects.create(shift=shift, employee=emp)
        assert shift.assignments.count() == 1

        # Employee requests time off for today
        tor = TimeOffRequest.objects.create(
            employee=emp,
            start_date=today,
            end_date=today,
            reason='Medical appointment'
        )
        assert tor.status == TimeOffRequest.Status.PENDING

        # Manager approves -> Overlapping shift should be automatically unassigned!
        removed = tor.approve(mgr, notes="Approved with coverage")
        assert removed == 1
        assert shift.assignments.count() == 0
        assert tor.status == TimeOffRequest.Status.APPROVED
        assert tor.reviewed_by == mgr

        # Attempting to assign employee now must fail validation!
        with pytest.raises(ValidationError):
            blocked_asgn = ShiftAssignment(shift=shift, employee=emp)
            blocked_asgn.clean()


@pytest.mark.django_db
class TestPhase4RoleScoping:
    def test_schedule_scoping_permissions(self):
        dept = Department.objects.create(name='HQ', code='HQ')
        ceo = User.objects.create(username='ceo_user', role=User.Role.CEO)
        mgr = User.objects.create(username='mgr_user', role=User.Role.MANAGER)
        other_mgr = User.objects.create(username='other_mgr', role=User.Role.MANAGER)
        emp_user = User.objects.create(username='emp_user', role=User.Role.EMPLOYEE)

        emp = Employee.objects.create(user=emp_user, name='Worker', department=dept, position='Tech')

        sched_draft = Schedule.objects.create(
            department=dept,
            title='Draft Sched',
            week_start_date=timezone.now().date(),
            status=Schedule.Status.DRAFT,
            created_by=mgr
        )

        # CEO can view and edit
        assert can_view_schedule(ceo, sched_draft) is True
        assert can_edit_schedule(ceo, sched_draft) is True

        # Creator manager can view and edit
        assert can_view_schedule(mgr, sched_draft) is True
        assert can_edit_schedule(mgr, sched_draft) is True

        # Employee cannot view draft schedule
        assert can_view_schedule(emp_user, sched_draft) is False
        assert can_edit_schedule(emp_user, sched_draft) is False

        # When published and employee is assigned
        shift = Shift.objects.create(
            schedule=sched_draft,
            role_title='Task',
            start_time=timezone.now(),
            end_time=timezone.now() + datetime.timedelta(hours=4)
        )
        ShiftAssignment.objects.create(shift=shift, employee=emp)
        sched_draft.status = Schedule.Status.PUBLISHED
        sched_draft.save()

        # Now employee can view published schedule they appear on, but cannot edit
        assert can_view_schedule(emp_user, sched_draft) is True
        assert can_edit_schedule(emp_user, sched_draft) is False


@pytest.mark.django_db
class TestPhase5PrioritySchedulerSolver:
    def test_cpsat_solver_constraints_and_objective(self):
        dept = Department.objects.create(name='Delivery', code='DEL')
        mgr = User.objects.create(username='dispatch', role=User.Role.MANAGER)

        # Create 4 employees
        # emp1 has high productivity (9.5)
        # emp2 has medium productivity (6.0)
        # emp3 has high productivity (9.0)
        # emp4 has low productivity (4.0)
        emp1 = Employee.objects.create(name='Fast Driver', department=dept, position='Driver', productivity_score=9.5, max_hours_per_week=40)
        emp2 = Employee.objects.create(name='Mid Driver', department=dept, position='Driver', productivity_score=6.0, max_hours_per_week=40)
        emp3 = Employee.objects.create(name='Lead Driver', department=dept, position='Driver', productivity_score=9.0, max_hours_per_week=40)
        emp4 = Employee.objects.create(name='Junior Driver', department=dept, position='Driver', productivity_score=4.0, max_hours_per_week=40)

        # Friction pair: emp1 and emp2 have high conflict (1.0/10)
        EmployeeCompatibility.objects.create(employee_a=emp1, employee_b=emp2, score=1.0)

        monday = timezone.now().date()
        sched = Schedule.objects.create(
            department=dept,
            title='Delivery Week',
            week_start_date=monday,
            created_by=mgr
        )

        # Shift 1: Needs 2 drivers
        shift1 = Shift.objects.create(
            schedule=sched,
            role_title='Morning Rush',
            start_time=timezone.make_aware(datetime.datetime.combine(monday, datetime.time(8, 0))),
            end_time=timezone.make_aware(datetime.datetime.combine(monday, datetime.time(16, 0))),
            headcount_needed=2
        )

        # emp2 has approved time-off on Monday! -> Hard constraint test
        TimeOffRequest.objects.create(
            employee=emp2,
            start_date=monday,
            end_date=monday,
            status=TimeOffRequest.Status.APPROVED,
            reviewed_by=mgr
        )

        # Run CP-SAT solver
        scheduler = PriorityScheduler(sched)
        result = scheduler.solve()

        assert result['success'] is True
        assert result['status'] in ('OPTIMAL', 'FEASIBLE')

        assigned_emp_ids = [a['employee_id'] for a in result['assignments']]
        assert len(assigned_emp_ids) == 2

        # emp2 MUST NOT be assigned because of approved time off (Hard Constraint 2)
        assert emp2.id not in assigned_emp_ids

        # Both assigned drivers should be valid
        assigned_names = [a['employee'].name for a in result['assignments']]
        assert 'Fast Driver' in assigned_names or 'Lead Driver' in assigned_names

        # Commit solution to database
        applied = scheduler.apply_solution(result['assignments'], user=mgr)
        assert len(applied) == 2
        for asgn in applied:
            assert asgn.is_auto_scheduled is True
            assert asgn.shift == shift1
