# pyright: reportAttributeAccessIssue=false
import datetime
from decimal import Decimal

from django.utils import timezone

from .models import (AvailabilitySlot, CompatibilityGroup, Schedule, Shift, TimeOffRequest)
from .tests_roles import RoleBase, person
from .tests_shifts import make_shift, put

MONDAY = timezone.localdate() + datetime.timedelta(days=28)
MONDAY -= datetime.timedelta(days=MONDAY.weekday())
URL = '/api/shifts/auto-schedule/'


class Base(RoleBase):
    def setUp(self):
        super().setUp()
        # managers can be scheduled too; keep Carol (she manages Eng) out of Eng's pool so these tests stay simple
        self.carol.department = self.mkt; self.carol.save()
        # Alice (best), Dan, Eve in Eng
        self.alice.productivity_score = Decimal('9.0'); self.alice.save()
        self.dan = person(self.company, self.eng, 'employee', 'dan@x.com', 'Dan', 'E')
        self.dan.productivity_score = Decimal('7.0'); self.dan.save()
        self.eve = person(self.company, self.eng, 'employee', 'eve@x.com', 'Eve', 'E')
        self.eve.productivity_score = Decimal('5.0'); self.eve.save()

    def day(self, n):
        return MONDAY + datetime.timedelta(days=n)

    def run_auto(self, client=None, **kw):
        body = {'department': self.eng.id, 'date_from': MONDAY.isoformat(),
                'date_to': (MONDAY + datetime.timedelta(days=6)).isoformat(), **kw}
        return (client or self.c_ceo).post(URL, body, format='json')

    def who(self, shift):
        return sorted(a.employee_id for a in shift.assignments.all())

    def group(self, people, score):
        g = CompatibilityGroup.objects.create(company=self.company, score=score)
        g.members.set(people)


class AgeAndEmploymentTests(Base):
    def test_age_and_minor_flag(self):
        from .scheduling import age_on
        self.assertEqual(age_on(datetime.date(2000, 5, 10), datetime.date(2018, 5, 9)), 17)
        self.assertEqual(age_on(datetime.date(2000, 5, 10), datetime.date(2018, 5, 10)), 18)
        today = datetime.date.today()
        self.eve.user.date_of_birth = today.replace(year=today.year - 17)
        self.eve.user.save()
        shift = make_shift(self.eng, day=self.day(0))
        put(shift, self.eve); put(shift, self.dan)
        data = {a['name']: a['is_minor'] for a in self.c_alice.get(f'/api/shifts/?department={self.eng.id}').data[0]['assignments']}
        self.assertEqual(data, {'Eve E': True, 'Dan E': False})

    def test_employee_fields_and_editing(self):
        r = self.c_carol.patch(f'/api/employees/{self.dan.id}/', {'employment_type': 'part_time'}, format='json')
        self.assertEqual((r.status_code, r.data['employment_type'], r.data['allow_overtime']), (200, 'part_time', False))
        r = self.c_carol.patch(f'/api/employees/{self.dan.id}/', {'allow_overtime': True}, format='json')
        self.assertEqual(r.status_code, 400)  # part time cannot have overtime
        r = self.c_carol.patch(f'/api/employees/{self.dan.id}/', {'employment_type': 'full_time', 'allow_overtime': True}, format='json')
        self.assertEqual((r.status_code, r.data['allow_overtime']), (200, True))
        r = self.c_carol.patch(f'/api/employees/{self.dan.id}/', {'employment_type': 'part_time'}, format='json')
        self.assertFalse(r.data['allow_overtime'])  # going part time clears overtime
        self.assertEqual(self.c_carol.patch(f'/api/employees/{self.dan.id}/', {'employment_type': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.c_alice.patch(f'/api/employees/{self.dan.id}/', {'employment_type': 'part_time'}, format='json').status_code, 403)

    def test_roster_birth_date(self):
        r = self.c_carol.post('/api/employees/', {'first_name': 'Kid', 'last_name': 'R', 'department': self.eng.id,
                                                  'employment_type': 'part_time', 'date_of_birth': '2030-01-01'}, format='json')
        self.assertEqual(r.status_code, 400)
        today = datetime.date.today()
        dob = today.replace(year=today.year - 16).isoformat()
        r = self.c_carol.post('/api/employees/', {'first_name': 'Kid', 'last_name': 'R', 'department': self.eng.id,
                                                  'employment_type': 'part_time', 'date_of_birth': dob}, format='json')
        self.assertEqual((r.status_code, r.data['is_minor'], r.data['age'], r.data['employment_type']), (201, True, 16, 'part_time'))
        # no birth date entered -> age unknown, not a minor
        r = self.c_carol.post('/api/employees/', {'first_name': 'Old', 'last_name': 'R', 'department': self.eng.id}, format='json')
        self.assertEqual((r.data['age'], r.data['is_minor'], r.data['employment_type']), (None, False, 'full_time'))
        # real accounts cannot have their birth date edited
        r = self.c_carol.patch(f'/api/employees/{self.dan.id}/', {'date_of_birth': dob}, format='json')
        self.assertEqual(r.status_code, 400)
        # roster birth date can be edited
        rid = self.c_carol.post('/api/employees/', {'first_name': 'Z', 'last_name': 'R', 'department': self.eng.id}, format='json').data['id']
        r = self.c_carol.patch(f'/api/employees/{rid}/', {'date_of_birth': dob}, format='json')
        self.assertEqual((r.status_code, r.data['is_minor']), (200, True))


class ManualWarningTests(Base):
    def test_full_time_over_40_needs_confirmation(self):
        for n in range(4):                      # 4 x 10h = 40h already
            put(make_shift(self.eng, '08:00', '18:00', 1, self.day(n)), self.dan)
        extra = make_shift(self.eng, '08:00', '12:00', 1, self.day(4))
        r = self.c_carol.post(f'/api/shifts/{extra.id}/assign/', {'employee': self.dan.id}, format='json')
        self.assertEqual((r.status_code, r.data['code']), (409, 'schedule_warning'))
        self.assertIn('44 hours', r.data['detail'])
        r = self.c_carol.post(f'/api/shifts/{extra.id}/assign/', {'employee': self.dan.id, 'confirm_warnings': True}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_overtime_allowed_has_no_warning(self):
        self.dan.allow_overtime = True; self.dan.save()
        for n in range(4):
            put(make_shift(self.eng, '08:00', '18:00', 1, self.day(n)), self.dan)
        extra = make_shift(self.eng, '08:00', '12:00', 1, self.day(4))
        self.assertEqual(self.c_carol.post(f'/api/shifts/{extra.id}/assign/', {'employee': self.dan.id}, format='json').status_code, 200)

    def test_part_time_limit_is_39(self):
        self.dan.employment_type = 'part_time'; self.dan.save()
        for n in range(3):
            put(make_shift(self.eng, '08:00', '18:00', 1, self.day(n)), self.dan)   # 30h
        ok = make_shift(self.eng, '08:00', '17:00', 1, self.day(3))                 # 39h
        self.assertEqual(self.c_carol.post(f'/api/shifts/{ok.id}/assign/', {'employee': self.dan.id}, format='json').status_code, 200)
        over = make_shift(self.eng, '08:00', '09:00', 1, self.day(4))               # 40h
        r = self.c_carol.post(f'/api/shifts/{over.id}/assign/', {'employee': self.dan.id}, format='json')
        self.assertEqual(r.status_code, 409)

    def test_minor_warnings(self):
        today = datetime.date.today()
        self.eve.user.date_of_birth = today.replace(year=today.year - 16); self.eve.user.save()
        late = make_shift(self.eng, '16:00', '21:30', 1, self.day(0))
        r = self.c_carol.post(f'/api/shifts/{late.id}/assign/', {'employee': self.eve.id}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertIn('under 18', r.data['detail']); self.assertIn('past 9 PM', r.data['detail'])
        long_ = make_shift(self.eng, '08:00', '17:00', 1, self.day(1))
        r = self.c_carol.post(f'/api/shifts/{long_.id}/assign/', {'employee': self.eve.id}, format='json')
        self.assertIn('more than 8 hours that day', r.data['detail'])
        fine = make_shift(self.eng, '10:00', '14:00', 1, self.day(2))
        self.assertEqual(self.c_carol.post(f'/api/shifts/{fine.id}/assign/', {'employee': self.eve.id}, format='json').status_code, 200)


class AutoScheduleTests(Base):
    def test_requires_staff_and_scope(self):
        self.assertEqual(self.run_auto(self.c_alice).status_code, 403)
        self.assertEqual(self.run_auto(self.c_bob).status_code, 403)   # Bob manages Marketing
        self.assertEqual(self.run_auto(self.c_carol).status_code, 200)

    def test_best_productivity_first_and_keeps_existing(self):
        s1 = make_shift(self.eng, '09:00', '13:00', 1, self.day(0))
        r = self.run_auto()
        self.assertEqual(r.data['created'], 1)
        self.assertEqual(self.who(s1), [self.alice.id])    # 9.0 beats 7.0 / 5.0
        # existing assignments stay; only open spots are filled
        s2 = make_shift(self.eng, '09:00', '13:00', 2, self.day(1))
        put(s2, self.eve)
        self.run_auto()
        self.assertEqual(self.who(s2), sorted([self.eve.id, self.alice.id]))
        self.assertEqual(self.run_auto().data['created'], 0)   # nothing left to fill (idempotent)

    def test_respects_time_off_availability_and_overlap(self):
        s = make_shift(self.eng, '09:00', '13:00', 3, self.day(0))
        TimeOffRequest.objects.create(employee=self.alice, start_date=self.day(0), end_date=self.day(0),
                                      status=TimeOffRequest.Status.APPROVED)
        self.dan.unavailable_days = [self.day(0).weekday()]; self.dan.save()   # Dan ticked "not available" that day
        self.run_auto()
        self.assertEqual(self.who(s), [self.eve.id])      # Alice off, Dan unavailable
        other = make_shift(self.eng, '10:00', '12:00', 1, self.day(0))
        self.run_auto()
        self.assertEqual(self.who(other), [])             # Eve is busy, Alice off, Dan unavailable

    def test_untouched_days_are_available_all_day(self):
        # Dan only entered Wednesday hours; every other day he never touched counts as available all day
        AvailabilitySlot.objects.create(employee=self.dan, day_of_week=2, start_time='09:00', end_time='17:00')
        self.alice.allow_overtime = False; self.alice.save()
        early = make_shift(self.eng, '09:00', '13:00', 3, self.day(0))
        TimeOffRequest.objects.create(employee=self.alice, start_date=self.day(0), end_date=self.day(0),
                                      status=TimeOffRequest.Status.APPROVED)
        self.run_auto()
        self.assertIn(self.dan.id, self.who(early))
        # a day with entered hours limits him to those hours
        wed = make_shift(self.eng, '06:00', '08:00', 1, self.day(2))
        self.dan.employment_type = 'full_time'; self.dan.save()
        self.run_auto()
        self.assertNotIn(self.dan.id, self.who(wed))

    def test_not_available_day_is_skipped(self):
        s = make_shift(self.eng, '09:00', '13:00', 1, self.day(1))
        for p in (self.alice, self.dan, self.eve):
            p.unavailable_days = [self.day(1).weekday()]; p.save()
        self.run_auto()
        self.assertEqual(self.who(s), [])

    def test_pending_time_off_popup_then_continue(self):
        make_shift(self.eng, day=self.day(1))
        TimeOffRequest.objects.create(employee=self.dan, start_date=self.day(2), end_date=self.day(2))
        r = self.run_auto()
        self.assertEqual((r.status_code, r.data['code'], r.data['count']), (409, 'pending_time_off', 1))
        self.assertEqual(Schedule.objects.count(), 0)
        self.assertEqual(self.run_auto(confirm_pending=True).status_code, 200)
        # pending request outside the week does not trigger the popup
        TimeOffRequest.objects.all().delete()
        TimeOffRequest.objects.create(employee=self.dan, start_date=self.day(20), end_date=self.day(20))
        self.assertEqual(self.run_auto().status_code, 200)

    def test_hour_caps(self):
        # five 10h shifts: Alice (full time) stops at 40h and Dan (part time target 24) takes the rest first
        shifts = [make_shift(self.eng, '08:00', '18:00', 1, self.day(n)) for n in range(5)]
        self.dan.employment_type = 'part_time'; self.dan.save()
        self.eve.employment_type = 'part_time'; self.eve.save()
        self.run_auto()
        from .scheduling import hours_in_week
        self.assertLessEqual(hours_in_week(self.alice, MONDAY), 40)
        self.assertLessEqual(hours_in_week(self.dan, MONDAY), 39)
        self.assertLessEqual(hours_in_week(self.eve, MONDAY), 39)
        self.assertTrue(all(s.assignments.count() == 1 for s in shifts))

    def test_overtime_only_as_last_resort(self):
        for n in range(6):
            make_shift(self.eng, '08:00', '18:00', 1, self.day(n % 7))
        # only Alice and she may not exceed 40h without overtime
        self.dan.delete(); self.eve.delete()
        self.run_auto()
        from .scheduling import hours_in_week
        self.assertEqual(hours_in_week(self.alice, MONDAY), 40)
        Schedule.objects.all().delete()
        self.alice.allow_overtime = True; self.alice.save()
        self.run_auto()
        self.assertEqual(hours_in_week(self.alice, MONDAY), 60)

    def test_minor_limits_are_never_broken(self):
        today = datetime.date.today()
        for p in (self.alice, self.dan):
            p.delete()
        self.eve.user.date_of_birth = today.replace(year=today.year - 15); self.eve.user.save()
        make_shift(self.eng, '08:00', '17:00', 1, self.day(0))      # 9h > 8h/day
        make_shift(self.eng, '17:00', '22:00', 1, self.day(1))      # past 9pm (and outside no-hours check)
        ok = make_shift(self.eng, '09:00', '13:00', 1, self.day(2))
        for n in range(3, 7):
            make_shift(self.eng, '09:00', '14:00', 1, self.day(n))  # 5h each: week cap 18h
        self.run_auto()
        from .scheduling import hours_in_week
        self.assertEqual(self.who(ok), [self.eve.id])
        self.assertLessEqual(hours_in_week(self.eve, MONDAY), 18)
        self.assertEqual(Shift.objects.get(shift_date=self.day(0)).assignments.count(), 0)
        self.assertEqual(Shift.objects.get(shift_date=self.day(1)).assignments.count(), 0)

    def test_compatibility_prefer_neutral_avoid(self):
        # Alice is placed first; Dan & Eve then choose between a shift with Alice and an empty one
        together = make_shift(self.eng, '09:00', '13:00', 2, self.day(0))
        apart = make_shift(self.eng, '14:00', '18:00', 2, self.day(0))
        put(together, self.alice)
        self.group([self.dan, self.alice], 9)      # prefer
        self.group([self.eve, self.alice], 2)      # avoid
        AvailabilitySlot.objects.create(employee=self.alice, day_of_week=0, start_time='09:00', end_time='13:00')  # keeps Alice off the second shift
        self.run_auto()
        self.assertIn(self.dan.id, self.who(together))
        self.assertNotIn(self.eve.id, self.who(together))   # Eve avoided Alice when other options existed
        self.assertIn(self.eve.id, self.who(apart))

    def test_avoided_pair_only_when_necessary(self):
        only = make_shift(self.eng, '09:00', '13:00', 2, self.day(0))
        put(only, self.alice)
        self.dan.delete()
        self.group([self.eve, self.alice], 1)
        r = self.run_auto()
        self.assertEqual(self.who(only), sorted([self.alice.id, self.eve.id]))   # no other option: allowed
        self.assertTrue(any('low compatibility' in n for n in r.data['notes']))

    def test_neutral_scores_are_okay_but_second_choice(self):
        a = make_shift(self.eng, '09:00', '13:00', 2, self.day(0))
        b = make_shift(self.eng, '14:00', '18:00', 1, self.day(0))
        put(a, self.alice)
        self.group([self.dan, self.alice], 5)       # okay together
        AvailabilitySlot.objects.create(employee=self.alice, day_of_week=0, start_time='09:00', end_time='13:00')
        self.eve.delete()
        # Dan is full time and can do only one of them if limited by availability: give him a single slot
        # covering both so he works both, but the empty shift (no neutral pairing) must be filled first.
        self.run_auto()
        order = [s.shift_id for s in Schedule.objects.filter(employee=self.dan).order_by('id')]
        self.assertEqual(order, [b.id, a.id])

    def test_notes_for_part_time_below_minimum(self):
        self.dan.employment_type = 'part_time'; self.dan.save()
        make_shift(self.eng, '09:00', '10:00', 1, self.day(0))
        r = self.run_auto()
        self.assertTrue(any('Dan E (part time)' in n for n in r.data['notes']))


class NotAvailableDaysTests(Base):
    def test_employee_sets_own_days(self):
        r = self.c_alice.get('/api/availability/days/')
        self.assertEqual((r.status_code, r.data['unavailable_days']), (200, []))
        r = self.c_alice.put('/api/availability/days/', {'unavailable_days': [6, 0, 6]}, format='json')
        self.assertEqual((r.status_code, r.data['unavailable_days']), (200, [0, 6]))
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.unavailable_days, [0, 6])
        self.assertEqual(self.c_alice.get('/api/me/').data['profile']['unavailable_days'], [0, 6])
        r = self.c_alice.put('/api/availability/days/', {'unavailable_days': []}, format='json')
        self.assertEqual(r.data['unavailable_days'], [])

    def test_bad_values_rejected(self):
        for bad in ([7], [-1], ['1'], [True], 'monday', None):
            r = self.c_alice.put('/api/availability/days/', {'unavailable_days': bad}, format='json')
            self.assertEqual(r.status_code, 400, bad)

    def test_only_own_or_managed(self):
        # Carol manages Engineering, where Alice works; Dana (employee) cannot touch Alice's days
        r = self.c_carol.put('/api/availability/days/', {'employee': self.alice.id, 'unavailable_days': [1]}, format='json')
        self.assertEqual(r.status_code, 200)
        r = self.c_alice.put('/api/availability/days/', {'employee': self.eve.id, 'unavailable_days': [1]}, format='json')
        self.assertEqual(r.status_code, 403)
