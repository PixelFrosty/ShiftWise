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
