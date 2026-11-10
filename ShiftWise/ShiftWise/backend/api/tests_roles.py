# pyright: reportAttributeAccessIssue=false
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import (Company, Department, EmployeeProfile, JoinCode, Notification, Schedule, TimeOffRequest,
                     TransferRequest, User)

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def person(company, department, role, email, first='Pat', last='Person'):
    user = User.objects.create_user(username=email.split('@')[0], email=email, first_name=first, last_name=last,
                                    password='pass12345', date_of_birth='1990-01-01')
    return EmployeeProfile.objects.create(user=user, company=company, department=department, role=role)


def as_user(profile):
    client = APIClient()
    client.force_authenticate(profile.user)
    return client


@FAST
class RoleBase(APITestCase):
    """Company with Eng + Mkt + HR. General Manager; Carol manages Eng; Bob manages Mkt; Alice (Eng), Gus (Mkt) employees."""

    def setUp(self):
        self.company = Company.objects.create(name='Acme')
        self.eng = Department.objects.create(company=self.company, name='Eng')
        self.mkt = Department.objects.create(company=self.company, name='Mkt')
        self.hr = Department.objects.create(company=self.company, name='HR')
        self.ceo = person(self.company, self.eng, 'ceo', 'ceo@x.com', 'Cee', 'Oh')
        self.carol = person(self.company, self.eng, 'manager', 'carol@x.com', 'Carol', 'M')
        self.carol.managed_departments.set([self.eng])
        self.bob = person(self.company, self.mkt, 'manager', 'bob@x.com', 'Bob', 'M')
        self.bob.managed_departments.set([self.mkt])
        self.alice = person(self.company, self.eng, 'employee', 'alice@x.com', 'Alice', 'E')
        self.gus = person(self.company, self.mkt, 'employee', 'gus@x.com', 'Gus', 'E')
        self.c_ceo, self.c_carol, self.c_bob = as_user(self.ceo), as_user(self.carol), as_user(self.bob)
        self.c_alice, self.c_gus = as_user(self.alice), as_user(self.gus)

    def make_code(self, role='employee', dept=None, creator=None):
        code = JoinCode.objects.create(company=self.company, role=role, created_by=(creator or self.ceo).user)
        code.departments.set([dept or self.eng])
        return code

    def signup_payload(self, **kw):
        data = {'username': 'newbie', 'email': 'newbie@x.com', 'first_name': 'New', 'last_name': 'Bie',
                'password': 'Str0ngPass!!', 'date_of_birth': '2000-01-01'}
        data.update(kw)
        return data


class SignupRoleTests(RoleBase):
    url = '/api/signup/'

    def test_role_required(self):
        r = APIClient().post(self.url, self.signup_payload(), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('role', r.data)

    def test_ceo_creates_company_with_default_department(self):
        r = APIClient().post(self.url, self.signup_payload(role='ceo', company_name='NewCo'), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        profile = User.objects.get(email='newbie@x.com').employee_profile
        self.assertEqual(profile.role, 'ceo')
        self.assertEqual(profile.company.name, 'NewCo')
        self.assertEqual(profile.department.name, 'General')

    def test_ceo_custom_department_and_company_required(self):
        r = APIClient().post(self.url, self.signup_payload(role='ceo', company_name='NewCo',
                                                           department_name='Sales'), format='json')
        self.assertEqual(User.objects.get(email='newbie@x.com').employee_profile.department.name, 'Sales')
        r = APIClient().post(self.url, self.signup_payload(role='ceo', email='n2@x.com', username='n2'),
                             format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('company_name', r.data)
        self.assertFalse(User.objects.filter(email='n2@x.com').exists())

    def test_employee_needs_valid_code(self):
        for code in ('', 'NOPE-NOPE'):
            r = APIClient().post(self.url, self.signup_payload(role='employee', join_code=code), format='json')
            self.assertEqual(r.status_code, 400)
            self.assertIn('join_code', r.data)
        self.assertFalse(User.objects.filter(email='newbie@x.com').exists())

    def test_employee_joins_with_code_once(self):
        code = self.make_code()
        r = APIClient().post(self.url, self.signup_payload(role='employee', join_code=code.code.lower()),
                             format='json')
        self.assertEqual(r.status_code, 201, r.data)
        profile = User.objects.get(email='newbie@x.com').employee_profile
        self.assertEqual((profile.role, profile.department), ('employee', self.eng))
        code.refresh_from_db()
        self.assertTrue(code.is_used)
        r = APIClient().post(self.url, self.signup_payload(role='employee', email='b@x.com', username='b',
                                                           join_code=code.code), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('already been used', r.data['join_code'][0])

    def test_code_for_wrong_role(self):
        code = self.make_code('manager')
        r = APIClient().post(self.url, self.signup_payload(role='employee', join_code=code.code), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('join_code', r.data)

    def test_manager_code_gives_managed_departments(self):
        code = self.make_code('manager')
        code.departments.set([self.eng, self.hr])
        r = APIClient().post(self.url, self.signup_payload(role='manager', join_code=code.code), format='json')
        self.assertEqual(r.status_code, 201, r.data)
        profile = User.objects.get(email='newbie@x.com').employee_profile
        self.assertEqual(set(profile.managed_departments.all()), {self.eng, self.hr})

    def test_code_check_endpoint(self):
        code = self.make_code()
        ok = APIClient().get('/api/join-code-check/', {'code': code.code, 'role': 'employee'})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data['company'], 'Acme')
        bad = APIClient().get('/api/join-code-check/', {'code': 'ZZZZ-ZZZZ'})
        self.assertEqual(bad.status_code, 404)
        self.assertFalse(bad.data['valid'])


class MeTests(RoleBase):
    def test_me_data(self):
        r = self.c_carol.get('/api/me/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['profile']['role'], 'manager')
        self.assertTrue(r.data['profile']['can_edit_schedule'])
        self.assertEqual([d['name'] for d in r.data['profile']['managed_departments']], ['Eng'])
        self.assertFalse(self.c_alice.get('/api/me/').data['profile']['can_edit_schedule'])

    def test_me_requires_login(self):
        self.assertEqual(APIClient().get('/api/me/').status_code, 401)

    def test_user_without_profile_can_join_with_code(self):
        user = User.objects.create_user(username='x', email='lone@x.com', first_name='L', last_name='One',
                                        password='pass12345', date_of_birth='1990-01-01')
        client = APIClient()
        client.force_authenticate(user)
        self.assertIsNone(client.get('/api/me/').data['profile'])
        r = client.post('/api/me/join/', {'join_code': 'NOPE-NOPE'}, format='json')
        self.assertEqual(r.status_code, 400)
        code = self.make_code(dept=self.mkt)
        r = client.post('/api/me/join/', {'join_code': code.code}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(client.get('/api/me/').data['profile']['department']['name'], 'Mkt')
        self.assertEqual(r.data['profile']['managed_departments'], [])


class CodeTests(RoleBase):
    def create(self, client, role, depts):
        return client.post('/api/join-codes/', {'role': role, 'departments': [d.pk for d in depts]}, format='json')

    def test_ceo_creates_manager_and_employee_codes(self):
        self.assertEqual(self.create(self.c_ceo, 'manager', [self.eng, self.mkt]).status_code, 201)
        self.assertEqual(self.create(self.c_ceo, 'employee', [self.hr]).status_code, 201)

    def test_manager_only_employee_codes_for_own_departments(self):
        self.assertEqual(self.create(self.c_carol, 'manager', [self.eng]).status_code, 403)
        self.assertEqual(self.create(self.c_carol, 'employee', [self.eng]).status_code, 201)
        self.assertEqual(self.create(self.c_carol, 'employee', [self.mkt]).status_code, 403)

    def test_employee_cannot_use_codes_api(self):
        self.assertEqual(self.c_alice.get('/api/join-codes/').status_code, 403)
        self.assertEqual(self.create(self.c_alice, 'employee', [self.eng]).status_code, 403)

    def test_validation(self):
        self.assertEqual(self.create(self.c_ceo, 'boss', [self.eng]).status_code, 400)
        self.assertEqual(self.create(self.c_ceo, 'employee', []).status_code, 400)
        self.assertEqual(self.create(self.c_ceo, 'employee', [self.eng, self.mkt]).status_code, 400)

    def test_list_scope_and_revoke(self):
        mine = self.make_code(creator=self.carol)
        theirs = self.make_code(creator=self.bob, dept=self.mkt)
        self.assertEqual([c['id'] for c in self.c_carol.get('/api/join-codes/').data], [mine.pk])
        self.assertEqual({c['id'] for c in self.c_ceo.get('/api/join-codes/').data}, {mine.pk, theirs.pk})
        self.assertEqual(self.c_carol.delete(f'/api/join-codes/{theirs.pk}/').status_code, 404)
        self.assertEqual(self.c_carol.delete(f'/api/join-codes/{mine.pk}/').status_code, 204)

    def test_other_company_cannot_see_codes(self):
        other_co = Company.objects.create(name='Other')
        other_dept = Department.objects.create(company=other_co, name='X')
        boss = person(other_co, other_dept, 'ceo', 'boss@y.com')
        self.make_code()
        self.assertEqual(as_user(boss).get('/api/join-codes/').data, [])


class DepartmentTests(RoleBase):
    def test_only_ceo_writes(self):
        self.assertEqual(self.c_ceo.post('/api/departments/', {'name': 'Ops'}, format='json').status_code, 201)
        self.assertEqual(self.c_carol.post('/api/departments/', {'name': 'Ops2'}, format='json').status_code, 403)
        self.assertEqual(self.c_alice.post('/api/departments/', {'name': 'Ops3'}, format='json').status_code, 403)

    def test_everyone_can_list_and_duplicates_rejected(self):
        self.assertEqual(self.c_alice.get('/api/departments/').status_code, 200)
        r = self.c_ceo.post('/api/departments/', {'name': ' eng '}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_delete_blocked_when_people_remain(self):
        self.assertEqual(self.c_ceo.delete(f'/api/departments/{self.eng.pk}/').status_code, 400)
        self.assertEqual(self.c_ceo.delete(f'/api/departments/{self.hr.pk}/').status_code, 204)
        self.assertEqual(self.c_carol.delete(f'/api/departments/{self.mkt.pk}/').status_code, 403)


class EmployeeDirectoryTests(RoleBase):
    def ids(self, client):
        r = client.get('/api/employees/')
        self.assertEqual(r.status_code, 200)
        return {e['id'] for e in r.data}

    def test_visibility(self):
        self.assertEqual(self.ids(self.c_ceo), {p.pk for p in (self.ceo, self.carol, self.bob, self.alice, self.gus)})
        self.assertEqual(self.ids(self.c_carol), {self.ceo.pk, self.carol.pk, self.alice.pk})
        self.assertEqual(self.c_alice.get('/api/employees/').status_code, 403)

    def test_add_roster_only_employee(self):
        r = self.c_carol.post('/api/employees/', {'first_name': 'Ro', 'last_name': 'Ster', 'department': self.eng.pk,
                                                  'position': 'Clerk'}, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        user = User.objects.get(first_name='Ro')
        self.assertFalse(user.has_usable_password())
        r = self.c_carol.post('/api/employees/', {'first_name': 'No', 'last_name': 'Way', 'department': self.mkt.pk},
                              format='json')
        self.assertEqual(r.status_code, 403)

    def test_remove_employee(self):
        self.assertEqual(self.c_bob.delete(f'/api/employees/{self.alice.pk}/').status_code, 404)
        self.assertEqual(self.c_carol.delete(f'/api/employees/{self.alice.pk}/').status_code, 204)
        self.assertFalse(EmployeeProfile.objects.filter(pk=self.alice.pk).exists())

    def test_roster_user_deleted_with_profile(self):
        r = self.c_carol.post('/api/employees/', {'first_name': 'Ro', 'last_name': 'Ster', 'department': self.eng.pk},
                              format='json')
        self.assertEqual(self.c_carol.delete(f'/api/employees/{r.data["id"]}/').status_code, 204)
        self.assertFalse(User.objects.filter(first_name='Ro').exists())

    def test_manager_cannot_remove_manager_or_ceo(self):
        self.assertEqual(self.c_carol.delete(f'/api/employees/{self.ceo.pk}/').status_code, 403)
        self.assertEqual(self.c_ceo.delete(f'/api/employees/{self.ceo.pk}/').status_code, 400)  # yourself
        self.assertEqual(self.c_ceo.delete(f'/api/employees/{self.carol.pk}/').status_code, 204)

    def test_only_ceo_assigns_managed_departments(self):
        url = f'/api/employees/{self.carol.pk}/'
        r = self.c_carol.patch(url, {'managed_department_ids': [self.eng.pk, self.mkt.pk]}, format='json')
        self.assertEqual(r.status_code, 403)
        r = self.c_ceo.patch(url, {'managed_department_ids': [self.eng.pk, self.mkt.pk]}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(set(self.carol.managed_departments.all()), {self.eng, self.mkt})


class TransferTests(RoleBase):
    def transfer(self, client, target, dept):
        return client.post(f'/api/employees/{target.pk}/transfer/', {'department': dept.pk}, format='json')

    def test_manager_moves_within_own_departments_instantly(self):
        self.carol.managed_departments.add(self.hr)
        r = self.transfer(self.c_carol, self.alice, self.hr)
        self.assertEqual((r.status_code, r.data['outcome']), (200, 'done'))
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.department, self.hr)

    def test_ceo_moves_instantly(self):
        r = self.transfer(self.c_ceo, self.alice, self.mkt)
        self.assertEqual(r.data['outcome'], 'done')

    def test_request_goes_to_destination_manager_and_accept_moves(self):
        r = self.transfer(self.c_carol, self.alice, self.mkt)
        self.assertEqual((r.status_code, r.data['outcome']), (202, 'pending'))
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.department, self.eng)
        note = Notification.objects.get(recipient=self.bob.user, kind='transfer_request')
        self.assertEqual(self.c_bob.get('/api/notifications/').data[0]['id'], note.pk)
        self.assertEqual(self.c_carol.get('/api/transfer-requests/').data[0]['status'], 'pending')
        tr = TransferRequest.objects.get()
        self.assertEqual(self.c_carol.post(f'/api/transfer-requests/{tr.pk}/accept/').status_code, 403)
        r = self.c_bob.post(f'/api/transfer-requests/{tr.pk}/accept/')
        self.assertEqual(r.status_code, 200, r.data)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.department, self.mkt)
        self.assertTrue(Notification.objects.filter(recipient=self.carol.user, kind='transfer_result').exists())

    def test_reject_leaves_employee_in_place(self):
        self.transfer(self.c_carol, self.alice, self.mkt)
        tr = TransferRequest.objects.get()
        self.assertEqual(self.c_bob.post(f'/api/transfer-requests/{tr.pk}/reject/').status_code, 200)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.department, self.eng)
        tr.refresh_from_db()
        self.assertEqual(tr.status, 'rejected')
        self.assertEqual(self.c_bob.post(f'/api/transfer-requests/{tr.pk}/accept/').status_code, 400)

    def test_destination_without_manager_goes_to_ceo(self):
        r = self.transfer(self.c_carol, self.alice, self.hr)
        self.assertEqual(r.data['outcome'], 'pending')
        self.assertTrue(Notification.objects.filter(recipient=self.ceo.user, kind='transfer_request').exists())
        tr = TransferRequest.objects.get()
        self.assertEqual(self.c_ceo.post(f'/api/transfer-requests/{tr.pk}/accept/').status_code, 200)
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.department, self.hr)

    def test_cannot_transfer_outside_scope(self):
        self.assertEqual(self.transfer(self.c_carol, self.gus, self.eng).status_code, 404)
        self.assertEqual(self.transfer(self.c_alice, self.alice, self.mkt).status_code, 403)


class LeaveTests(RoleBase):
    def test_employee_leaves(self):
        r = self.c_alice.post('/api/me/leave/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertFalse(EmployeeProfile.objects.filter(pk=self.alice.pk).exists())
        self.assertIsNone(self.c_alice.get('/api/me/').data['profile'])
        self.assertTrue(User.objects.filter(pk=self.alice.user_id).exists())

    def test_ceo_cannot_leave(self):
        r = self.c_ceo.post('/api/me/leave/')
        self.assertEqual(r.status_code, 400)
        self.assertIn('General Manager cannot leave', str(r.data))
        self.assertTrue(EmployeeProfile.objects.filter(pk=self.ceo.pk).exists())

    def test_last_manager_leaving_notifies_ceo(self):
        r = self.c_bob.post('/api/me/leave/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(Notification.objects.filter(recipient=self.ceo.user, kind='no_manager').exists())

    def test_manager_leaving_with_co_manager_does_not_notify(self):
        self.carol.managed_departments.add(self.mkt)
        self.c_bob.post('/api/me/leave/')
        self.assertFalse(Notification.objects.filter(kind='no_manager').exists())


class NotificationTests(RoleBase):
    def test_mark_read(self):
        n = Notification.objects.create(recipient=self.alice.user, kind='info', message='Hi')
        self.assertEqual(self.c_alice.get('/api/me/').data['unread_notifications'], 1)
        self.assertEqual(self.c_bob.post(f'/api/notifications/{n.pk}/read/').status_code, 404)
        self.assertEqual(self.c_alice.post(f'/api/notifications/{n.pk}/read/').data['unread_notifications'], 0)
        Notification.objects.create(recipient=self.alice.user, kind='info', message='Again')
        self.assertEqual(self.c_alice.post('/api/notifications/read-all/').status_code, 200)
        self.assertEqual(self.c_alice.get('/api/me/').data['unread_notifications'], 0)


class SchedulePermissionTests(RoleBase):
    def shift(self, employee, **kw):
        fields = {'task_name': 'Shift', 'employee': employee, 'shift_date': '2026-10-19',
                  'start_time': '09:00', 'end_time': '17:00'}
        fields.update(kw)
        return Schedule.objects.create(**fields)

    def payload(self, employee, **kw):
        data = {'task_name': 'Shift', 'employee': employee.pk, 'shift_date': '2026-10-20',
                'start_time': '09:00', 'end_time': '17:00'}
        data.update(kw)
        return data

    def test_employee_is_read_only_and_sees_own_department(self):
        mine = self.shift(self.alice)
        self.shift(self.gus)
        r = self.c_alice.get('/api/schedules/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual({s['id'] for s in r.data}, {mine.pk})
        self.assertEqual(self.c_alice.post('/api/schedules/', self.payload(self.alice), format='json').status_code, 403)
        self.assertEqual(self.c_alice.delete(f'/api/schedules/{mine.pk}/').status_code, 403)
        self.assertEqual(self.c_alice.patch(f'/api/schedules/{mine.pk}/', {'task_name': 'x'},
                                            format='json').status_code, 403)

    def test_manager_edits_only_managed_departments(self):
        self.assertEqual(self.c_carol.post('/api/schedules/', self.payload(self.alice), format='json').status_code, 201)
        self.assertEqual(self.c_carol.post('/api/schedules/', self.payload(self.gus), format='json').status_code, 403)
        theirs = self.shift(self.gus)
        self.assertIn(self.c_carol.delete(f'/api/schedules/{theirs.pk}/').status_code, (403, 404))
        self.assertTrue(Schedule.objects.filter(pk=theirs.pk).exists())

    def test_two_managers_in_one_department_can_each_edit(self):
        carol2 = person(self.company, self.eng, 'manager', 'carol2@x.com')
        carol2.managed_departments.set([self.eng])
        a = self.c_carol.post('/api/schedules/', self.payload(self.alice), format='json')
        b = as_user(carol2).post('/api/schedules/', self.payload(self.alice, shift_date='2026-10-21'), format='json')
        self.assertEqual((a.status_code, b.status_code), (201, 201))

    def test_ceo_edits_everything(self):
        self.assertEqual(self.c_ceo.post('/api/schedules/', self.payload(self.gus), format='json').status_code, 201)


class TimeOffPermissionTests(RoleBase):
    def request(self, client, **kw):
        data = {'start_date': '2026-11-02', 'end_date': '2026-11-03', 'reason': 'Trip'}
        data.update(kw)
        return client.post('/api/time-off/', data, format='json')

    def test_employee_submits_and_sees_only_own(self):
        r = self.request(self.c_alice)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['status'], 'pending')
        self.request(self.c_gus)
        rows = self.c_alice.get('/api/time-off/').data
        self.assertEqual({row['employee'] for row in rows}, {self.alice.pk})

    def test_employee_cannot_decide(self):
        pk = self.request(self.c_alice).data['id']
        r = self.c_alice.patch(f'/api/time-off/{pk}/', {'status': 'approved'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.assertEqual(TimeOffRequest.objects.get(pk=pk).status, 'pending')

    def test_employee_can_withdraw_pending(self):
        pk = self.request(self.c_alice).data['id']
        self.assertEqual(self.c_alice.delete(f'/api/time-off/{pk}/').status_code, 204)

    def test_manager_decides_in_scope_only(self):
        pk = self.request(self.c_alice).data['id']
        gus_pk = self.request(self.c_gus).data['id']
        r = self.c_carol.patch(f'/api/time-off/{pk}/', {'status': 'approved'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.c_carol.patch(f'/api/time-off/{gus_pk}/', {'status': 'approved'},
                                            format='json').status_code, 404)
        self.assertEqual({row['id'] for row in self.c_carol.get('/api/time-off/').data}, {pk})

    def test_manager_cannot_approve_own_request(self):
        pk = self.request(self.c_carol).data['id']
        self.assertEqual(self.c_carol.patch(f'/api/time-off/{pk}/', {'status': 'approved'},
                                            format='json').status_code, 403)
        # but the General Manager can answer a manager's request
        self.assertEqual(self.c_ceo.patch(f'/api/time-off/{pk}/', {'status': 'approved'},
                                          format='json').status_code, 200)


class CompanyIsolationTests(RoleBase):
    def test_other_company_ceo_sees_nothing_of_ours(self):
        other_co = Company.objects.create(name='Other')
        other_dept = Department.objects.create(company=other_co, name='X')
        boss = as_user(person(other_co, other_dept, 'ceo', 'boss@y.com'))
        Schedule.objects.create(task_name='s', employee=self.alice, shift_date='2026-10-19',
                                start_time='09:00', end_time='17:00')
        self.assertEqual(boss.get('/api/schedules/').data, [])
        self.assertEqual({e['id'] for e in boss.get('/api/employees/').data}, {boss_p.pk for boss_p in
                         EmployeeProfile.objects.filter(company=other_co)})
        self.assertEqual(boss.delete(f'/api/employees/{self.alice.pk}/').status_code, 404)
        self.assertEqual(boss.delete(f'/api/departments/{self.eng.pk}/').status_code, 404)

    def test_user_without_profile_is_locked_out(self):
        user = User.objects.create_user(username='x', email='lone@x.com', first_name='L', last_name='One',
                                        password='pass12345', date_of_birth='1990-01-01')
        client = APIClient()
        client.force_authenticate(user)
        for url in ('/api/schedules/', '/api/employees/', '/api/time-off/'):
            self.assertEqual(client.get(url).status_code, 403, url)


class ResetCommandTests(APITestCase):
    def test_requires_yes_and_seeds(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('reset_demo_data')
        User.objects.create_user(username='old', email='old@x.com', first_name='O', last_name='D',
                                 password='pass12345', date_of_birth='1990-01-01')
        call_command('reset_demo_data', '--yes', stdout=open('/dev/null', 'w'))
        self.assertFalse(User.objects.filter(email='old@x.com').exists())
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Department.objects.count(), 4)
        ceo = User.objects.get(email='ceo@example.com')
        self.assertTrue(ceo.check_password('ShiftWise123!'))
        self.assertEqual(EmployeeProfile.objects.filter(role='manager').count(), 2)
        self.assertEqual(JoinCode.objects.filter(used_by__isnull=True).count(), 4)
        client = APIClient()
        r = client.post('/api/login/', {'email': 'employee@example.com', 'password': 'ShiftWise123!'}, format='json')
        self.assertEqual(r.status_code, 200)
