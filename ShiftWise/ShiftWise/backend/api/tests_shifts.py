# pyright: reportAttributeAccessIssue=false
import datetime

from django.utils import timezone

from .models import (AvailabilitySlot, Notification, Schedule, SchedulePublication, Shift, ShiftRequest, ShiftTemplate, TimeOffRequest)
from .tests_roles import RoleBase, as_user, person

DAY = timezone.localdate() + datetime.timedelta(days=14)


def make_shift(department, start='09:00', end='13:00', headcount=2, day=DAY, name='Morning', posted=True):
    """A shift. Its week is posted by default so employees can see it; pass posted=False for a draft week."""
    shift = Shift.objects.create(department=department, name=name, shift_date=day, start_time=start,
                                 end_time=end, headcount=headcount)
    if posted:
        SchedulePublication.objects.get_or_create(department=department, week_start=shift.week_start)
    return shift


def put(shift, profile):
    return Schedule.objects.create(task_name=shift.name or 'Shift', employee=profile, shift_date=shift.shift_date,
                                   start_time=shift.start_time, end_time=shift.end_time, shift=shift)


class HoursTests(RoleBase):
    def test_everyone_reads_only_ceo_writes(self):
        r = self.c_alice.get('/api/company/')
        self.assertEqual((r.status_code, r.data['open_time'], r.data['close_time']), (200, '08:00', '18:00'))
        body = {'open_time': '07:00', 'close_time': '20:00'}
        self.assertEqual(self.c_carol.patch('/api/company/', body, format='json').status_code, 403)
        r = self.c_ceo.patch('/api/company/', body, format='json')
        self.assertEqual((r.status_code, r.data['open_time']), (200, '07:00'))
        self.assertEqual(self.c_alice.get('/api/me/').data['profile']['company']['close_time'], '20:00')

    def test_validation(self):
        r = self.c_ceo.patch('/api/company/', {'open_time': '18:00', 'close_time': '08:00'}, format='json')
        self.assertEqual(r.status_code, 400)
        make_shift(self.eng, '08:00', '17:00')
        r = self.c_ceo.patch('/api/company/', {'open_time': '09:00', 'close_time': '18:00'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('outside', str(r.data))


class TemplateTests(RoleBase):
    body = {'name': 'Morning', 'start_time': '08:00', 'end_time': '12:00', 'headcount': 2}

    def test_staff_create_employee_cannot(self):
        r = self.c_carol.post('/api/shift-templates/', self.body, format='json')
        self.assertEqual((r.status_code, r.data['headcount']), (201, 2))
        self.assertEqual(self.c_alice.post('/api/shift-templates/', self.body, format='json').status_code, 403)
        self.assertEqual(self.c_alice.get('/api/shift-templates/').status_code, 403)
        self.assertEqual(len(self.c_bob.get('/api/shift-templates/').data), 1)  # shared across the company

    def test_validation(self):
        for bad in ({**self.body, 'start_time': '06:00'}, {**self.body, 'end_time': '19:00'},
                    {**self.body, 'end_time': '07:00'}, {**self.body, 'headcount': 0}, {**self.body, 'name': ' '}):
            self.assertEqual(self.c_ceo.post('/api/shift-templates/', bad, format='json').status_code, 400, bad)

    def test_delete_rules(self):
        t = self.c_carol.post('/api/shift-templates/', self.body, format='json').data['id']
        self.assertEqual(self.c_bob.delete(f'/api/shift-templates/{t}/').status_code, 403)
        self.assertEqual(self.c_ceo.delete(f'/api/shift-templates/{t}/').status_code, 204)


class ShiftTests(RoleBase):
    def body(self, **kw):
        data = {'department': self.eng.pk, 'name': 'Morning', 'shift_date': DAY.isoformat(),
                'start_time': '09:00', 'end_time': '13:00', 'headcount': 3}
        data.update(kw)
        return data

    def test_manager_creates_in_scope_only(self):
        r = self.c_carol.post('/api/shifts/', self.body(), format='json')
        self.assertEqual((r.status_code, r.data['headcount'], r.data['open_count']), (201, 3, 3))
        self.assertEqual(self.c_carol.post('/api/shifts/', self.body(department=self.mkt.pk), format='json').status_code, 403)
        self.assertEqual(self.c_alice.post('/api/shifts/', self.body(), format='json').status_code, 403)
        self.assertEqual(self.c_ceo.post('/api/shifts/', self.body(department=self.mkt.pk), format='json').status_code, 201)

    def test_must_fit_hours(self):
        for bad in ({'end_time': '08:30', 'start_time': '09:00'}, {'headcount': 0}):
            self.assertEqual(self.c_ceo.post('/api/shifts/', self.body(**bad), format='json').status_code, 400, bad)

    def test_outside_hours_needs_confirmation(self):
        for early in ({'start_time': '07:00'}, {'end_time': '19:00'}):
            r = self.c_ceo.post('/api/shifts/', self.body(**early), format='json')
            self.assertEqual((r.status_code, r.data['code']), (409, 'outside_hours'), early)
        self.assertEqual(Shift.objects.count(), 0)
        r = self.c_ceo.post('/api/shifts/', self.body(start_time='07:00', allow_outside_hours=True), format='json')
        self.assertEqual((r.status_code, r.data['outside_hours']), (201, True))
        # a normal shift is not flagged
        self.assertFalse(self.c_ceo.post('/api/shifts/', self.body(), format='json').data['outside_hours'])
        # editing a shift out of hours asks again, and confirming flags it
        s = make_shift(self.eng)
        self.assertEqual(self.c_ceo.patch(f'/api/shifts/{s.pk}/', {'end_time': '20:00'}, format='json').status_code, 409)
        r = self.c_ceo.patch(f'/api/shifts/{s.pk}/', {'end_time': '20:00', 'allow_outside_hours': True}, format='json')
        self.assertEqual((r.status_code, r.data['outside_hours']), (200, True))
        # staff can add people to it; employees still cannot create shifts
        self.assertEqual(self.c_alice.post('/api/shifts/', self.body(start_time='07:00', allow_outside_hours=True),
                                           format='json').status_code, 403)

    def test_outside_hours_shift_does_not_block_changing_hours(self):
        self.c_ceo.post('/api/shifts/', self.body(start_time='07:00', allow_outside_hours=True), format='json')
        r = self.c_ceo.patch('/api/company/', {'open_time': '08:00', 'close_time': '19:00'}, format='json')
        self.assertEqual(r.status_code, 200)

    def test_visibility(self):
        mine, theirs = make_shift(self.eng), make_shift(self.mkt)
        self.assertEqual([s['id'] for s in self.c_alice.get('/api/shifts/').data], [mine.pk])
        # managers can look at every department (Carol runs Eng, Bob runs Mkt) but employees only their own
        self.assertEqual({s['id'] for s in self.c_carol.get('/api/shifts/').data}, {mine.pk, theirs.pk})
        self.assertEqual({s['id'] for s in self.c_bob.get('/api/shifts/').data}, {mine.pk, theirs.pk})
        self.assertEqual([s['id'] for s in self.c_gus.get('/api/shifts/').data], [theirs.pk])
        self.assertEqual({s['id'] for s in self.c_ceo.get('/api/shifts/').data}, {mine.pk, theirs.pk})
        r = self.c_ceo.get('/api/shifts/', {'department': self.mkt.pk, 'date_from': DAY.isoformat(),
                                            'date_to': DAY.isoformat()})
        self.assertEqual([s['id'] for s in r.data], [theirs.pk])
        self.assertEqual(self.c_ceo.get('/api/shifts/', {'date_from': 'nope'}).status_code, 400)

    def test_assign_and_unassign_show_names(self):
        shift = make_shift(self.eng, headcount=2)
        r = self.c_carol.post(f'/api/shifts/{shift.pk}/assign/', {'employee': self.alice.pk}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([a['name'] for a in r.data['assignments']], ['Alice E'])
        self.assertEqual(r.data['open_count'], 1)
        self.assertEqual(Schedule.objects.filter(shift=shift).count(), 1)
        aid = r.data['assignments'][0]['id']
        r = self.c_alice.get('/api/shifts/')
        self.assertEqual(r.data[0]['assignments'][0]['name'], 'Alice E')  # employees see names too
        self.assertEqual(self.c_alice.post(f'/api/shifts/{shift.pk}/unassign/', {'assignment': aid},
                                           format='json').status_code, 403)
        r = self.c_carol.post(f'/api/shifts/{shift.pk}/unassign/', {'assignment': aid}, format='json')
        self.assertEqual(r.data['open_count'], 2)

    def test_assign_rules(self):
        shift = make_shift(self.eng, headcount=1)
        url = f'/api/shifts/{shift.pk}/assign/'
        self.assertEqual(self.c_carol.post(url, {'employee': self.gus.pk}, format='json').status_code, 400)  # other dept
        self.assertEqual(self.c_bob.post(url, {'employee': self.alice.pk}, format='json').status_code, 403)  # can see it, doesn't run it
        self.assertEqual(self.c_carol.post(url, {'employee': self.alice.pk}, format='json').status_code, 200)
        self.assertEqual(self.c_carol.post(url, {'employee': self.alice.pk}, format='json').status_code, 400)  # again
        other = person(self.company, self.eng, 'employee', 'zed@x.com')
        r = self.c_carol.post(url, {'employee': other.pk}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('full', str(r.data))

    def test_overlap_blocked(self):
        a, b = make_shift(self.eng), make_shift(self.eng, '12:00', '15:00', name='Mid')
        self.c_carol.post(f'/api/shifts/{a.pk}/assign/', {'employee': self.alice.pk}, format='json')
        r = self.c_carol.post(f'/api/shifts/{b.pk}/assign/', {'employee': self.alice.pk}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('already works', str(r.data))

    def test_approved_time_off_warns_then_confirms(self):
        TimeOffRequest.objects.create(employee=self.alice, start_date=DAY, end_date=DAY, status='approved')
        TimeOffRequest.objects.create(employee=self.alice, start_date=DAY + datetime.timedelta(days=3),
                                      end_date=DAY + datetime.timedelta(days=3), status='pending')
        shift = make_shift(self.eng)
        url = f'/api/shifts/{shift.pk}/assign/'
        r = self.c_carol.post(url, {'employee': self.alice.pk}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'time_off_approved')
        self.assertEqual(r.data['detail'], "Alice E's request off was approved, are you sure you would like to schedule them?")
        self.assertFalse(Schedule.objects.filter(shift=shift).exists())
        r = self.c_carol.post(url, {'employee': self.alice.pk, 'confirm_time_off': True}, format='json')
        self.assertEqual(r.status_code, 200)
        # a pending (not approved) request does not warn
        later = make_shift(self.eng, day=DAY + datetime.timedelta(days=3))
        self.assertEqual(self.c_carol.post(f'/api/shifts/{later.pk}/assign/', {'employee': self.alice.pk},
                                           format='json').status_code, 200)

    def test_edit_shift(self):
        shift = make_shift(self.eng, headcount=2)
        put(shift, self.alice)
        put(shift, person(self.company, self.eng, 'employee', 'z@x.com'))
        url = f'/api/shifts/{shift.pk}/'
        r = self.c_carol.patch(url, {'headcount': 1}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.c_carol.patch(url, {'headcount': 4, 'start_time': '10:00', 'end_time': '14:00'}, format='json')
        self.assertEqual((r.status_code, r.data['open_count']), (200, 2))
        self.assertEqual(set(Schedule.objects.filter(shift=shift).values_list('start_time', flat=True)),
                         {datetime.time(10, 0)})
        self.assertEqual(self.c_alice.patch(url, {'headcount': 5}, format='json').status_code, 403)
        self.assertEqual(self.c_bob.patch(url, {'headcount': 5}, format='json').status_code, 403)

    def test_delete_shift_removes_assignments(self):
        shift = make_shift(self.eng)
        put(shift, self.alice)
        self.assertEqual(self.c_carol.delete(f'/api/shifts/{shift.pk}/').status_code, 204)
        self.assertFalse(Schedule.objects.filter(employee=self.alice).exists())

    def test_apply_template(self):
        t = ShiftTemplate.objects.create(company=self.company, name='Morning', start_time='08:00', end_time='12:00',
                                         headcount=2)
        days = [(DAY + datetime.timedelta(days=i)).isoformat() for i in range(3)]
        body = {'template': t.pk, 'department': self.eng.pk, 'dates': days}
        r = self.c_carol.post('/api/shifts/apply-template/', body, format='json')
        self.assertEqual((r.status_code, r.data), (201, {'created': 3, 'skipped': 0}))
        self.assertEqual(Shift.objects.filter(department=self.eng, headcount=2).count(), 3)
        r = self.c_carol.post('/api/shifts/apply-template/', body, format='json')
        self.assertEqual(r.data, {'created': 0, 'skipped': 3})
        self.assertEqual(self.c_carol.post('/api/shifts/apply-template/', {**body, 'department': self.mkt.pk},
                                           format='json').status_code, 403)
        self.assertEqual(self.c_carol.post('/api/shifts/apply-template/', {**body, 'dates': []},
                                           format='json').status_code, 400)
        self.assertEqual(self.c_alice.post('/api/shifts/apply-template/', body, format='json').status_code, 403)

    def test_transfer_drops_future_shifts_of_old_department(self):
        shift = make_shift(self.eng)
        put(shift, self.alice)
        self.c_ceo.post(f'/api/employees/{self.alice.pk}/transfer/', {'department': self.mkt.pk}, format='json')
        self.assertFalse(Schedule.objects.filter(employee=self.alice, shift__isnull=False).exists())


class ShiftRequestTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.dana = person(self.company, self.eng, 'employee', 'dana@x.com', 'Dana', 'D')
        self.c_dana = as_user(self.dana)
        self.s1 = make_shift(self.eng, '09:00', '13:00', 2)
        self.s2 = make_shift(self.eng, '14:00', '18:00', 2, name='Afternoon')
        self.mine = put(self.s1, self.alice)      # Alice, morning
        self.theirs = put(self.s2, self.dana)     # Dana, afternoon

    def ask(self, client, **body):
        return client.post('/api/shift-requests/', body, format='json')

    def test_give_away_accepted(self):
        r = self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk)
        self.assertEqual(r.status_code, 201, r.data)
        note = Notification.objects.get(recipient=self.dana.user, kind='shift_request')
        self.assertIn('asked you to take their shift', note.message)
        inbox = self.c_dana.get('/api/notifications/').data
        self.assertEqual(inbox[0]['shift_request']['kind'], 'give')
        sr = r.data['id']
        self.assertEqual(self.c_alice.post(f'/api/shift-requests/{sr}/accept/').status_code, 403)  # only the target
        r = self.c_dana.post(f'/api/shift-requests/{sr}/accept/')
        self.assertEqual(r.status_code, 200, r.data)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.employee, self.dana)
        self.assertTrue(Notification.objects.filter(recipient=self.alice.user, kind='info', message__contains='accepted').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.carol.user, kind='info', message__contains='gave').exists())
        self.assertEqual(self.c_dana.post(f'/api/shift-requests/{sr}/accept/').status_code, 400)  # only once

    def test_take_someones_shift(self):
        r = self.ask(self.c_alice, kind='take', schedule=self.theirs.pk)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['target']['name'], 'Dana D')
        self.c_dana.post(f"/api/shift-requests/{r.data['id']}/accept/")
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.employee, self.alice)

    def test_swap(self):
        r = self.ask(self.c_alice, kind='swap', schedule=self.mine.pk, other_schedule=self.theirs.pk)
        self.assertEqual(r.status_code, 201, r.data)
        self.c_dana.post(f"/api/shift-requests/{r.data['id']}/accept/")
        self.mine.refresh_from_db(), self.theirs.refresh_from_db()
        self.assertEqual((self.mine.employee, self.theirs.employee), (self.dana, self.alice))

    def test_decline_and_cancel(self):
        r = self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk)
        sr = r.data['id']
        self.assertEqual(self.c_dana.post(f'/api/shift-requests/{sr}/decline/').status_code, 200)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.employee, self.alice)
        self.assertTrue(Notification.objects.filter(recipient=self.alice.user, message__contains='declined').exists())
        r = self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk)
        self.assertEqual(self.c_dana.post(f"/api/shift-requests/{r.data['id']}/cancel/").status_code, 403)
        self.assertEqual(self.c_alice.post(f"/api/shift-requests/{r.data['id']}/cancel/").status_code, 200)

    def test_rules(self):
        # can't give away someone else's shift, or ask a person in another department
        self.assertEqual(self.ask(self.c_alice, kind='give', schedule=self.theirs.pk, to_employee=self.dana.pk).status_code, 400)
        self.assertEqual(self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.gus.pk).status_code, 400)
        self.assertEqual(self.ask(self.c_alice, kind='take', schedule=self.mine.pk).status_code, 400)
        self.assertEqual(self.ask(self.c_alice, kind='nope', schedule=self.mine.pk).status_code, 400)
        # a pending request blocks a second one
        self.assertEqual(self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk).status_code, 201)
        self.assertEqual(self.ask(self.c_dana, kind='take', schedule=self.mine.pk).status_code, 400)
        # a shift in the past can't be requested
        old = make_shift(self.eng, day=timezone.localdate() - datetime.timedelta(days=2))
        past = put(old, self.alice)
        self.assertEqual(self.ask(self.c_alice, kind='give', schedule=past.pk, to_employee=self.dana.pk).status_code, 400)

    def test_roster_person_cannot_be_asked(self):
        roster = person(self.company, self.eng, 'employee', 'roster.abc@roster.invalid')
        roster.user.set_unusable_password()
        roster.user.save()
        r = self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=roster.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('no login', str(r.data))

    def test_conflicts_are_checked(self):
        # Dana already works 09:00-13:00 on another... same day overlap
        clash = make_shift(self.eng, '10:00', '12:00', 1, name='Clash')
        put(clash, self.dana)
        r = self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('already works', str(r.data))
        clash.delete()
        TimeOffRequest.objects.create(employee=self.dana, start_date=DAY, end_date=DAY, status='approved')
        r = self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn('approved time off', str(r.data))

    def test_stale_request_is_cancelled(self):
        r = self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk)
        Schedule.objects.filter(pk=self.mine.pk).update(employee=self.carol)  # a manager reassigned it
        resp = self.c_dana.post(f"/api/shift-requests/{r.data['id']}/accept/")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(ShiftRequest.objects.get(pk=r.data['id']).status, 'cancelled')

    def test_list_shows_mine_only(self):
        self.ask(self.c_alice, kind='give', schedule=self.mine.pk, to_employee=self.dana.pk)
        self.assertEqual(len(self.c_alice.get('/api/shift-requests/').data), 1)
        self.assertEqual(len(self.c_dana.get('/api/shift-requests/').data), 1)
        self.assertEqual(len(self.c_gus.get('/api/shift-requests/').data), 0)

    def test_coworkers_list(self):
        names = [c['name'] for c in self.c_alice.get('/api/coworkers/').data]
        self.assertEqual(sorted(names), ['Carol M', 'Cee Oh', 'Dana D'])  # same department, not me, not other departments


class ShiftNoteTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.dana = person(self.company, self.eng, 'employee', 'dana@x.com', 'Dana', 'D')
        self.c_dana = as_user(self.dana)
        self.shift = make_shift(self.eng, '09:00', '13:00', 3)

    def assign(self, client, who, **extra):
        return client.post(f'/api/shifts/{self.shift.pk}/assign/', {'employee': who.pk, **extra}, format='json')

    def note_of(self, client, who):
        shifts = client.get('/api/shifts/').data
        return next(a['note'] for a in shifts[0]['assignments'] if a['employee_id'] == who.pk)

    def test_note_is_optional_and_saved_on_assign(self):
        self.assertEqual(self.assign(self.c_carol, self.alice).status_code, 200)
        self.assertEqual(self.note_of(self.c_carol, self.alice), '')
        r = self.assign(self.c_carol, self.dana, note='  Restock the front shelves  ')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.note_of(self.c_carol, self.dana), 'Restock the front shelves')

    def test_edit_and_clear_note_later(self):
        self.assign(self.c_carol, self.alice)
        a = Schedule.objects.get(shift=self.shift, employee=self.alice)
        url = f'/api/shifts/{self.shift.pk}/note/'
        r = self.c_carol.post(url, {'assignment': a.pk, 'note': 'Open the register'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.note_of(self.c_ceo, self.alice), 'Open the register')
        self.c_ceo.post(url, {'assignment': a.pk, 'note': ''}, format='json')
        self.assertEqual(self.note_of(self.c_carol, self.alice), '')

    def test_only_managers_of_the_department_can_write(self):
        self.assign(self.c_carol, self.alice)
        a = Schedule.objects.get(shift=self.shift, employee=self.alice)
        url = f'/api/shifts/{self.shift.pk}/note/'
        self.assertEqual(self.c_alice.post(url, {'assignment': a.pk, 'note': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.c_bob.post(url, {'assignment': a.pk, 'note': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.assign(self.c_alice, self.dana, note='x').status_code, 403)

    def test_too_long_or_wrong_type(self):
        self.assertEqual(self.assign(self.c_carol, self.alice, note='x' * 501).status_code, 400)
        self.assertEqual(self.assign(self.c_carol, self.alice, note=['no']).status_code, 400)
        self.assertEqual(Schedule.objects.filter(shift=self.shift).count(), 0)
        self.assertEqual(self.assign(self.c_carol, self.alice, note='x' * 500).status_code, 200)

    def test_only_the_person_and_their_managers_see_it(self):
        self.assign(self.c_carol, self.alice, note='Deep clean the grill')
        self.assign(self.c_carol, self.dana)
        self.assertEqual(self.note_of(self.c_alice, self.alice), 'Deep clean the grill')
        self.assertEqual(self.note_of(self.c_carol, self.alice), 'Deep clean the grill')
        self.assertEqual(self.note_of(self.c_ceo, self.alice), 'Deep clean the grill')
        self.assertEqual(self.note_of(self.c_dana, self.alice), '')          # coworker
        self.assertEqual(self.note_of(self.c_dana, self.dana), '')
        # the plain schedules endpoint must not leak it either
        rows = self.c_dana.get('/api/schedules/').data
        rows = rows['results'] if isinstance(rows, dict) else rows
        self.assertTrue(all(r['notes'] == '' for r in rows if r['employee'] == self.alice.pk))
        rows = self.c_alice.get('/api/schedules/').data
        rows = rows['results'] if isinstance(rows, dict) else rows
        self.assertIn('Deep clean the grill', [r['notes'] for r in rows])

    def test_note_clears_when_the_shift_changes_hands(self):
        self.assign(self.c_carol, self.alice, note='Close the store')
        sr = self.c_alice.post('/api/shift-requests/', {'kind': 'give', 'schedule': Schedule.objects.get(
            shift=self.shift, employee=self.alice).pk, 'to_employee': self.dana.pk}, format='json')
        self.assertEqual(sr.status_code, 201, sr.data)
        self.assertEqual(self.c_dana.post(f'/api/shift-requests/{sr.data["id"]}/accept/').status_code, 200)
        self.assertEqual(self.note_of(self.c_carol, self.dana), '')


class ManagerSeesEverythingTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.shift = make_shift(self.mkt, '09:00', '13:00', 2)
        self.on = put(self.shift, self.gus)
        self.on.notes = 'Count the till'
        self.on.save()

    def test_other_department_is_visible_with_people_but_notes_stay_private(self):
        r = self.c_carol.get('/api/shifts/', {'department': self.mkt.pk})
        self.assertEqual([s['id'] for s in r.data], [self.shift.pk])
        person = r.data[0]['assignments'][0]
        self.assertEqual((person['name'], person['note']), ('Gus E', ''))      # Carol does not run Mkt
        self.assertEqual(self.c_bob.get('/api/shifts/').data[0]['assignments'][0]['note'], 'Count the till')

    def test_but_cannot_change_a_department_they_do_not_run(self):
        url = f'/api/shifts/{self.shift.pk}/'
        self.assertEqual(self.c_carol.patch(url, {'headcount': 5}, format='json').status_code, 403)
        self.assertEqual(self.c_carol.delete(url).status_code, 403)
        r = self.c_carol.post(f'{url}assign/', {'employee': self.alice.pk}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.c_carol.post('/api/shifts/', {'department': self.mkt.pk, 'name': 'x', 'shift_date': DAY.isoformat(),
                                                            'start_time': '09:00', 'end_time': '10:00', 'headcount': 1},
                                           format='json').status_code, 403)
        self.assertEqual(self.c_carol.post('/api/shifts/auto-schedule/', {'department': self.mkt.pk, 'date_from': DAY.isoformat(),
                                                                          'date_to': DAY.isoformat()}, format='json').status_code, 403)
        # a manager who is given a second department can then change it
        self.carol.managed_departments.add(self.mkt)
        self.assertEqual(self.c_carol.patch(url, {'headcount': 5}, format='json').status_code, 200)


class PostingTests(RoleBase):
    """A department's week is a draft until a manager reviews and posts it."""

    def setUp(self):
        super().setUp()
        self.shift = make_shift(self.eng, '09:00', '13:00', 2, posted=False)
        self.on = put(self.shift, self.alice)
        self.week = self.shift.week_start.isoformat()
        self.body = {'department': self.eng.pk, 'week_start': self.week}

    def post(self, client, **extra):
        return client.post('/api/shifts/publish/', {**self.body, 'reviewed': True, 'confirmed': True, **extra}, format='json')

    def test_draft_is_hidden_from_employees_but_not_managers(self):
        self.assertEqual(self.c_alice.get('/api/shifts/').data, [])
        self.assertEqual(list(self.c_alice.get('/api/schedules/').data), [])
        self.assertEqual([s['id'] for s in self.c_carol.get('/api/shifts/').data], [self.shift.pk])
        self.assertEqual([s['id'] for s in self.c_ceo.get('/api/shifts/').data], [self.shift.pk])
        self.assertFalse(self.c_alice.get('/api/shifts/publication/', self.body).data['published'])

    def test_employee_cannot_post_or_review(self):
        self.assertEqual(self.post(self.c_alice).status_code, 403)
        self.assertEqual(self.c_alice.get('/api/shifts/review/', self.body).status_code, 403)

    def test_only_managers_of_that_department_can_post(self):
        self.assertEqual(self.post(self.c_bob).status_code, 403)
        self.assertFalse(SchedulePublication.objects.exists())

    def test_posting_needs_review_and_confirmation(self):
        r = self.c_carol.post('/api/shifts/publish/', self.body, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.c_carol.post('/api/shifts/publish/', {**self.body, 'reviewed': True}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.c_carol.post('/api/shifts/publish/', {**self.body, 'confirmed': True}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.c_carol.post('/api/shifts/publish/', {**self.body, 'reviewed': 'yes', 'confirmed': 'yes'}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertFalse(SchedulePublication.objects.exists())

    def test_cannot_post_an_empty_week(self):
        r = self.post(self.c_carol, week_start=(DAY + datetime.timedelta(days=21)).isoformat())
        self.assertEqual(r.status_code, 400)
        self.assertIn('nothing to post', r.data['detail'].lower())

    def test_review_summarises_the_week(self):
        make_shift(self.eng, '14:00', '18:00', 1, name='Afternoon', posted=False)  # nobody on it
        data = self.c_carol.get('/api/shifts/review/', self.body).data
        self.assertEqual((data['shift_count'], data['slots'], data['filled'], data['open_slots']), (2, 3, 1, 2))
        self.assertEqual(len(data['open_shifts']), 2)
        self.assertEqual(data['people'], [{'name': 'Alice E', 'hours': 4.0, 'shifts': 1}])
        self.assertFalse(data['published'])

    def test_review_warns_about_time_off_and_outside_hours(self):
        TimeOffRequest.objects.create(employee=self.alice, start_date=DAY, end_date=DAY, status='approved')
        TimeOffRequest.objects.create(employee=self.alice, start_date=DAY + datetime.timedelta(days=1),
                                      end_date=DAY + datetime.timedelta(days=1), status='pending')
        self.shift.outside_hours = True
        self.shift.save()
        warnings = ' '.join(self.c_carol.get('/api/shifts/review/', self.body).data['warnings'])
        self.assertIn('approved time off', warnings)
        self.assertIn('outside the hours of operation', warnings)

    def test_posting_shows_the_week_and_tells_the_people_on_it(self):
        r = self.post(self.c_carol)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data['published'])
        self.assertEqual([s['id'] for s in self.c_alice.get('/api/shifts/').data], [self.shift.pk])
        self.assertTrue(self.c_alice.get('/api/shifts/publication/', self.body).data['published'])
        note = Notification.objects.get(recipient=self.alice.user)
        self.assertIn('was posted', note.message)
        self.assertFalse(Notification.objects.filter(recipient=self.gus.user).exists())  # other department
        self.assertEqual(self.post(self.c_carol).status_code, 400)  # only once

    def test_general_manager_can_post_any_department(self):
        self.assertEqual(self.post(self.c_ceo).status_code, 201)

    def test_drafts_stay_hidden_for_other_weeks_and_departments(self):
        self.post(self.c_carol)
        later = make_shift(self.eng, day=DAY + datetime.timedelta(days=7), posted=False)
        other = make_shift(self.mkt, posted=False)
        ids = [s['id'] for s in self.c_alice.get('/api/shifts/').data]
        self.assertEqual(ids, [self.shift.pk])
        self.assertNotIn(later.pk, ids)
        self.assertEqual(self.c_gus.get('/api/shifts/').data, [])
        self.assertEqual([s['id'] for s in self.c_carol.get('/api/shifts/').data if s['id'] == other.pk], [other.pk])

    def test_no_notifications_while_still_a_draft(self):
        self.c_carol.post(f'/api/shifts/{self.shift.pk}/assign/', {'employee': self.alice.pk + 0}, format='json')
        dana = person(self.company, self.eng, 'employee', 'dana@x.com', 'Dana', 'D')
        self.assertEqual(self.c_carol.post(f'/api/shifts/{self.shift.pk}/assign/', {'employee': dana.pk}, format='json').status_code, 200)
        self.assertFalse(Notification.objects.filter(recipient=dana.user).exists())
        self.c_carol.post(f'/api/shifts/{self.shift.pk}/unassign/', {'assignment': Schedule.objects.get(employee=dana).pk}, format='json')
        self.assertFalse(Notification.objects.filter(recipient=dana.user).exists())

    def test_edits_after_posting_go_live_and_only_tell_the_affected_person(self):
        self.post(self.c_carol)
        dana = person(self.company, self.eng, 'employee', 'dana@x.com', 'Dana', 'D')
        Notification.objects.all().delete()
        self.assertEqual(self.c_carol.post(f'/api/shifts/{self.shift.pk}/assign/', {'employee': dana.pk}, format='json').status_code, 200)
        self.assertEqual(list(Notification.objects.values_list('recipient', flat=True)), [dana.user_id])
        Notification.objects.all().delete()
        self.c_carol.patch(f'/api/shifts/{self.shift.pk}/', {'start_time': '10:00'}, format='json')
        self.assertEqual({n.recipient_id for n in Notification.objects.all()}, {dana.user_id, self.alice.user_id})
        Notification.objects.all().delete()
        self.c_carol.post(f'/api/shifts/{self.shift.pk}/unassign/', {'assignment': Schedule.objects.get(employee=dana).pk}, format='json')
        self.assertEqual([n.recipient_id for n in Notification.objects.all()], [dana.user_id])
        Notification.objects.all().delete()
        self.c_carol.delete(f'/api/shifts/{self.shift.pk}/')
        self.assertEqual([n.recipient_id for n in Notification.objects.all()], [self.alice.user_id])

    def test_cannot_ask_for_a_swap_on_a_draft_week(self):
        dana = person(self.company, self.eng, 'employee', 'dana@x.com', 'Dana', 'D')
        mine = Schedule.objects.get(employee=self.alice)
        r = self.c_alice.post('/api/shift-requests/', {'kind': 'give', 'schedule': mine.pk, 'to_employee': dana.pk}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_moving_a_shift_into_another_week_keeps_week_start_in_step(self):
        self.c_carol.patch(f'/api/shifts/{self.shift.pk}/', {'shift_date': (DAY + datetime.timedelta(days=7)).isoformat()}, format='json')
        self.shift.refresh_from_db()
        self.assertEqual(self.shift.week_start, self.shift.shift_date - datetime.timedelta(days=self.shift.shift_date.weekday()))


class AvailabilityAlertTests(RoleBase):
    """Managers of the department and the General Manager hear when an employee changes their availability."""

    def slot(self, client, who, day=0, start='09:00', end='17:00'):
        return client.post('/api/availability/', {'employee': who.pk, 'day_of_week': day, 'start_time': start, 'end_time': end}, format='json')

    def heard(self, who):
        return Notification.objects.filter(recipient=who.user, message__contains='changed their availability')

    def test_manager_and_general_manager_are_told(self):
        self.assertEqual(self.slot(self.c_alice, self.alice).status_code, 201)
        self.assertEqual(self.heard(self.carol).count(), 1)
        self.assertEqual(self.heard(self.ceo).count(), 1)
        self.assertIn('Alice E', self.heard(self.carol).first().message)
        self.assertEqual(self.heard(self.bob).count(), 0)      # manages another department
        self.assertEqual(self.heard(self.alice).count(), 0)    # not told about their own change

    def test_a_burst_of_edits_is_one_alert_until_it_is_read(self):
        slot_id = self.slot(self.c_alice, self.alice).data['id']
        self.slot(self.c_alice, self.alice, day=1)
        self.c_alice.patch(f'/api/availability/{slot_id}/', {'end_time': '15:00'}, format='json')
        self.c_alice.put('/api/availability/days/', {'unavailable_days': [5]}, format='json')
        self.c_alice.delete(f'/api/availability/{slot_id}/')
        self.assertEqual(self.heard(self.carol).count(), 1)
        self.heard(self.carol).update(is_read=True)
        self.slot(self.c_alice, self.alice, day=2)
        self.assertEqual(self.heard(self.carol).count(), 2)   # a new alert once the old one was read

    def test_unchanged_days_do_not_alert_and_manager_edits_do_not_alert(self):
        self.c_alice.put('/api/availability/days/', {'unavailable_days': []}, format='json')
        self.assertEqual(self.heard(self.carol).count(), 0)
        self.assertEqual(self.slot(self.c_carol, self.alice).status_code, 201)       # a manager edited it
        self.c_carol.put('/api/availability/days/', {'employee': self.alice.pk, 'unavailable_days': [3]}, format='json')
        self.assertEqual(self.heard(self.ceo).count(), 0)
        self.c_alice.put('/api/availability/days/', {'unavailable_days': [3, 4]}, format='json')
        self.assertEqual(self.heard(self.ceo).count(), 1)


class AvailabilityWarningTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.shift = make_shift(self.eng, '09:00', '13:00', 2, posted=False)

    def assign(self, **extra):
        return self.c_carol.post(f'/api/shifts/{self.shift.pk}/assign/', {'employee': self.alice.pk, **extra}, format='json')

    def test_untouched_availability_is_fine(self):
        self.assertEqual(self.assign().status_code, 200)

    def test_not_available_day_asks_for_confirmation(self):
        self.alice.unavailable_days = [self.shift.shift_date.weekday()]
        self.alice.save()
        r = self.assign()
        self.assertEqual(r.status_code, 409, r.data)
        self.assertEqual(r.data['code'], 'schedule_warning')
        self.assertIn('not available', r.data['detail'])
        self.assertFalse(Schedule.objects.filter(shift=self.shift).exists())
        self.assertEqual(self.assign(confirm_warnings=True).status_code, 200)

    def test_hours_outside_a_slot_ask_for_confirmation(self):
        day = self.shift.shift_date.weekday()
        AvailabilitySlot.objects.create(employee=self.alice, day_of_week=day, start_time='13:00', end_time='17:00')
        r = self.assign()
        self.assertEqual(r.status_code, 409, r.data)
        self.assertIn('only available 1 PM - 5 PM', r.data['detail'])
        self.assertEqual(self.assign(confirm_warnings=True).status_code, 200)

    def test_inside_a_slot_is_fine(self):
        day = self.shift.shift_date.weekday()
        AvailabilitySlot.objects.create(employee=self.alice, day_of_week=day, start_time='08:00', end_time='14:00')
        self.assertEqual(self.assign().status_code, 200)

    def test_post_review_lists_it_too(self):
        put(self.shift, self.alice)
        self.alice.unavailable_days = [self.shift.shift_date.weekday()]
        self.alice.save()
        data = self.c_carol.get('/api/shifts/review/', {'department': self.eng.pk, 'week_start': self.shift.week_start.isoformat()}).data
        self.assertTrue(any('not available' in w for w in data['warnings']), data['warnings'])


class OfferToEveryoneTests(RoleBase):
    """Giving up a shift to the whole department: everyone is asked, the first to accept gets it."""

    def setUp(self):
        super().setUp()
        self.dana = person(self.company, self.eng, 'employee', 'dana@x.com', 'Dana', 'D')
        self.erin = person(self.company, self.eng, 'employee', 'erin@x.com', 'Erin', 'E')
        self.c_dana, self.c_erin = as_user(self.dana), as_user(self.erin)
        self.shift = make_shift(self.eng, '09:00', '13:00', 2)
        self.mine = put(self.shift, self.alice)

    def offer(self, **extra):
        return self.c_alice.post('/api/shift-requests/', {'kind': 'offer', 'schedule': self.mine.pk, **extra}, format='json')

    def test_everyone_in_the_department_is_asked_and_managers_told(self):
        r = self.offer()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data['kind'], r.data['status'], r.data['target']), ('offer', 'pending', None))
        for who in (self.dana, self.erin):
            n = Notification.objects.get(recipient=who.user, kind='shift_request')
            self.assertIn('wants to give up their shift', n.message)
            self.assertIn('9 AM - 1 PM', n.message)
            self.assertEqual(n.shift_request_id, r.data['id'])
        self.assertFalse(Notification.objects.filter(recipient=self.alice.user, kind='shift_request').exists())
        self.assertFalse(Notification.objects.filter(recipient=self.gus.user).exists())       # other department
        self.assertFalse(Notification.objects.filter(recipient=self.carol.user, kind='shift_request').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.carol.user, message__contains='offered').exists())

    def test_first_to_accept_gets_it_and_nobody_else_can(self):
        sr = self.offer().data['id']
        r = self.c_dana.post(f'/api/shift-requests/{sr}/accept/')
        self.assertEqual(r.status_code, 200, r.data)
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.employee, self.dana)
        self.assertEqual((r.data['status'], r.data['target']['name']), ('accepted', 'Dana D'))
        late = self.c_erin.post(f'/api/shift-requests/{sr}/accept/')
        self.assertEqual(late.status_code, 400)
        self.assertIn('already took', late.data['detail'])
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.employee, self.dana)
        self.assertTrue(Notification.objects.get(recipient=self.erin.user, kind='shift_request').is_read)
        self.assertTrue(Notification.objects.filter(recipient=self.alice.user, message__contains='accepted').exists())
        self.assertTrue(Notification.objects.filter(recipient=self.carol.user, message__contains='gave').exists())

    def test_declining_only_dismisses_it_for_that_person(self):
        sr = self.offer().data['id']
        r = self.c_dana.post(f'/api/shift-requests/{sr}/decline/')
        self.assertEqual((r.status_code, r.data['status']), (200, 'pending'))
        self.assertTrue(Notification.objects.get(recipient=self.dana.user, kind='shift_request').is_read)
        self.assertFalse(Notification.objects.get(recipient=self.erin.user, kind='shift_request').is_read)
        self.assertEqual(self.c_erin.post(f'/api/shift-requests/{sr}/accept/').status_code, 200)

    def test_who_may_answer(self):
        sr = self.offer().data['id']
        self.assertEqual(self.c_alice.post(f'/api/shift-requests/{sr}/accept/').status_code, 403)   # the giver
        self.assertEqual(self.c_gus.post(f'/api/shift-requests/{sr}/accept/').status_code, 404)     # other department
        self.assertEqual(self.c_carol.post(f'/api/shift-requests/{sr}/accept/').status_code, 404)   # managers are only told

    def test_accept_checks_the_acceptor_can_work_it(self):
        other = make_shift(self.eng, '10:00', '12:00', 1, name='Clash')
        put(other, self.dana)
        sr = self.offer().data['id']
        r = self.c_dana.post(f'/api/shift-requests/{sr}/accept/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('already works', r.data['detail'])
        self.mine.refresh_from_db()
        self.assertEqual(self.mine.employee, self.alice)
        self.assertEqual(self.c_erin.post(f'/api/shift-requests/{sr}/accept/').status_code, 200)   # still open

    def test_requester_can_cancel_and_cannot_offer_twice_or_someone_elses_shift(self):
        sr = self.offer().data['id']
        self.assertEqual(self.offer().status_code, 400)
        self.assertEqual(self.c_alice.post(f'/api/shift-requests/{sr}/cancel/').status_code, 200)
        self.assertEqual(self.c_dana.post(f'/api/shift-requests/{sr}/accept/').status_code, 400)
        theirs = put(make_shift(self.eng, '14:00', '18:00', 1, name='PM'), self.dana)
        r = self.c_alice.post('/api/shift-requests/', {'kind': 'offer', 'schedule': theirs.pk}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_offer_is_void_if_the_shift_changed_hands_meanwhile(self):
        sr = self.offer().data['id']
        self.mine.employee = self.erin
        self.mine.save()
        r = self.c_dana.post(f'/api/shift-requests/{sr}/accept/')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.c_dana.get('/api/shift-requests/').data[0]['status'], 'cancelled')

    def test_nobody_to_offer_to(self):
        self.dana.delete()
        self.erin.delete()
        r = self.offer()
        self.assertEqual(r.status_code, 400)

    def test_offer_not_available_on_a_draft_week(self):
        draft = make_shift(self.eng, '14:00', '18:00', 1, name='Draft', day=DAY + datetime.timedelta(days=21), posted=False)
        row = put(draft, self.alice)
        r = self.c_alice.post('/api/shift-requests/', {'kind': 'offer', 'schedule': row.pk}, format='json')
        self.assertEqual(r.status_code, 400)


class ExtraDepartmentTests(RoleBase):
    """An employee has a home department and can also work in others, where a manager schedules them by hand."""

    def setUp(self):
        super().setUp()
        self.mkt_shift = make_shift(self.mkt, '09:00', '13:00', 2)
        self.url = f'/api/employees/{self.alice.pk}/'

    def add(self, client, ids=None):
        return client.patch(self.url, {'extra_department_ids': [self.mkt.pk] if ids is None else ids}, format='json')

    def test_general_manager_and_home_manager_can_add_extra_departments(self):
        r = self.add(self.c_ceo)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([d['name'] for d in r.data['extra_departments']], ['Mkt'])
        self.assertEqual(r.data['department']['name'], 'Eng')          # home is unchanged
        self.assertTrue(Notification.objects.filter(recipient=self.alice.user, message__contains='Mkt').exists())
        self.assertEqual(self.add(self.c_carol, []).status_code, 200)   # home manager removes it again
        self.assertEqual(self.add(self.c_carol).status_code, 200)

    def test_manager_of_the_extra_department_sees_but_cannot_edit(self):
        self.add(self.c_ceo)
        self.assertIn(self.alice.pk, [e['id'] for e in self.c_bob.get('/api/employees/').data])
        self.assertEqual(self.add(self.c_bob, []).status_code, 403)
        self.assertEqual(self.c_bob.patch(self.url, {'position': 'x'}, format='json').status_code, 403)

    def test_validation(self):
        self.assertEqual(self.add(self.c_ceo, [self.eng.pk]).status_code, 400)            # that is the home department
        self.assertEqual(self.add(self.c_ceo, [99999]).status_code, 400)
        self.assertEqual(self.add(self.c_ceo, 'x').status_code, 400)
        r = self.c_ceo.patch(f'/api/employees/{self.carol.pk}/', {'extra_department_ids': [self.mkt.pk]}, format='json')
        self.assertEqual(r.status_code, 400)                                                # managers use managed departments
        self.assertEqual(self.add(self.c_alice).status_code, 403)

    def test_manager_of_the_extra_department_schedules_them_by_hand(self):
        url = f'/api/shifts/{self.mkt_shift.pk}/assign/'
        self.assertEqual(self.c_bob.post(url, {'employee': self.alice.pk}, format='json').status_code, 400)   # not in Mkt yet
        self.add(self.c_ceo)
        self.assertEqual(self.c_bob.post(url, {'employee': self.alice.pk}, format='json').status_code, 200)
        self.assertEqual(self.c_carol.post(url, {'employee': self.alice.pk}, format='json').status_code, 403)  # Carol does not run Mkt
        shifts = self.c_alice.get('/api/shifts/').data
        self.assertIn(self.mkt_shift.pk, [s['id'] for s in shifts])
        self.assertEqual(self.c_gus.get('/api/shifts/').data[0]['id'], self.mkt_shift.pk)

    def test_auto_scheduler_never_places_them_outside_their_home_department(self):
        self.add(self.c_ceo)
        r = self.c_bob.post('/api/shifts/auto-schedule/', {'department': self.mkt.pk, 'date_from': DAY.isoformat(),
                                                           'date_to': DAY.isoformat(), 'confirm_pending': True}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(Schedule.objects.filter(employee=self.alice).exists())
        self.assertTrue(Schedule.objects.filter(employee=self.gus, shift=self.mkt_shift).exists())

    def test_hours_and_clashes_count_across_departments(self):
        self.add(self.c_ceo)
        put(make_shift(self.eng, '10:00', '12:00', 1, name='Clash'), self.alice)
        r = self.c_bob.post(f'/api/shifts/{self.mkt_shift.pk}/assign/', {'employee': self.alice.pk}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('already works', str(r.data))

    def test_cannot_drop_a_department_they_still_have_shifts_in(self):
        self.add(self.c_ceo)
        put(self.mkt_shift, self.alice)
        r = self.add(self.c_ceo, [])
        self.assertEqual(r.status_code, 400)
        self.assertIn('upcoming shifts', str(r.data))
        Schedule.objects.filter(employee=self.alice).delete()
        self.assertEqual(self.add(self.c_ceo, []).status_code, 200)

    def test_moving_their_home_department_into_an_extra_one_clears_it(self):
        self.add(self.c_ceo)
        r = self.c_ceo.post(f'{self.url}transfer/', {'department': self.mkt.pk}, format='json')
        self.assertIn(r.status_code, (200, 201), r.data)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.department_id, self.mkt.pk)
        self.assertEqual(self.alice.extra_departments.count(), 0)

    def test_transfer_keeps_shifts_in_extra_departments(self):
        self.add(self.c_ceo)
        row = put(self.mkt_shift, self.alice)
        self.c_ceo.post(f'{self.url}transfer/', {'department': self.hr.pk}, format='json')
        self.assertTrue(Schedule.objects.filter(pk=row.pk).exists())

    def test_requests_work_in_the_extra_department(self):
        self.add(self.c_ceo)
        row = put(self.mkt_shift, self.alice)
        names = [c['name'] for c in self.c_alice.get('/api/coworkers/', {'department': self.mkt.pk}).data]
        self.assertIn('Gus E', names)
        self.assertNotIn('Alice E', names)
        self.assertEqual(self.c_alice.get('/api/coworkers/', {'department': self.hr.pk}).status_code, 403)
        self.assertNotIn('Gus E', [c['name'] for c in self.c_alice.get('/api/coworkers/').data])   # home = Eng
        r = self.c_alice.post('/api/shift-requests/', {'kind': 'offer', 'schedule': row.pk}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(Notification.objects.filter(recipient=self.gus.user, kind='shift_request').exists())
        self.assertEqual(self.c_gus.post(f'/api/shift-requests/{r.data["id"]}/accept/').status_code, 200)

    def test_extra_members_can_answer_offers_and_availability_alerts_reach_both_managers(self):
        self.add(self.c_ceo)
        row = put(self.mkt_shift, self.gus)
        r = self.c_gus.post('/api/shift-requests/', {'kind': 'offer', 'schedule': row.pk}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(Notification.objects.filter(recipient=self.alice.user, kind='shift_request').exists())
        self.assertEqual(self.c_alice.post(f'/api/shift-requests/{r.data["id"]}/accept/').status_code, 200)
        self.c_alice.post('/api/availability/', {'employee': self.alice.pk, 'day_of_week': 0, 'start_time': '09:00', 'end_time': '17:00'}, format='json')
        for manager in (self.carol, self.bob, self.ceo):
            self.assertTrue(Notification.objects.filter(recipient=manager.user, message__contains='changed their availability').exists())

    def test_department_with_extra_members_cannot_be_deleted(self):
        self.add(self.c_ceo)
        self.assertEqual(self.c_ceo.delete(f'/api/departments/{self.hr.pk}/').status_code, 204)
        r = self.c_ceo.delete(f'/api/departments/{self.mkt.pk}/')
        self.assertEqual(r.status_code, 400)

    def test_me_lists_extra_departments(self):
        self.add(self.c_ceo)
        me = self.c_alice.get('/api/me/').data
        self.assertEqual([d['name'] for d in me['profile']['extra_departments']], ['Mkt'])
