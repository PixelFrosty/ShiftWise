from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status

from django.urls import reverse

# Create your tests here.

from .models import User

class UserTests(TestCase):
    def test_createUser(self):
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

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)  # pyright: ignore[reportAttributeAccessIssue]
        self.assertEqual(response.data['username'], 'Test')  # pyright: ignore[reportAttributeAccessIssue]
        self.assertEqual(response.data['email'], 'test@gmail.com')  # pyright: ignore[reportAttributeAccessIssue]
        self.assertEqual(response.data['first_name'], 'test')  # pyright: ignore[reportAttributeAccessIssue]
        self.assertEqual(response.data['last_name'], 'user')  # pyright: ignore[reportAttributeAccessIssue]
        self.assertEqual(response.data['date_of_birth'], '2000-02-02')  # pyright: ignore[reportAttributeAccessIssue]
        self.assertNotIn('password', response.data)  # pyright: ignore[reportAttributeAccessIssue]
