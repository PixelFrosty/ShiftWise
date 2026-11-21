from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status

from django.urls import reverse

# Create your tests here.
# pyright: reportAttributeAccessIssue=false

from .admin import EmployeeProfileForm
from .models import Company, Department, EmployeeProfile, User, SchedulePublication
from .serializers import EmployeeProfileSerializer, TaskSerializer

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

    def test_user_can_have_multiple_employee_profiles(self):
        user = User.objects.create_user(
            username='multi',
            email='multi@example.com',
            first_name='Multi',
            last_name='Jobs',
            password='testpassword',
            date_of_birth='1990-01-01'
        )
        company1 = Company.objects.create(name='Company 1')
        dept1 = Department.objects.create(company=company1, name='Dept 1')
        company2 = Company.objects.create(name='Company 2')
        dept2 = Department.objects.create(company=company2, name='Dept 2')

        job1 = EmployeeProfile.objects.create(user=user, company=company1, department=dept1, position='Cashier')
        job2 = EmployeeProfile.objects.create(user=user, company=company2, department=dept2, position='Stocker')

        self.assertEqual(user.employee_profiles.count(), 2)
        self.assertIn(job1, user.employee_profiles.all())
        self.assertIn(job2, user.employee_profiles.all())
        self.assertEqual(user.employee_profile, job1)


class EmployeeProfileDepartmentCompanyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='worker', email='worker@example.com', first_name='Work', last_name='Er',
            password='pass', date_of_birth='1990-01-01')
        self.company1 = Company.objects.create(name='Company 1')
        self.dept1 = Department.objects.create(company=self.company1, name='Dept 1')
        self.company2 = Company.objects.create(name='Company 2')
        self.dept2 = Department.objects.create(company=self.company2, name='Dept 2')

    def test_matching_company_and_department_succeeds(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        self.assertEqual(profile.company, self.company1)
        self.assertEqual(profile.department, self.dept1)

    def test_mismatched_department_and_company_rejected_on_create(self):
        with self.assertRaises(ValidationError) as ctx:
            EmployeeProfile.objects.create(
                user=self.user, company=self.company1, department=self.dept2, position='Cashier')
        self.assertIn('department', ctx.exception.message_dict)

    def test_mismatched_department_and_company_rejected_on_save(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        profile.department = self.dept2
        with self.assertRaises(ValidationError) as ctx:
            profile.save()
        self.assertIn('department', ctx.exception.message_dict)

    def test_admin_form_filters_department_queryset_by_company(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        form = EmployeeProfileForm(instance=profile)
        self.assertIn(self.dept1, form.fields['department'].queryset)
        self.assertNotIn(self.dept2, form.fields['department'].queryset)

    def test_admin_form_rejects_mismatched_department(self):
        data = {
            'user': self.user.pk,
            'company': self.company1.pk,
            'department': self.dept2.pk,
            'role': EmployeeProfile.Role.EMPLOYEE,
            'position': 'Cashier',
        }
        form = EmployeeProfileForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('department', form.errors)

    def test_serializer_rejects_mismatched_department(self):
        data = {
            'user': self.user.pk,
            'company': self.company1.pk,
            'department': self.dept2.pk,
            'role': 'employee',
        }
        serializer = EmployeeProfileSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('department', serializer.errors)

    def test_company_cannot_be_changed_on_existing_profile(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        profile.company = self.company2
        with self.assertRaises(ValidationError) as ctx:
            profile.save()
        self.assertIn('company', ctx.exception.message_dict)

    def test_profile_can_update_other_fields_without_changing_company(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        dept1_b = Department.objects.create(company=self.company1, name='Dept 1B')
        profile.position = 'Lead Cashier'
        profile.department = dept1_b
        profile.role = EmployeeProfile.Role.MANAGER
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(profile.position, 'Lead Cashier')
        self.assertEqual(profile.department, dept1_b)
        self.assertEqual(profile.role, EmployeeProfile.Role.MANAGER)
        self.assertEqual(profile.company, self.company1)

    def test_admin_form_disables_company_for_existing_profile(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        form = EmployeeProfileForm(instance=profile)
        self.assertTrue(form.fields['company'].disabled)

    def test_admin_form_rejects_tampered_company_change(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        data = {
            'user': self.user.pk,
            'company': self.company2.pk,
            'department': self.dept2.pk,
            'role': EmployeeProfile.Role.EMPLOYEE,
            'position': 'Cashier',
        }
        form = EmployeeProfileForm(instance=profile, data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('company', form.errors)

    def test_serializer_rejects_company_change_on_existing_profile(self):
        profile = EmployeeProfile.objects.create(
            user=self.user, company=self.company1, department=self.dept1, position='Cashier')
        serializer = EmployeeProfileSerializer(instance=profile, data={'company': self.company2.pk}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('company', serializer.errors)

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


class SignupCheckApiTests(APITestCase):
    def setUp(self):
        self.url = reverse('signup_check')
        self.user = User.objects.create_user(
            username='ExistingUser',
            email='existing@example.com',
            first_name='Existing',
            last_name='User',
            password='testpassword123',
            date_of_birth='1995-05-05'
        )

    def test_taken_when_both_username_and_email_match(self):
        response = self.client.get(
            self.url,
            {'username': 'ExistingUser', 'email': 'existing@example.com'}
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {'taken': True, 'message': 'Email or username has already been taken.'}
        )

    def test_taken_when_only_email_matches(self):
        response = self.client.get(
            self.url,
            {'username': 'fresh_user', 'email': 'existing@example.com'}
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {'taken': True, 'message': 'Email or username has already been taken.'}
        )

    def test_taken_when_only_username_matches(self):
        response = self.client.get(
            self.url,
            {'username': 'ExistingUser', 'email': 'fresh_email@example.com'}
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {'taken': True, 'message': 'Email or username has already been taken.'}
        )

    def test_taken_case_insensitive(self):
        response = self.client.get(
            self.url,
            {'username': 'EXISTINGUSER', 'email': 'EXISTING@EXAMPLE.COM'}
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data,
            {'taken': True, 'message': 'Email or username has already been taken.'}
        )

    def test_available_when_neither_matches(self):
        response = self.client.get(
            self.url,
            {'username': 'new_user', 'email': 'new_email@example.com'}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data,
            {'taken': False, 'message': 'Email and username are available.'}
        )

    def test_missing_email_returns_400(self):
        response = self.client.get(
            self.url,
            {'username': 'brand_new_username'}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'detail': "Both 'email' and 'username' must be provided."})

    def test_missing_username_returns_400(self):
        response = self.client.get(
            self.url,
            {'email': 'unique_email@example.com'}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'detail': "Both 'email' and 'username' must be provided."})

    def test_empty_email_returns_400(self):
        response = self.client.get(
            self.url,
            {'username': 'brand_new_username', 'email': '   '}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'detail': "Both 'email' and 'username' must be provided."})

    def test_empty_username_returns_400(self):
        response = self.client.get(
            self.url,
            {'username': '   ', 'email': 'unique_email@example.com'}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data, {'detail': "Both 'email' and 'username' must be provided."})

    def test_empty_params_returns_400(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('detail', response.data)

        response = self.client.get(
            self.url,
            {'username': '   ', 'email': '   '}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_post_method_not_allowed(self):
        response = self.client.post(
            self.url,
            {'username': 'ExistingUser', 'email': 'existing@example.com'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_endpoint_accessible_unauthenticated(self):
        self.client.credentials()  # Ensure no auth header is set
        response = self.client.get(
            self.url,
            {'username': 'any_user', 'email': 'any@example.com'}
        )
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


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

    def test_schedule_inherits_company_and_department_from_task(self):
        task = Task.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            name='Kitchen Duty'
        )
        s = Schedule.objects.create(
            task=task,
            task_name=task.name,
            employee=self.employee,
            shift_date=DAY,
            start_time='10:00',
            end_time='14:00'
        )
        self.assertEqual(s.company, self.employee.company)
        self.assertEqual(s.department, self.employee.department)

    def test_schedule_attached_company_and_department_without_task(self):
        s = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Custom Task',
            employee=self.employee,
            shift_date=DAY,
            start_time='10:00',
            end_time='14:00'
        )
        self.assertEqual(s.company, self.employee.company)
        self.assertEqual(s.department, self.employee.department)


class ScheduleOverlapTests(ScheduleApiBase):
    def test_overlap_same_employee_rejected(self):
        self.make_schedule()
        response = self.client.post(self.list_url, self.payload(start_time='16:00', end_time='20:00'), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)

    def test_overlap_different_profile_same_user_rejected(self):
        self.make_schedule()
        second_job = EmployeeProfile.objects.create(
            user=self.employee.user, company=self.employee.company, department=self.employee.department,
            position='Second Job')
        response = self.client.post(
            self.list_url, self.payload(employee=second_job.pk, start_time='16:00', end_time='20:00'), format='json')
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

    def test_same_user_different_profile_rejected(self):
        second_job = EmployeeProfile.objects.create(
            user=self.a.user, company=self.a.company, department=self.a.department, position='Second Job')
        response = self.client.post(
            self.list_url, {'employee_a': self.a.pk, 'employee_b': second_job.pk, 'score': 5}, format='json')
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


# Shift Generator Tests
import datetime
from .models import CompanyHours, Skill, Task
from .services.shift_generator import ShiftGeneratorService

class ShiftGeneratorTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='schedmanager', email='schedmanager@example.com',
            first_name='Schedule', last_name='Manager', password='pass', date_of_birth='1990-01-01'
        )
        self.client.force_authenticate(user=self.user)
        self.company = Company.objects.create(name='Test Retail Co')
        self.department = Department.objects.create(company=self.company, name='Operations')
        self.employee = EmployeeProfile.objects.create(
            user=self.user, company=self.company, department=self.department,
            role=EmployeeProfile.Role.EMPLOYEE, max_weekly_hours=40.0
        )

        # Operating hours: Monday to Friday 09:00 - 17:00 (8h each), closed weekends
        self.hours = CompanyHours.objects.create(
            company=self.company,
            monday_start=datetime.time(9, 0), monday_end=datetime.time(17, 0),
            tuesday_start=datetime.time(9, 0), tuesday_end=datetime.time(17, 0),
            wednesday_start=datetime.time(9, 0), wednesday_end=datetime.time(17, 0),
            thursday_start=datetime.time(9, 0), thursday_end=datetime.time(17, 0),
            friday_start=datetime.time(9, 0), friday_end=datetime.time(17, 0),
            saturday_start=None, saturday_end=None,
            sunday_start=None, sunday_end=None,
        )

        self.project = Project.objects.create(
            company=self.company, department=self.department, name='Store Front',
            priority=Project.Priority.HIGH, is_active=True
        )
        self.week_start = datetime.date(2026, 11, 16)  # A Monday

    def test_recurring_task_generates_for_every_open_day(self):
        Task.objects.create(
            company=self.company, project=self.project, name='Register Lead',
            is_recurring=True, required_people=1, duration_hours=8.0,
            preferred_window=Task.PreferredWindow.OPEN_TO_CLOSE
        )
        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        self.assertEqual(res['total_shifts_generated'], 5)
        self.assertEqual(res['unassigned_shifts'], 5)
        self.assertEqual(res['pre_assigned_shifts'], 0)
        # Verify shifts exist Mon-Fri (Nov 16 - Nov 20)
        dates = Schedule.objects.filter(task__company=self.company).values_list('shift_date', flat=True)
        self.assertEqual(len(set(dates)), 5)
        for s in Schedule.objects.all():
            self.assertEqual(s.start_time, datetime.time(9, 0))
            self.assertEqual(s.end_time, datetime.time(17, 0))
            self.assertIsNone(s.employee)

    def test_multi_person_preassigned_task(self):
        Task.objects.create(
            company=self.company, project=self.project, name='Inventory Audit',
            is_recurring=False, required_people=3, duration_hours=4.0,
            employee=self.employee, preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        self.assertEqual(res['total_shifts_generated'], 3)
        self.assertEqual(res['pre_assigned_shifts'], 1)
        self.assertEqual(res['unassigned_shifts'], 2)

        shifts = list(Schedule.objects.all().order_by('id'))
        self.assertEqual(len(shifts), 3)
        self.assertEqual(shifts[0].employee, self.employee)
        self.assertIsNone(shifts[1].employee)
        self.assertIsNone(shifts[2].employee)
        for s in shifts:
            self.assertEqual(s.start_time, datetime.time(9, 0))
            self.assertEqual(s.end_time, datetime.time(13, 0))

    def test_preferred_windows_intra_day(self):
        # 1. Beginning of day (2h) -> 09:00 - 11:00
        t1 = Task.objects.create(
            company=self.company, project=self.project, name='Opening Prep',
            is_recurring=False, required_people=1, duration_hours=2.0,
            preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        # 2. Mid day (4h) -> midpoint is 13:00 -> 11:00 - 15:00
        t2 = Task.objects.create(
            company=self.company, project=self.project, name='Lunch Rush',
            is_recurring=False, required_people=1, duration_hours=4.0,
            preferred_window=Task.PreferredWindow.MID_DAY
        )
        # 3. End of day (2h) -> 15:00 - 17:00
        t3 = Task.objects.create(
            company=self.company, project=self.project, name='Closing Sweep',
            is_recurring=False, required_people=1, duration_hours=2.0,
            preferred_window=Task.PreferredWindow.END_OF_DAY
        )

        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        service.generate()

        s1 = Schedule.objects.get(task=t1)
        self.assertEqual(s1.start_time, datetime.time(9, 0))
        self.assertEqual(s1.end_time, datetime.time(11, 0))

        s2 = Schedule.objects.get(task=t2)
        self.assertEqual(s2.start_time, datetime.time(11, 0))
        self.assertEqual(s2.end_time, datetime.time(15, 0))

        s3 = Schedule.objects.get(task=t3)
        self.assertEqual(s3.start_time, datetime.time(15, 0))
        self.assertEqual(s3.end_time, datetime.time(17, 0))

    def test_multi_day_split_for_long_duration(self):
        # 20-hour task, daily capacity is 8 hours -> 8h, 8h, 4h across 3 days
        Task.objects.create(
            company=self.company, project=self.project, name='Store Remodel',
            is_recurring=False, required_people=1, duration_hours=20.0,
            preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        self.assertEqual(res['total_shifts_generated'], 3)
        shifts = list(Schedule.objects.all().order_by('shift_date'))
        self.assertEqual(len(shifts), 3)
        # Day 1: 8h (09:00 - 17:00)
        self.assertEqual(shifts[0].start_time, datetime.time(9, 0))
        self.assertEqual(shifts[0].end_time, datetime.time(17, 0))
        # Day 2: 8h (09:00 - 17:00)
        self.assertEqual(shifts[1].start_time, datetime.time(9, 0))
        self.assertEqual(shifts[1].end_time, datetime.time(17, 0))
        # Day 3: 4h (09:00 - 13:00)
        self.assertEqual(shifts[2].start_time, datetime.time(9, 0))
        self.assertEqual(shifts[2].end_time, datetime.time(13, 0))

    def test_preassigned_employee_leave_avoidance(self):
        # Alice is on approved time off on Monday Nov 16
        TimeOffRequest.objects.create(
            employee=self.employee,
            start_date=datetime.date(2026, 11, 16),
            end_date=datetime.date(2026, 11, 16),
            status=TimeOffRequest.Status.APPROVED
        )
        # Task pre-assigned to Alice
        Task.objects.create(
            company=self.company, project=self.project, name='Audit Prep',
            is_recurring=False, required_people=1, duration_hours=4.0,
            employee=self.employee, preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        # Should be scheduled on an open day that is NOT Monday
        shift = Schedule.objects.first()
        self.assertNotEqual(shift.shift_date, datetime.date(2026, 11, 16))
        self.assertEqual(shift.employee, self.employee)
        self.assertTrue(len(res['warnings']) > 0)

    def test_api_generate_endpoint(self):
        Task.objects.create(
            company=self.company, project=self.project, name='API Scheduled Task',
            is_recurring=True, required_people=2, duration_hours=4.0
        )
        url = reverse('schedule-generate')
        payload = {
            'company_id': self.company.pk,
            'week_start': '2026-11-16',
            'clear_existing': True
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['company_id'], self.company.pk)
        self.assertEqual(response.data['total_shifts_generated'], 10)  # 5 days * 2 people
        self.assertEqual(response.data['unassigned_shifts'], 10)

    def test_recurring_task_respects_employee_time_off(self):
        # Alice is pre-assigned to recurring task
        task = Task.objects.create(
            company=self.company, project=self.project, name='Daily Front Desk',
            is_recurring=True, required_people=1, duration_hours=8.0,
            employee=self.employee, preferred_window=Task.PreferredWindow.OPEN_TO_CLOSE
        )
        # Alice is approved off on Wednesday Nov 18
        TimeOffRequest.objects.create(
            employee=self.employee,
            start_date=datetime.date(2026, 11, 18),
            end_date=datetime.date(2026, 11, 18),
            status=TimeOffRequest.Status.APPROVED
        )

        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        self.assertEqual(res['total_shifts_generated'], 5)
        self.assertEqual(res['pre_assigned_shifts'], 4)  # Mon, Tue, Thu, Fri
        self.assertEqual(res['unassigned_shifts'], 1)    # Wed

        wed_shift = Schedule.objects.get(shift_date=datetime.date(2026, 11, 18))
        self.assertIsNone(wed_shift.employee)  # Left unassigned for smart scheduler!
        self.assertTrue(any('approved time-off' in w for w in res['warnings']))

        mon_shift = Schedule.objects.get(shift_date=datetime.date(2026, 11, 16))
        self.assertEqual(mon_shift.employee, self.employee)

    def test_availability_hours_validation(self):
        # Alice is only available on Monday from 09:00 to 13:00 (4 hours)
        AvailabilitySlot.objects.create(
            employee=self.employee,
            day_of_week=0,  # Monday
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0)
        )

        # Task A: 09:00 - 13:00 (fits Alice's slot)
        Task.objects.create(
            company=self.company, project=self.project, name='Morning Task',
            is_recurring=False, required_people=1, duration_hours=4.0,
            employee=self.employee, preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        # Task B: 09:00 - 17:00 (exceeds Alice's 13:00 end_time)
        Task.objects.create(
            company=self.company, project=self.project, name='Full Day Task',
            is_recurring=False, required_people=1, duration_hours=8.0,
            employee=self.employee, preferred_window=Task.PreferredWindow.OPEN_TO_CLOSE
        )

        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        morning_shift = Schedule.objects.get(task__name='Morning Task')
        self.assertEqual(morning_shift.employee, self.employee)

        full_day_shift = Schedule.objects.get(task__name='Full Day Task')
        self.assertIsNone(full_day_shift.employee)  # Left unassigned!
        self.assertTrue(any('do not cover shift' in w for w in res['warnings']))

    def test_flexible_task_concurrency_leveling_between_shifts(self):
        # Anchor 1: Morning task 09:00 - 11:00 (BEGINNING_OF_DAY)
        Task.objects.create(
            company=self.company, project=self.project, name='Morning Opening',
            is_recurring=False, required_people=1, duration_hours=2.0,
            preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        # Anchor 2: Evening task 15:00 - 17:00 (END_OF_DAY)
        Task.objects.create(
            company=self.company, project=self.project, name='Evening Closing',
            is_recurring=False, required_people=1, duration_hours=2.0,
            preferred_window=Task.PreferredWindow.END_OF_DAY
        )
        # Flexible task: 2 hours. Should fill the valley right at 11:00 - 13:00 with no pause
        t_flex = Task.objects.create(
            company=self.company, project=self.project, name='Midday Restock',
            is_recurring=False, required_people=1, duration_hours=2.0,
            preferred_window=Task.PreferredWindow.FLEXIBLE
        )

        # Restrict to only Monday by zeroing other days
        self.hours.tuesday_start = None
        self.hours.tuesday_end = None
        self.hours.wednesday_start = None
        self.hours.wednesday_end = None
        self.hours.thursday_start = None
        self.hours.thursday_end = None
        self.hours.friday_start = None
        self.hours.friday_end = None
        self.hours.save()

        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        service.generate()

        s_flex = Schedule.objects.get(task=t_flex)
        self.assertEqual(s_flex.start_time, datetime.time(11, 0))
        self.assertEqual(s_flex.end_time, datetime.time(13, 0))

    def test_flexible_task_with_preassigned_employee_afternoon_availability(self):
        # Alice is only available in the afternoon (13:00 - 17:00) on Monday
        AvailabilitySlot.objects.create(
            employee=self.employee,
            day_of_week=0,  # Monday
            start_time=datetime.time(13, 0),
            end_time=datetime.time(17, 0)
        )
        # Only Monday open
        self.hours.tuesday_start = None
        self.hours.tuesday_end = None
        self.hours.wednesday_start = None
        self.hours.wednesday_end = None
        self.hours.thursday_start = None
        self.hours.thursday_end = None
        self.hours.friday_start = None
        self.hours.friday_end = None
        self.hours.save()

        # Flexible task of 3 hours pre-assigned to Alice
        t_flex = Task.objects.create(
            company=self.company, project=self.project, name='Afternoon Audit',
            is_recurring=False, required_people=1, duration_hours=3.0,
            employee=self.employee, preferred_window=Task.PreferredWindow.FLEXIBLE
        )

        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        s_flex = Schedule.objects.get(task=t_flex)
        self.assertEqual(s_flex.employee, self.employee)
        self.assertEqual(s_flex.start_time, datetime.time(13, 0))
        self.assertEqual(s_flex.end_time, datetime.time(16, 0))
        self.assertEqual(len(res['warnings']), 0)

    def test_multi_person_task_at_same_time(self):
        t_multi = Task.objects.create(
            company=self.company, project=self.project, name='Group Floor Reset',
            is_recurring=False, required_people=3, duration_hours=3.0,
            preferred_window=Task.PreferredWindow.FLEXIBLE
        )

        # Restrict to Monday
        self.hours.tuesday_start = None
        self.hours.tuesday_end = None
        self.hours.wednesday_start = None
        self.hours.wednesday_end = None
        self.hours.thursday_start = None
        self.hours.thursday_end = None
        self.hours.friday_start = None
        self.hours.friday_end = None
        self.hours.save()

        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        service.generate()

        shifts = list(Schedule.objects.filter(task=t_multi).order_by('id'))
        self.assertEqual(len(shifts), 3)
        # All 3 positions work at the exact same time
        self.assertEqual(shifts[0].start_time, datetime.time(9, 0))
        self.assertEqual(shifts[0].end_time, datetime.time(12, 0))
        self.assertEqual(shifts[1].start_time, datetime.time(9, 0))
        self.assertEqual(shifts[1].end_time, datetime.time(12, 0))
        self.assertEqual(shifts[2].start_time, datetime.time(9, 0))
        self.assertEqual(shifts[2].end_time, datetime.time(12, 0))

    def test_inter_day_load_balancing_accounts_for_person_hours(self):
        # Task 1: 4 hours, 2 people -> 8 person-hours.
        # Placed on Monday (first open day with 0 hours)
        Task.objects.create(
            company=self.company, project=self.project, name='Two-Person Setup',
            is_recurring=False, required_people=2, duration_hours=4.0,
            preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        # Task 2: 4 hours, 1 person.
        # Candidate days: Monday now has 8 scheduled person-hours, Tuesday has 0.
        # Should pick Tuesday!
        t2 = Task.objects.create(
            company=self.company, project=self.project, name='Solo Followup',
            is_recurring=False, required_people=1, duration_hours=4.0,
            preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )

        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        service.generate()

        t2_shift = Schedule.objects.get(task=t2)
        # Week start is Nov 16 (Monday). Tuesday is Nov 17.
        self.assertEqual(t2_shift.shift_date, datetime.date(2026, 11, 17))

    def test_non_recurring_task_respects_preferred_day(self):
        # Even though Mon, Tue, Wed have 0 load, task specifically requests Thursday (3)
        t_pref = Task.objects.create(
            company=self.company, project=self.project, name='Thursday Deep Clean',
            is_recurring=False, required_people=1, duration_hours=3.0,
            preferred_day=Task.Day.THURSDAY, preferred_window=Task.PreferredWindow.FLEXIBLE
        )
        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        self.assertEqual(res['total_shifts_generated'], 1)
        shift = Schedule.objects.get(task=t_pref)
        # Thursday of week Nov 16 is Nov 19
        self.assertEqual(shift.shift_date, datetime.date(2026, 11, 19))

    def test_recurring_task_with_preferred_day_only_generates_on_that_weekday(self):
        # A weekly recurring task that only runs every Wednesday (2)
        t_rec = Task.objects.create(
            company=self.company, project=self.project, name='Wednesday All-Hands',
            is_recurring=True, required_people=1, duration_hours=1.0,
            preferred_day=Task.Day.WEDNESDAY, preferred_window=Task.PreferredWindow.BEGINNING_OF_DAY
        )
        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        # Generates only 1 shift for the week on Wednesday Nov 18, rather than 5 on all open days
        self.assertEqual(res['total_shifts_generated'], 1)
        shift = Schedule.objects.get(task=t_rec)
        self.assertEqual(shift.shift_date, datetime.date(2026, 11, 18))

    def test_preferred_day_closed_falls_back_with_warning(self):
        # Company closed on Saturday (5)
        t_sat = Task.objects.create(
            company=self.company, project=self.project, name='Weekend Promo',
            is_recurring=False, required_people=1, duration_hours=2.0,
            preferred_day=Task.Day.SATURDAY, preferred_window=Task.PreferredWindow.FLEXIBLE
        )
        service = ShiftGeneratorService(company=self.company, week_start=self.week_start)
        res = service.generate()

        self.assertEqual(res['total_shifts_generated'], 1)
        self.assertTrue(any('company is closed on that day' in w for w in res['warnings']))

    def test_task_serializer_with_preferred_day(self):
        task = Task.objects.create(
            company=self.company, project=self.project, name='Task with Preferred Day',
            is_recurring=False, required_people=1, duration_hours=2.0,
            preferred_day=Task.Day.TUESDAY, preferred_window=Task.PreferredWindow.FLEXIBLE
        )
        serializer = TaskSerializer(task)
        self.assertEqual(serializer.data['preferred_day'], 1)
        self.assertEqual(serializer.data['preferred_day_name'], 'Tuesday')


class ScheduleMultipleEmployeesTests(ScheduleApiBase):
    def setUp(self):
        super().setUp()
        self.emp2 = make_employee('emp2@example.com', department=self.employee.department)
        self.emp3 = make_employee('emp3@example.com', department=self.employee.department)
        self.task = Task.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            name='Multi Cashier',
            required_people=2,
            duration_hours=4.0
        )

    def test_create_schedule_with_list_of_employees(self):
        payload = {
            'task': self.task.pk,
            'shift_date': DAY,
            'start_time': '09:00',
            'end_time': '13:00',
            'employees': [self.employee.pk, self.emp2.pk],
            'notes': 'Team shift'
        }
        res = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.data), 2)
        # Check database rows (1-entry-per-employee)
        db_rows = Schedule.objects.filter(task=self.task, shift_date=DAY)
        self.assertEqual(db_rows.count(), 2)
        assigned_ids = set(db_rows.values_list('employee_id', flat=True))
        self.assertEqual(assigned_ids, {self.employee.pk, self.emp2.pk})

    def test_create_schedule_with_open_slots_up_to_headcount(self):
        # Task requires 2 people, but only 1 employee provided
        payload = {
            'task': self.task.pk,
            'shift_date': DAY,
            'start_time': '09:00',
            'end_time': '13:00',
            'employees': [self.employee.pk],
            'notes': 'Partial team'
        }
        res = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.data), 2)
        db_rows = Schedule.objects.filter(task=self.task, shift_date=DAY)
        self.assertEqual(db_rows.count(), 2)
        self.assertEqual(db_rows.filter(employee=self.employee).count(), 1)
        self.assertEqual(db_rows.filter(employee__isnull=True).count(), 1)

    def test_create_schedule_exceeding_headcount_rejected(self):
        # Task requires 2 people, but 3 provided
        payload = {
            'task': self.task.pk,
            'shift_date': DAY,
            'start_time': '09:00',
            'end_time': '13:00',
            'employees': [self.employee.pk, self.emp2.pk, self.emp3.pk]
        }
        res = self.client.post(self.list_url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('employees', res.data)
        self.assertIn('Cannot add more than 2 employees', res.data['employees'][0])

    def test_assign_employee_to_existing_schedule_entry(self):
        # Create unassigned slot
        Schedule.objects.create(
            task=self.task, task_name=self.task.name, shift_date=DAY,
            start_time='09:00', end_time='13:00', employee=self.employee
        )
        Schedule.objects.create(
            task=self.task, task_name=self.task.name, shift_date=DAY,
            start_time='09:00', end_time='13:00', employee=None
        )
        url = reverse('schedule-assign-employees')
        res = self.client.post(url, {
            'task': self.task.pk,
            'shift_date': DAY,
            'start_time': '09:00',
            'end_time': '13:00',
            'employees': [self.emp2.pk]
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # Now 2 employees are assigned, 0 unassigned
        db_rows = Schedule.objects.filter(task=self.task, shift_date=DAY)
        self.assertEqual(db_rows.filter(employee__isnull=False).count(), 2)
        self.assertEqual(db_rows.filter(employee__isnull=True).count(), 0)

        # Attempting to assign a 3rd employee exceeds headcount of 2
        res2 = self.client.post(url, {
            'task': self.task.pk,
            'shift_date': DAY,
            'start_time': '09:00',
            'end_time': '13:00',
            'employees': [self.emp3.pk]
        }, format='json')
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('employees', res2.data)

    def test_tasks_endpoint(self):
        url = reverse('task-list')
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(any(t['name'] == 'Multi Cashier' for t in res.data))


class SmartShiftAssignerApiTests(ScheduleApiBase):
    def setUp(self):
        super().setUp()
        self.emp2 = make_employee('assignee2@example.com', department=self.employee.department)
        # Operating hours
        CompanyHours.objects.create(
            company=self.employee.company,
            monday_start=datetime.time(9, 0), monday_end=datetime.time(17, 0),
            tuesday_start=datetime.time(9, 0), tuesday_end=datetime.time(17, 0),
            wednesday_start=datetime.time(9, 0), wednesday_end=datetime.time(17, 0),
            thursday_start=datetime.time(9, 0), thursday_end=datetime.time(17, 0),
            friday_start=datetime.time(9, 0), friday_end=datetime.time(17, 0),
        )
        self.week_start = datetime.date(2026, 11, 16)  # Monday

    def test_assign_shifts_api_fills_unassigned_slots(self):
        # Create 2 unassigned schedule slots for Nov 16
        s1 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Floor Shift 1',
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )
        s2 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Floor Shift 2',
            shift_date=self.week_start,
            start_time=datetime.time(13, 0),
            end_time=datetime.time(17, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )

        url = reverse('schedule-assign')
        payload = {
            'company_id': self.employee.company.pk,
            'week_start': self.week_start.isoformat(),
            'department_id': self.employee.department.pk,
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['total_unassigned_slots'], 2)
        self.assertEqual(res.data['slots_filled'], 2)
        self.assertEqual(res.data['unfillable_slots'], 0)

        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertIsNotNone(s1.employee)
        self.assertIsNotNone(s2.employee)

    def test_shift_auto_schedule_legacy_endpoint_delegates_to_assigner(self):
        # Create unassigned slot
        s = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Auto Scheduled Slot',
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )

        url = reverse('shift_auto_schedule_api')
        payload = {
            'department': self.employee.department.pk,
            'date_from': self.week_start.isoformat(),
            'date_to': '2026-11-22',
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['created'], 1)
        self.assertEqual(res.data['slots_filled'], 1)

        s.refresh_from_db()
        self.assertIsNotNone(s.employee)

    def test_assign_shifts_respects_skills(self):
        forklift = Skill.objects.create(company=self.employee.company, name='Forklift')
        self.emp2.skills.add(forklift)
        # self.employee does not have forklift skill

        task = Task.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            name='Warehouse Loading',
            required_people=1,
            duration_hours=4.0
        )
        task.skills.add(forklift)

        s = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task=task,
            task_name=task.name,
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )

        url = reverse('schedule-assign')
        payload = {
            'company_id': self.employee.company.pk,
            'week_start': self.week_start.isoformat(),
            'department_id': self.employee.department.pk,
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['slots_filled'], 1)

        s.refresh_from_db()
        self.assertEqual(s.employee, self.emp2)

    def test_assign_shifts_respects_time_off(self):
        TimeOffRequest.objects.create(
            employee=self.employee,
            start_date=self.week_start,
            end_date=self.week_start,
            status=TimeOffRequest.Status.APPROVED
        )

        s = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Daily Register',
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )

        url = reverse('schedule-assign')
        payload = {
            'company_id': self.employee.company.pk,
            'week_start': self.week_start.isoformat(),
            'department_id': self.employee.department.pk,
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['slots_filled'], 1)

        s.refresh_from_db()
        # self.employee is on leave, so self.emp2 must be assigned
        self.assertEqual(s.employee, self.emp2)

    def test_clear_assignments_endpoint(self):
        # Create schedules with employees
        s1 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Shift 1',
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=self.employee,
            status=Schedule.Status.SCHEDULED,
        )
        s2 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Shift 2',
            shift_date=self.week_start + datetime.timedelta(days=1),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(18, 0),
            employee=self.emp2,
            status=Schedule.Status.SCHEDULED,
        )
        url = reverse('schedule-clear-assignments')
        payload = {
            'company_id': self.employee.company.pk,
            'week_start': self.week_start.isoformat(),
            'department_id': self.employee.department.pk,
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['cleared_count'], 2)

        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertIsNone(s1.employee)
        self.assertIsNone(s2.employee)
        # Shift records must still exist
        self.assertEqual(Schedule.objects.filter(pk__in=[s1.pk, s2.pk]).count(), 2)

    def test_clear_shifts_endpoint(self):
        s1 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Shift 1',
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=self.employee,
            status=Schedule.Status.SCHEDULED,
        )
        s2 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Shift 2',
            shift_date=self.week_start + datetime.timedelta(days=2),
            start_time=datetime.time(14, 0),
            end_time=datetime.time(18, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )
        url = reverse('schedule-clear-shifts')
        payload = {
            'company_id': self.employee.company.pk,
            'week_start': self.week_start.isoformat(),
            'department_id': self.employee.department.pk,
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['deleted_count'], 2)

        self.assertEqual(Schedule.objects.filter(pk__in=[s1.pk, s2.pk]).count(), 0)

    def test_skills_crud_and_independent_assignment(self):
        # 1. Create a skill for the company via Skill API
        url = reverse('skill-list')
        res = self.client.post(url, {'name': 'First Aid', 'description': 'CPR & First Aid'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        skill_id = res.data['id']
        self.assertEqual(res.data['name'], 'First Aid')

        skill = Skill.objects.get(pk=skill_id)
        # Verify creating skill does NOT give it to all employees or all tasks
        self.assertEqual(skill.employees.count(), 0)
        self.assertEqual(skill.tasks.count(), 0)

        # 2. Assign skill to an individual employee
        emp_url = reverse('employee-detail', args=[self.emp2.pk])
        emp_res = self.client.patch(emp_url, {'skills': [skill_id]}, format='json')
        self.assertEqual(emp_res.status_code, status.HTTP_200_OK)
        self.emp2.refresh_from_db()
        self.employee.refresh_from_db()
        self.assertIn(skill, self.emp2.skills.all())
        self.assertNotIn(skill, self.employee.skills.all())

        # 3. Assign skill to an individual task
        task = Task.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            name='First Aid Station',
            required_people=1,
            duration_hours=4.0
        )
        task_url = reverse('task-detail', args=[task.pk])
        task_res = self.client.patch(task_url, {'skills': [skill_id]}, format='json')
        self.assertEqual(task_res.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertIn(skill, task.skills.all())

        # 4. Verify cross-company skill assignment is rejected
        other_comp = Company.objects.create(name='Other Corp')
        other_skill = Skill.objects.create(company=other_comp, name='Hazardous Materials')
        bad_task_res = self.client.patch(task_url, {'skills': [other_skill.pk]}, format='json')
        self.assertEqual(bad_task_res.status_code, status.HTTP_400_BAD_REQUEST)
        bad_emp_res = self.client.patch(emp_url, {'skills': [other_skill.pk]}, format='json')
        self.assertEqual(bad_emp_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_shifts_unfillable_when_no_employee_has_skill(self):
        welding = Skill.objects.create(company=self.employee.company, name='Welding')
        task = Task.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            name='Structural Welding',
            required_people=1,
            duration_hours=4.0
        )
        task.skills.add(welding)
        # Neither self.employee nor self.emp2 has Welding skill

        s = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task=task,
            task_name=task.name,
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )

        url = reverse('schedule-assign')
        payload = {
            'company_id': self.employee.company.pk,
            'week_start': self.week_start.isoformat(),
            'department_id': self.employee.department.pk,
        }
        res = self.client.post(url, payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['slots_filled'], 0)
        self.assertEqual(res.data['unfillable_slots'], 1)
        self.assertIn('Welding', res.data['unfillable_details'][0]['reason'])

        s.refresh_from_db()
        self.assertIsNone(s.employee)


class SchedulePublicationApiTests(ScheduleApiBase):
    def setUp(self):
        super().setUp()
        self.week_start = datetime.date(2026, 11, 23)  # Monday
        self.emp2 = make_employee('pubemp2@example.com', department=self.employee.department)

    def test_shift_publication_default_draft(self):
        url = reverse('shift_publication_api')
        res = self.client.get(url, {
            'department': self.employee.department.pk,
            'week_start': self.week_start.isoformat(),
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['published'])
        self.assertIsNone(res.data['published_at'])
        self.assertIsNone(res.data['published_by'])
        self.assertEqual(res.data['week_start'], self.week_start.isoformat())

    def test_shift_review_metrics_and_warnings(self):
        # 1 assigned shift (4 hours)
        s1 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Morning Reception',
            shift_date=self.week_start,
            start_time=datetime.time(9, 0),
            end_time=datetime.time(13, 0),
            employee=self.employee,
            status=Schedule.Status.SCHEDULED,
        )
        # 1 unassigned shift (open slot)
        s2 = Schedule.objects.create(
            company=self.employee.company,
            department=self.employee.department,
            task_name='Afternoon Reception',
            shift_date=self.week_start,
            start_time=datetime.time(13, 0),
            end_time=datetime.time(17, 0),
            employee=None,
            status=Schedule.Status.SCHEDULED,
        )

        url = reverse('shift_review_api')
        res = self.client.get(url, {
            'department': self.employee.department.pk,
            'week_start': self.week_start.isoformat(),
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['slots'], 2)
        self.assertEqual(res.data['filled'], 1)
        self.assertEqual(res.data['open_slots'], 1)
        self.assertEqual(res.data['shift_count'], 2)
        self.assertTrue(len(res.data['open_shifts']) > 0)
        self.assertIn('Afternoon Reception', res.data['open_shifts'][0])
        self.assertTrue(len(res.data['people']) > 0)
        self.assertEqual(res.data['people'][0]['hours'], 4.0)
        self.assertTrue(any('still need an employee assigned' in w for w in res.data['warnings']))

    def test_shift_publish_and_unpublish_workflow(self):
        pub_url = reverse('shift_publish_api')
        unpub_url = reverse('shift_unpublish_api')
        check_url = reverse('shift_publication_api')

        # 1. Publish week
        pub_res = self.client.post(pub_url, {
            'department': self.employee.department.pk,
            'week_start': self.week_start.isoformat(),
        }, format='json')
        self.assertEqual(pub_res.status_code, status.HTTP_200_OK)
        self.assertTrue(pub_res.data['published'])
        self.assertIsNotNone(pub_res.data['published_at'])

        # Verify DB record
        db_pub = SchedulePublication.objects.get(
            company=self.employee.company,
            department=self.employee.department,
            week_start=self.week_start,
        )
        self.assertTrue(db_pub.published)

        # Check status endpoint
        check_res = self.client.get(check_url, {
            'department': self.employee.department.pk,
            'week_start': self.week_start.isoformat(),
        })
        self.assertEqual(check_res.status_code, status.HTTP_200_OK)
        self.assertTrue(check_res.data['published'])
        self.assertIsNotNone(check_res.data['published_by'])

        # 2. Revert / Unpublish week
        unpub_res = self.client.post(unpub_url, {
            'department': self.employee.department.pk,
            'week_start': self.week_start.isoformat(),
        }, format='json')
        self.assertEqual(unpub_res.status_code, status.HTTP_200_OK)
        self.assertFalse(unpub_res.data['published'])
        self.assertIsNone(unpub_res.data['published_at'])

        db_pub.refresh_from_db()
        self.assertFalse(db_pub.published)

        # Check status endpoint again
        check_res2 = self.client.get(check_url, {
            'department': self.employee.department.pk,
            'week_start': self.week_start.isoformat(),
        })
        self.assertEqual(check_res2.status_code, status.HTTP_200_OK)
        self.assertFalse(check_res2.data['published'])





