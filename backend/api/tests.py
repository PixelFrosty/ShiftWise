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
# Schedule / Shift endpoint tests
# ---------------------------------------------------------------------------
from datetime import datetime, timezone as dt_timezone

from .models import Schedule, Shift


def make_user(email='mgr@example.com'):
    return User.objects.create_user(
        username='mgr', email=email, first_name='m', last_name='gr',
        password='pass12345', date_of_birth='1990-01-01')


MONDAY = '2026-10-19'  # a Monday


def iso(day, hour):
    """ISO timestamp (UTC) on 2026-10-<day> at <hour>:00."""
    return datetime(2026, 10, day, hour, tzinfo=dt_timezone.utc).isoformat()


class ScheduleApiBase(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(self.user)
        self.list_url = reverse('schedule-list')

    def make_schedule(self, name='Week A', week_start=MONDAY):
        return Schedule.objects.create(name=name, week_start=week_start, created_by=self.user)

    def detail_url(self, pk):
        return reverse('schedule-detail', args=[pk])


class ScheduleAuthTests(APITestCase):
    def test_all_endpoints_require_auth(self):
        user = make_user()
        s = Schedule.objects.create(name='x', week_start=MONDAY, created_by=user)
        sh = Shift.objects.create(schedule=s, start=iso(19, 9), end=iso(19, 17))
        urls = [
            ('get', reverse('schedule-list')), ('post', reverse('schedule-list')),
            ('get', reverse('schedule-detail', args=[s.pk])),
            ('put', reverse('schedule-detail', args=[s.pk])),
            ('patch', reverse('schedule-detail', args=[s.pk])),
            ('delete', reverse('schedule-detail', args=[s.pk])),
            ('get', reverse('shift-list', args=[s.pk])), ('post', reverse('shift-list', args=[s.pk])),
            ('get', reverse('shift-detail', args=[s.pk, sh.pk])),
            ('patch', reverse('shift-detail', args=[s.pk, sh.pk])),
            ('delete', reverse('shift-detail', args=[s.pk, sh.pk])),
        ]
        for method, url in urls:
            response = getattr(self.client, method)(url, {}, format='json')
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, f'{method} {url}')


class ScheduleCrudTests(ScheduleApiBase):
    def test_create(self):
        response = self.client.post(self.list_url, {'name': 'Week A', 'week_start': MONDAY}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'draft')
        self.assertEqual(response.data['created_by'], self.user.pk)
        self.assertEqual(response.data['shift_count'], 0)

    def test_create_ignores_created_by_and_validates_status(self):
        response = self.client.post(
            self.list_url, {'name': 'W', 'week_start': MONDAY, 'created_by': 999}, format='json')
        self.assertEqual(response.data['created_by'], self.user.pk)
        bad = self.client.post(
            self.list_url, {'name': 'W', 'week_start': MONDAY, 'status': 'nope'}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('status', bad.data)

    def test_create_missing_fields(self):
        response = self.client.post(self.list_url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)
        self.assertIn('week_start', response.data)

    def test_create_week_start_must_be_monday(self):
        response = self.client.post(self.list_url, {'name': 'W', 'week_start': '2026-10-20'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('week_start', response.data)

    def test_create_bad_date_and_blank_name(self):
        response = self.client.post(self.list_url, {'name': '   ', 'week_start': 'garbage'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('week_start', response.data)
        self.assertIn('name', response.data)

    def test_list_and_filters(self):
        self.make_schedule('A', MONDAY)
        self.make_schedule('B', '2026-10-26')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        filtered = self.client.get(self.list_url, {'week_start': '2026-10-26'})
        self.assertEqual([s['name'] for s in filtered.data], ['B'])
        bad = self.client.get(self.list_url, {'week_start': 'nope'})
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_includes_shifts(self):
        s = self.make_schedule()
        Shift.objects.create(schedule=s, start=iso(19, 9), end=iso(19, 17), headcount_needed=2)
        response = self.client.get(self.detail_url(s.pk))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['shifts']), 1)
        self.assertEqual(response.data['shifts'][0]['headcount_needed'], 2)
        self.assertEqual(response.data['shift_count'], 1)

    def test_retrieve_missing_is_404(self):
        self.assertEqual(self.client.get(self.detail_url(9999)).status_code, status.HTTP_404_NOT_FOUND)

    def test_update_put_and_patch(self):
        s = self.make_schedule()
        put = self.client.put(self.detail_url(s.pk), {'name': 'Renamed', 'week_start': MONDAY}, format='json')
        self.assertEqual(put.status_code, status.HTTP_200_OK)
        self.assertEqual(put.data['name'], 'Renamed')
        patch = self.client.patch(self.detail_url(s.pk), {'status': 'published'}, format='json')
        self.assertEqual(patch.status_code, status.HTTP_200_OK)
        self.assertEqual(patch.data['status'], 'published')

    def test_update_invalid(self):
        s = self.make_schedule()
        response = self.client.patch(self.detail_url(s.pk), {'week_start': '2026-10-21'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_move_week_with_shifts(self):
        s = self.make_schedule()
        Shift.objects.create(schedule=s, start=iso(19, 9), end=iso(19, 17))
        response = self.client.patch(self.detail_url(s.pk), {'week_start': '2026-10-26'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('week_start', response.data)

    def test_delete_cascades_shifts(self):
        s = self.make_schedule()
        Shift.objects.create(schedule=s, start=iso(19, 9), end=iso(19, 17))
        response = self.client.delete(self.detail_url(s.pk))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Schedule.objects.filter(pk=s.pk).exists())
        self.assertEqual(Shift.objects.count(), 0)


class ShiftCrudTests(ScheduleApiBase):
    def setUp(self):
        super().setUp()
        self.schedule = self.make_schedule()
        self.url = reverse('shift-list', args=[self.schedule.pk])

    def shift_url(self, pk):
        return reverse('shift-detail', args=[self.schedule.pk, pk])

    def test_create(self):
        payload = {'start': iso(19, 9), 'end': iso(19, 17), 'headcount_needed': 3, 'notes': 'Opening'}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['schedule'], self.schedule.pk)
        self.assertEqual(response.data['headcount_needed'], 3)

    def test_create_defaults_headcount_to_one(self):
        response = self.client.post(self.url, {'start': iso(19, 9), 'end': iso(19, 17)}, format='json')
        self.assertEqual(response.data['headcount_needed'], 1)

    def test_create_end_before_start(self):
        response = self.client.post(self.url, {'start': iso(19, 17), 'end': iso(19, 9)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('end', response.data)

    def test_create_outside_schedule_week(self):
        response = self.client.post(self.url, {'start': iso(26, 9), 'end': iso(26, 17)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_create_bad_headcount_and_missing_fields(self):
        response = self.client.post(self.url, {'start': iso(19, 9), 'end': iso(19, 17), 'headcount_needed': 0},
                                    format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('headcount_needed', response.data)
        response = self.client.post(self.url, {}, format='json')
        self.assertIn('start', response.data)
        self.assertIn('end', response.data)

    def test_list_and_retrieve(self):
        shift = Shift.objects.create(schedule=self.schedule, start=iso(19, 9), end=iso(19, 17))
        self.assertEqual(len(self.client.get(self.url).data), 1)
        self.assertEqual(self.client.get(self.shift_url(shift.pk)).data['id'], shift.pk)

    def test_unknown_schedule_is_404(self):
        self.assertEqual(self.client.get(reverse('shift-list', args=[9999])).status_code, 404)
        payload = {'start': iso(19, 9), 'end': iso(19, 17)}
        self.assertEqual(self.client.post(reverse('shift-list', args=[9999]), payload, format='json').status_code, 404)

    def test_shift_under_wrong_schedule_is_404(self):
        other = self.make_schedule('Other', '2026-10-26')
        shift = Shift.objects.create(schedule=other, start=iso(26, 9), end=iso(26, 17))
        self.assertEqual(self.client.get(self.shift_url(shift.pk)).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(self.shift_url(shift.pk)).status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_validates_against_stored_values(self):
        shift = Shift.objects.create(schedule=self.schedule, start=iso(19, 9), end=iso(19, 17))
        # moving only `end` before the stored `start` must fail
        response = self.client.patch(self.shift_url(shift.pk), {'end': iso(19, 8)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        ok = self.client.patch(self.shift_url(shift.pk), {'headcount_needed': 4}, format='json')
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data['headcount_needed'], 4)

    def test_put(self):
        shift = Shift.objects.create(schedule=self.schedule, start=iso(19, 9), end=iso(19, 17))
        response = self.client.put(self.shift_url(shift.pk),
                                   {'start': iso(20, 9), 'end': iso(20, 13), 'headcount_needed': 2}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete(self):
        shift = Shift.objects.create(schedule=self.schedule, start=iso(19, 9), end=iso(19, 17))
        self.assertEqual(self.client.delete(self.shift_url(shift.pk)).status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Shift.objects.count(), 0)