from django.urls import path
from . import views
from rest_framework_simplejwt.views import (TokenObtainPairView, TokenRefreshView, TokenBlacklistView)

urlpatterns = [
    path('test/', views.test, name='test_api'),
    path('signup/', views.sign_up, name='signup_api'),
    path('login/', TokenObtainPairView.as_view(), name='login_api'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh_api'),
    path('logout/', TokenBlacklistView.as_view(), name='logout_api')
]
