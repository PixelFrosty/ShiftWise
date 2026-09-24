from django.urls import path
from . import views

urlpatterns = [
    # go to /api/test/ to test the API
    path('signup/', views.sign_up, name='signup_api'),
]
