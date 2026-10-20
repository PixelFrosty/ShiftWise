from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status

from django.urls import reverse

# Create your tests here.
# pyright: reportAttributeAccessIssue=false

from .models import User

class UserModelTests(TestCase):
    def test_create(self):
        U1 = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            first_name='test',
            last_name='user',
            password='testpassword',
            date_of_birth='2000-02-02'
        )

        self.assertEqual(U1.username, 'testuser')
        self.assertEqual(U1.email, 'testuser@example.com')
        self.assertEqual(U1.first_name, 'test')
        self.assertEqual(U1.last_name, 'user')
        self.assertEqual(U1.date_of_birth, '2000-02-02')
        self.assertTrue(U1.check_password('testpassword'))

class ApiSignupTest(APITestCase):
    def test_signupApi(self):
        url = reverse('signup_api')
        payload = {
            'username': 'Test',
            'email': 'test@gmail.com',
            'first_name': 'test',
            'last_name': 'user',
            'password': 'testpass',
            'date_of_birth': '2000-02-02'
        }

        response = self.client.post(url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['username'], 'Test')
        self.assertEqual(response.data['email'], 'test@gmail.com')
        self.assertEqual(response.data['first_name'], 'test')
        self.assertEqual(response.data['last_name'], 'user')
        self.assertEqual(response.data['date_of_birth'], '2000-02-02')
        self.assertNotIn('password', response.data)

class ApiLoginTests(APITestCase):

    def setUp(self):
        self.login_url = reverse('login_api')

        self.email = 'test@gmail.com'
        self.password = 'testpass'

        User.objects.create_user(
            username='Test',
            email=self.email,
            first_name='test',
            last_name='user',
            password=self.password,
            date_of_birth='2000-02-02'
        )

    def test_nonexisting(self):
        payload = { 'email': 'fake@gmail.com', 'password': self.password }
        response = self.client.post(self.login_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_info(self):
        payload = { 'email': self.email, } # password omitted
        response = self.client.post(self.login_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_failed(self):
        payload = { 'email': self.email, 'password': 'wrongPassword' }
        response = self.client.post(self.login_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access', response.data)

    def test_success(self):
        payload = { 'email': self.email, 'password': self.password }
        response = self.client.post(self.login_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_access_token(self):
        payload = { 'email': self.email, 'password': self.password }
        login_response = self.client.post(self.login_url, payload, format='json')
        self.access_token = login_response.data['access']

        url = reverse('test_api')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access_token}')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Hello World! - This is a test API endpoint.')


class ApiLogoutTests(APITestCase):
    def setUp(self):
        self.login_url = reverse('login_api')
        self.logout_url = reverse('logout_api')
        self.refresh_url = reverse('token_refresh_api')

        self.email = 'test@gmail.com'
        self.password = 'testpass'

        User.objects.create_user(
            username='Test',
            email=self.email,
            first_name='test',
            last_name='user',
            password=self.password,
            date_of_birth='2000-02-02'
        )

        payload = { 'email': self.email, 'password': self.password }
        login_response = self.client.post(self.login_url, payload, format='json')
        self.access_token = login_response.data['access']
        self.refresh_token = login_response.data['refresh']

    def test_success(self):
        payload = {'refresh': self.refresh_token}
        response = self.client.post(self.logout_url, payload, format='json')

        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_205_RESET_CONTENT])

    def test_blacklisted_token_refresh(self):
        # shouldn't be able to use refresh token after logout
        payload = { 'refresh': self.refresh_token }
        self.client.post(self.logout_url, payload, format='json')

        response = self.client.post(self.refresh_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)

    def test_already_logged_out(self):
        payload = { 'refresh': self.refresh_token }
        self.client.post(self.logout_url, payload, format='json')

        response = self.client.post(self.logout_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_token(self):
        payload = {'refresh': 'invalid.token.string'}
        response = self.client.post(self.logout_url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_refresh_token(self):
        response = self.client.post(self.logout_url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('refresh', response.data)


# ---------------------------------------------------------------------------
# Schedule endpoint tests
# ---------------------------------------------------------------------------
from .models import Company, Department, EmployeeProfile, Schedule

DAY = '2026-10-19'


def make_employee(email='emp@example.com', department=None, first='Eve', last='Worker'):
    """Create a user + employee profile (and a company/department if none is given)."""
    if department is None:
        company = Company.objects.create(name='Test Co')
        department = Department.objects.create(company=company, name='Front')
    user = User.objects.create_user(
        username=email.split('@')[0], email=email, first_name=first, last_name=last,
        password='pass12345', date_of_birth='1995-05-05')
    return EmployeeProfile.objects.create(user=user, company=department.company, department=department)


class ScheduleApiBase(APITestCase):
    def setUp(self):
        self.employee = make_employee()
        self.client.force_authenticate(self.employee.user)
        self.list_url = reverse('schedule-list')

    def payload(self, **overrides):
        data = {'task_name': 'Register', 'employee': self.employee.pk, 'shift_date': DAY,
                'start_time': '09:00', 'end_time': '17:00'}
        data.update(overrides)
        return data

    def make_schedule(self, **overrides):
        fields = {'task_name': 'Register', 'employee': self.employee, 'shift_date': DAY,
                  'start_time': '09:00', 'end_time': '17:00'}
        fields.update(overrides)
        return Schedule.objects.create(**fields)

    def detail_url(self, pk):
        return reverse('schedule-detail', args=[pk])


class ScheduleAuthTests(APITestCase):
    def test_all_endpoints_require_auth(self):
        employee = make_employee()
        s = Schedule.objects.create(task_name='x', employee=employee, shift_date=DAY,
                                    start_time='09:00', end_time='17:00')
        detail = reverse('schedule-detail', args=[s.pk])
        for method, url in [('get', reverse('schedule-list')), ('post', reverse('schedule-list')),
                            ('get', detail), ('put', detail), ('patch', detail), ('delete', detail)]:
            response = getattr(self.client, method)(url, {}, format='json')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, f'{method} {url}')


class ScheduleCreateTests(ScheduleApiBase):
    def test_create(self):
        response = self.client.post(self.list_url, self.payload(notes='Opening'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'scheduled')
        self.assertEqual(response.data['employee'], self.employee.pk)
        self.assertEqual(response.data['employee_name'], 'Eve Worker')
        self.assertEqual(response.data['start_time'], '09:00:00')
        self.assertEqual(response.data['notes'], 'Opening')
        self.assertIn('created_at', response.data)

    def test_create_missing_fields(self):
        response = self.client.post(self.list_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ['task_name', 'employee', 'shift_date', 'start_time', 'end_time']:
            self.assertIn(field, response.data)

    def test_create_end_before_or_equal_start(self):
        for end in ['08:00', '09:00']:
            response = self.client.post(self.list_url, self.payload(end_time=end), format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('end_time', response.data)

    def test_create_bad_formats_and_values(self):
        response = self.client.post(
            self.list_url, self.payload(shift_date='garbage', start_time='nope', status='bogus', task_name='  '),
            format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ['shift_date', 'start_time', 'status', 'task_name']:
            self.assertIn(field, response.data)

    def test_create_unknown_employee(self):
        response = self.client.post(self.list_url, self.payload(employee=9999), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('employee', response.data)

    def test_timestamps_are_read_only(self):
        response = self.client.post(self.list_url, self.payload(created_at='2000-01-01T00:00:00Z'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(response.data['created_at'][:4], '2000')


class ScheduleOverlapTests(ScheduleApiBase):
    def test_overlap_same_employee_rejected(self):
        self.make_schedule()
        response = self.client.post(self.list_url, self.payload(start_time='16:00', end_time='20:00'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_back_to_back_is_allowed(self):
        self.make_schedule()
        response = self.client.post(self.list_url, self.payload(start_time='17:00', end_time='20:00'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_other_employee_or_other_day_is_allowed(self):
        self.make_schedule()
        other = make_employee('other@example.com', department=self.employee.department)
        r1 = self.client.post(self.list_url, self.payload(employee=other.pk), format='json')
        r2 = self.client.post(self.list_url, self.payload(shift_date='2026-10-20'), format='json')
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r2.status_code, status.HTTP_201_CREATED)

    def test_cancelled_rows_do_not_block(self):
        self.make_schedule(status='cancelled')
        response = self.client.post(self.list_url, self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_does_not_clash_with_itself(self):
        s = self.make_schedule()
        response = self.client.patch(self.detail_url(s.pk), {'end_time': '18:00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_update_into_overlap_rejected(self):
        self.make_schedule()
        later = self.make_schedule(start_time='18:00', end_time='20:00')
        response = self.client.patch(self.detail_url(later.pk), {'start_time': '16:00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ScheduleReadUpdateDeleteTests(ScheduleApiBase):
    def test_list_and_filters(self):
        other = make_employee('other@example.com')  # different company/department
        a = self.make_schedule()
        b = self.make_schedule(shift_date='2026-10-21')
        c = self.make_schedule(employee=other, shift_date='2026-10-22', status='completed')

        def ids(**params):
            response = self.client.get(self.list_url, params)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return [row['id'] for row in response.data]

        self.assertEqual(ids(), [a.pk, b.pk, c.pk])
        self.assertEqual(ids(employee=other.pk), [c.pk])
        self.assertEqual(ids(department=self.employee.department_id), [a.pk, b.pk])
        self.assertEqual(ids(status='completed'), [c.pk])
        self.assertEqual(ids(shift_date=DAY), [a.pk])
        self.assertEqual(ids(date_from='2026-10-20', date_to='2026-10-21'), [b.pk])

    def test_bad_filters_return_400(self):
        for params, field in [({'employee': 'abc'}, 'employee'), ({'department': 'x'}, 'department'),
                              ({'status': 'bogus'}, 'status'), ({'shift_date': 'nope'}, 'shift_date'),
                              ({'date_from': ''}, 'date_from'), ({'date_to': '2026-13-45'}, 'date_to')]:
            response = self.client.get(self.list_url, params)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, params)
            self.assertIn(field, response.data)

    def test_retrieve_and_404(self):
        s = self.make_schedule()
        self.assertEqual(self.client.get(self.detail_url(s.pk)).data['task_name'], 'Register')
        self.assertEqual(self.client.get(self.detail_url(9999)).status_code, status.HTTP_404_NOT_FOUND)

    def test_put_and_patch(self):
        s = self.make_schedule()
        put = self.client.put(self.detail_url(s.pk), self.payload(task_name='Drive-thru'), format='json')
        self.assertEqual(put.status_code, status.HTTP_200_OK)
        self.assertEqual(put.data['task_name'], 'Drive-thru')
        patch = self.client.patch(self.detail_url(s.pk), {'status': 'completed'}, format='json')
        self.assertEqual(patch.data['status'], 'completed')

    def test_patch_validates_against_stored_values(self):
        s = self.make_schedule()
        response = self.client.patch(self.detail_url(s.pk), {'end_time': '08:00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_time', response.data)

    def test_delete(self):
        s = self.make_schedule()
        self.assertEqual(self.client.delete(self.detail_url(s.pk)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Schedule.objects.filter(pk=s.pk).exists())
        self.assertEqual(self.client.delete(self.detail_url(s.pk)).status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Compatibility score endpoint tests
# ---------------------------------------------------------------------------
from .models import CompatibilityScore


class CompatibilityApiBase(APITestCase):
    def setUp(self):
        self.a = make_employee('a@example.com', first='Ann', last='A')
        self.b = make_employee('b@example.com', department=self.a.department, first='Bob', last='B')
        self.c = make_employee('c@example.com', department=self.a.department, first='Cy', last='C')
        self.client.force_authenticate(self.a.user)
        self.list_url = reverse('compatibility-list')

    def detail_url(self, pk):
        return reverse('compatibility-detail', args=[pk])

    def make_score(self, x, y, score='7.5'):
        return CompatibilityScore.objects.create(employee_a=x, employee_b=y, score=score)


class CompatibilityAuthTests(CompatibilityApiBase):
    def test_all_endpoints_require_auth(self):
        row = self.make_score(self.a, self.b)
        self.client.force_authenticate(None)
        detail = self.detail_url(row.pk)
        for method, url in [('get', self.list_url), ('post', self.list_url), ('get', detail),
                            ('put', detail), ('patch', detail), ('delete', detail)]:
            response = getattr(self.client, method)(url, {}, format='json')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, f'{method} {url}')


class CompatibilityCreateTests(CompatibilityApiBase):
    def test_create(self):
        response = self.client.post(
            self.list_url, {'employee_a': self.a.pk, 'employee_b': self.b.pk, 'score': '8.25'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['score'], '8.25')
        self.assertEqual(response.data['rated_by'], self.a.user.pk)
        self.assertEqual(response.data['employee_a_name'], 'Ann A')

    def test_response_has_only_diagram_fields(self):
        response = self.client.post(
            self.list_url, {'employee_a': self.a.pk, 'employee_b': self.b.pk, 'score': 5}, format='json')
        self.assertEqual(set(response.data),
                         {'id', 'employee_a', 'employee_a_name', 'employee_b', 'employee_b_name', 'score', 'rated_by'})

    def test_pair_is_stored_in_id_order(self):
        response = self.client.post(
            self.list_url, {'employee_a': self.b.pk, 'employee_b': self.a.pk, 'score': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['employee_a'], min(self.a.pk, self.b.pk))
        self.assertEqual(response.data['employee_b'], max(self.a.pk, self.b.pk))

    def test_reversed_duplicate_rejected(self):
        self.make_score(self.a, self.b)
        response = self.client.post(
            self.list_url, {'employee_a': self.b.pk, 'employee_b': self.a.pk, 'score': 3}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)
        self.assertEqual(CompatibilityScore.objects.count(), 1)

    def test_same_employee_rejected(self):
        response = self.client.post(
            self.list_url, {'employee_a': self.a.pk, 'employee_b': self.a.pk, 'score': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_different_company_rejected(self):
        outsider = make_employee('out@example.com')  # makes its own company
        response = self.client.post(
            self.list_url, {'employee_a': self.a.pk, 'employee_b': outsider.pk, 'score': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_score_validation(self):
        for bad in [-1, 10.01, 11, 'abc', None]:
            response = self.client.post(
                self.list_url, {'employee_a': self.a.pk, 'employee_b': self.b.pk, 'score': bad}, format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
            self.assertIn('score', response.data)
        for good in [0, 10]:
            CompatibilityScore.objects.all().delete()
            response = self.client.post(
                self.list_url, {'employee_a': self.a.pk, 'employee_b': self.b.pk, 'score': good}, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, good)

    def test_missing_and_unknown_fields(self):
        response = self.client.post(self.list_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        for field in ['employee_a', 'employee_b', 'score']:
            self.assertIn(field, response.data)
        response = self.client.post(
            self.list_url, {'employee_a': 9999, 'employee_b': self.b.pk, 'score': 5}, format='json')
        self.assertIn('employee_a', response.data)


class CompatibilityReadUpdateDeleteTests(CompatibilityApiBase):
    def test_list_and_employee_filter(self):
        ab = self.make_score(self.a, self.b)
        bc = self.make_score(self.b, self.c)
        ids = lambda **p: sorted(r['id'] for r in self.client.get(self.list_url, p).data)
        self.assertEqual(ids(), sorted([ab.pk, bc.pk]))
        self.assertEqual(ids(employee=self.a.pk), [ab.pk])
        self.assertEqual(ids(employee=self.b.pk), sorted([ab.pk, bc.pk]))  # matches either side
        self.assertEqual(self.client.get(self.list_url, {'employee': 'x'}).status_code, 400)

    def test_retrieve_and_404(self):
        row = self.make_score(self.a, self.b)
        self.assertEqual(self.client.get(self.detail_url(row.pk)).data['score'], '7.50')
        self.assertEqual(self.client.get(self.detail_url(9999)).status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_score(self):
        row = self.make_score(self.a, self.b)
        response = self.client.patch(self.detail_url(row.pk), {'score': 2}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['score'], '2.00')
        bad = self.client.patch(self.detail_url(row.pk), {'score': 99}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_same_pair_in_either_order_ok(self):
        row = self.make_score(self.a, self.b)
        response = self.client.put(
            self.detail_url(row.pk), {'employee_a': self.b.pk, 'employee_b': self.a.pk, 'score': 4}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cannot_change_the_pair(self):
        row = self.make_score(self.a, self.b)
        response = self.client.patch(self.detail_url(row.pk), {'employee_b': self.c.pk}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete(self):
        row = self.make_score(self.a, self.b)
        self.assertEqual(self.client.delete(self.detail_url(row.pk)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(CompatibilityScore.objects.count(), 0)

    def test_model_save_normalises_order(self):
        row = self.make_score(self.c, self.a)
        self.assertLess(row.employee_a_id, row.employee_b_id)


# ---------------------------------------------------------------------------
# Availability slot, time-off request and project endpoint tests
# ---------------------------------------------------------------------------
from django.test import override_settings

from .models import AvailabilitySlot, Project, TimeOffRequest

FAST_HASHER = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


@FAST_HASHER
class EmployeeApiBase(APITestCase):
    """Shared setup: two employees in one department, one outsider, logged in as the first."""
    url_name = None

    def setUp(self):
        self.emp = make_employee('emp@example.com', first='Eve', last='Worker')
        self.other = make_employee('other@example.com', department=self.emp.department, first='Sam', last='Mate')
        self.outsider = make_employee('out@example.com', first='Out', last='Sider')  # own company/department
        self.client.force_authenticate(self.emp.user)
        self.list_url = reverse(f'{self.url_name}-list')

    def detail_url(self, pk):
        return reverse(f'{self.url_name}-detail', args=[pk])

    def assert_requires_auth(self, row):
        self.client.force_authenticate(None)
        detail = self.detail_url(row.pk)
        for method, url in [('get', self.list_url), ('post', self.list_url), ('get', detail),
                            ('put', detail), ('patch', detail), ('delete', detail)]:
            response = getattr(self.client, method)(url, {}, format='json')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, f'{method} {url}')

    def list_ids(self, **params):
        response = self.client.get(self.list_url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [row['id'] for row in response.data]


# --- availability ----------------------------------------------------------------------------

class AvailabilityTests(EmployeeApiBase):
    url_name = 'availability'

    def payload(self, **overrides):
        data = {'employee': self.emp.pk, 'day_of_week': 0, 'start_time': '09:00', 'end_time': '17:00'}
        data.update(overrides)
        return data

    def make(self, **overrides):
        fields = {'employee': self.emp, 'day_of_week': 0, 'start_time': '09:00', 'end_time': '17:00'}
        fields.update(overrides)
        return AvailabilitySlot.objects.create(**fields)

    def test_requires_auth(self):
        self.assert_requires_auth(self.make())

    def test_create(self):
        response = self.client.post(self.list_url, self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['day_name'], 'Monday')
        self.assertEqual(response.data['employee_name'], 'Eve Worker')
        self.assertEqual(response.data['start_time'], '09:00:00')

    def test_create_missing_and_invalid(self):
        response = self.client.post(self.list_url, {}, format='json')
        for field in ['employee', 'day_of_week', 'start_time', 'end_time']:
            self.assertIn(field, response.data)
        for bad in [7, -1, 'abc']:
            response = self.client.post(self.list_url, self.payload(day_of_week=bad), format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, bad)
            self.assertIn('day_of_week', response.data)
        response = self.client.post(self.list_url, self.payload(employee=9999), format='json')
        self.assertIn('employee', response.data)

    def test_end_must_be_after_start(self):
        for end in ['08:00', '09:00']:
            response = self.client.post(self.list_url, self.payload(end_time=end), format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('end_time', response.data)

    def test_overlap_rules(self):
        self.make()
        overlap = self.client.post(self.list_url, self.payload(start_time='16:00', end_time='20:00'), format='json')
        self.assertEqual(overlap.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', overlap.data)
        for ok in [self.payload(start_time='17:00', end_time='20:00'),      # touching
                   self.payload(day_of_week=1),                              # other day
                   self.payload(employee=self.other.pk)]:                    # other employee
            self.assertEqual(self.client.post(self.list_url, ok, format='json').status_code, 201)

    def test_update_does_not_clash_with_itself(self):
        slot = self.make()
        response = self.client.patch(self.detail_url(slot.pk), {'end_time': '18:00'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bad = self.client.patch(self.detail_url(slot.pk), {'end_time': '08:00'}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_filters(self):
        a = self.make()
        b = self.make(day_of_week=2)
        c = self.make(employee=self.outsider, day_of_week=2)
        self.assertEqual(self.list_ids(), [a.pk, b.pk, c.pk])
        self.assertEqual(self.list_ids(employee=self.emp.pk), [a.pk, b.pk])
        self.assertEqual(self.list_ids(department=self.emp.department_id), [a.pk, b.pk])
        self.assertEqual(self.list_ids(day_of_week=2), [b.pk, c.pk])
        for params in [{'employee': 'x'}, {'department': 'x'}, {'day_of_week': 'x'}, {'day_of_week': 9}]:
            self.assertEqual(self.client.get(self.list_url, params).status_code, 400, params)

    def test_retrieve_put_delete_404(self):
        slot = self.make()
        self.assertEqual(self.client.get(self.detail_url(slot.pk)).data['day_of_week'], 0)
        self.assertEqual(self.client.get(self.detail_url(9999)).status_code, status.HTTP_404_NOT_FOUND)
        put = self.client.put(self.detail_url(slot.pk), self.payload(day_of_week=3), format='json')
        self.assertEqual(put.data['day_name'], 'Thursday')
        self.assertEqual(self.client.delete(self.detail_url(slot.pk)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(AvailabilitySlot.objects.count(), 0)


# --- time off --------------------------------------------------------------------------------

class TimeOffTests(EmployeeApiBase):
    url_name = 'time-off'

    def payload(self, **overrides):
        data = {'employee': self.emp.pk, 'start_date': '2026-11-02', 'end_date': '2026-11-04', 'reason': 'Trip'}
        data.update(overrides)
        return data

    def make(self, **overrides):
        fields = {'employee': self.emp, 'start_date': '2026-11-02', 'end_date': '2026-11-04'}
        fields.update(overrides)
        return TimeOffRequest.objects.create(**fields)

    def test_requires_auth(self):
        self.assert_requires_auth(self.make())

    def test_create_starts_pending(self):
        response = self.client.post(self.list_url, self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'pending')
        self.assertEqual(response.data['employee_name'], 'Eve Worker')
        self.assertIn('requested_at', response.data)

    def test_reason_is_optional_and_single_day_allowed(self):
        response = self.client.post(
            self.list_url, {'employee': self.emp.pk, 'start_date': '2026-11-02', 'end_date': '2026-11-02'},
            format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_cannot_create_as_approved(self):
        response = self.client.post(self.list_url, self.payload(status='approved'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', response.data)

    def test_create_missing_and_invalid(self):
        response = self.client.post(self.list_url, {}, format='json')
        for field in ['employee', 'start_date', 'end_date']:
            self.assertIn(field, response.data)
        response = self.client.post(self.list_url, self.payload(start_date='nope'), format='json')
        self.assertIn('start_date', response.data)
        response = self.client.post(self.list_url, self.payload(employee=9999), format='json')
        self.assertIn('employee', response.data)

    def test_end_before_start(self):
        response = self.client.post(self.list_url, self.payload(end_date='2026-11-01'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end_date', response.data)

    def test_overlap_rules(self):
        self.make()
        overlap = self.client.post(self.list_url, self.payload(start_date='2026-11-04', end_date='2026-11-06'),
                                   format='json')
        self.assertEqual(overlap.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', overlap.data)
        for ok in [self.payload(start_date='2026-11-05', end_date='2026-11-06'),  # day after
                   self.payload(employee=self.other.pk)]:                          # other employee
            self.assertEqual(self.client.post(self.list_url, ok, format='json').status_code, 201)

    def test_denied_requests_do_not_block(self):
        self.make(status='denied')
        response = self.client.post(self.list_url, self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_approve_and_deny_via_patch(self):
        req = self.make()
        approved = self.client.patch(self.detail_url(req.pk), {'status': 'approved'}, format='json')
        self.assertEqual(approved.status_code, status.HTTP_200_OK)
        self.assertEqual(approved.data['status'], 'approved')
        denied = self.client.patch(self.detail_url(req.pk), {'status': 'denied'}, format='json')
        self.assertEqual(denied.data['status'], 'denied')
        bad = self.client.patch(self.detail_url(req.pk), {'status': 'maybe'}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', bad.data)

    def test_reinstating_a_denied_request_rechecks_overlap(self):
        denied = self.make(status='denied')
        self.make(start_date='2026-11-03', end_date='2026-11-03')
        response = self.client.patch(self.detail_url(denied.pk), {'status': 'pending'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_validates_against_stored_dates(self):
        req = self.make()
        response = self.client.patch(self.detail_url(req.pk), {'end_date': '2026-11-01'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requested_at_is_read_only(self):
        response = self.client.post(self.list_url, self.payload(requested_at='2000-01-01T00:00:00Z'), format='json')
        self.assertNotEqual(response.data['requested_at'][:4], '2000')

    def test_list_filters(self):
        a = self.make()
        b = self.make(start_date='2026-11-10', end_date='2026-11-12', status='approved')
        c = self.make(employee=self.outsider, start_date='2026-11-03', end_date='2026-11-03')
        self.assertEqual(self.list_ids(), [a.pk, c.pk, b.pk])
        self.assertEqual(self.list_ids(employee=self.emp.pk), [a.pk, b.pk])
        self.assertEqual(self.list_ids(department=self.emp.department_id), [a.pk, b.pk])
        self.assertEqual(self.list_ids(status='approved'), [b.pk])
        # overlap window: Nov 4 - Nov 10 touches a (ends 4th) and b (starts 10th), not c (3rd)
        self.assertEqual(self.list_ids(date_from='2026-11-04', date_to='2026-11-10'), [a.pk, b.pk])
        for params in [{'employee': 'x'}, {'department': 'x'}, {'status': 'bogus'},
                       {'date_from': 'nope'}, {'date_to': '2026-13-45'}]:
            self.assertEqual(self.client.get(self.list_url, params).status_code, 400, params)

    def test_retrieve_put_delete_404(self):
        req = self.make()
        self.assertEqual(self.client.get(self.detail_url(req.pk)).data['reason'], '')
        self.assertEqual(self.client.get(self.detail_url(9999)).status_code, status.HTTP_404_NOT_FOUND)
        put = self.client.put(self.detail_url(req.pk), self.payload(reason='Updated'), format='json')
        self.assertEqual(put.status_code, status.HTTP_200_OK)
        self.assertEqual(put.data['reason'], 'Updated')
        self.assertEqual(self.client.delete(self.detail_url(req.pk)).status_code, status.HTTP_204_NO_CONTENT)


# --- projects --------------------------------------------------------------------------------

class ProjectTests(EmployeeApiBase):
    url_name = 'project'

    def payload(self, **overrides):
        data = {'company': self.emp.company_id, 'name': 'Remodel'}
        data.update(overrides)
        return data

    def make(self, **overrides):
        fields = {'company': self.emp.company, 'name': 'Remodel'}
        fields.update(overrides)
        return Project.objects.create(**fields)

    def test_requires_auth(self):
        self.assert_requires_auth(self.make())

    def test_create_with_defaults(self):
        response = self.client.post(self.list_url, self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['priority'], 'medium')
        self.assertTrue(response.data['is_active'])
        self.assertIsNone(response.data['department'])
        self.assertEqual(response.data['description'], '')

    def test_create_full(self):
        response = self.client.post(
            self.list_url,
            self.payload(department=self.emp.department_id, description='Big job', priority='high', is_active=False),
            format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['priority'], 'high')
        self.assertFalse(response.data['is_active'])

    def test_create_missing_and_invalid(self):
        response = self.client.post(self.list_url, {}, format='json')
        self.assertIn('company', response.data)
        self.assertIn('name', response.data)
        response = self.client.post(self.list_url, self.payload(name='   ', priority='urgent'), format='json')
        self.assertIn('name', response.data)
        self.assertIn('priority', response.data)
        response = self.client.post(self.list_url, self.payload(company=9999), format='json')
        self.assertIn('company', response.data)

    def test_department_must_belong_to_company(self):
        response = self.client.post(
            self.list_url, self.payload(department=self.outsider.department_id), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.data)
        project = self.make()
        response = self.client.patch(self.detail_url(project.pk),
                                     {'department': self.outsider.department_id}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_filters(self):
        a = self.make(name='A', priority='high')
        b = self.make(name='B', department=self.emp.department, is_active=False)
        c = self.make(name='C', company=self.outsider.company, department=self.outsider.department)
        self.assertEqual(self.list_ids(), [a.pk, b.pk, c.pk])
        self.assertEqual(self.list_ids(company=self.emp.company_id), [a.pk, b.pk])
        self.assertEqual(self.list_ids(department=self.emp.department_id), [b.pk])
        self.assertEqual(self.list_ids(priority='high'), [a.pk])
        self.assertEqual(self.list_ids(is_active='false'), [b.pk])
        self.assertEqual(self.list_ids(is_active='TRUE'), [a.pk, c.pk])
        for params in [{'company': 'x'}, {'department': 'x'}, {'priority': 'urgent'}, {'is_active': 'maybe'}]:
            self.assertEqual(self.client.get(self.list_url, params).status_code, 400, params)

    def test_retrieve_update_delete_404(self):
        project = self.make()
        self.assertEqual(self.client.get(self.detail_url(project.pk)).data['name'], 'Remodel')
        self.assertEqual(self.client.get(self.detail_url(9999)).status_code, status.HTTP_404_NOT_FOUND)
        patch = self.client.patch(self.detail_url(project.pk), {'is_active': False, 'priority': 'low'}, format='json')
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertFalse(patch.data['is_active'])
        put = self.client.put(self.detail_url(project.pk), self.payload(name='Renamed'), format='json')
        self.assertEqual(put.data['name'], 'Renamed')
        self.assertEqual(self.client.delete(self.detail_url(project.pk)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Project.objects.count(), 0)

    def test_deleting_department_keeps_project(self):
        project = self.make(department=self.emp.department)
        self.other.delete()
        self.emp.delete()
        self.emp.department.delete()
        project.refresh_from_db()
        self.assertIsNone(project.department)
