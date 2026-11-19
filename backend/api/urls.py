from django.urls import path
from . import views
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (TokenObtainPairView, TokenRefreshView, TokenBlacklistView)

router = DefaultRouter()
router.register('schedules', views.ScheduleViewSet, basename='schedule')
router.register('tasks', views.TaskViewSet, basename='task')
router.register('departments', views.DepartmentViewSet, basename='department')
router.register('employees', views.EmployeeProfileViewSet, basename='employee')
router.register('compatibility', views.CompatibilityScoreViewSet, basename='compatibility')
router.register('availability', views.AvailabilitySlotViewSet, basename='availability')
router.register('time-off', views.TimeOffRequestViewSet, basename='time-off')
router.register('projects', views.ProjectViewSet, basename='project')
router.register('skills', views.SkillViewSet, basename='skill')

urlpatterns = [
    path('test/', views.test, name='test_api'),
    path('signup/', views.sign_up, name='signup_api'),
    path('signup-check/', views.signup_check, name='signup_check'),
    path('login/', TokenObtainPairView.as_view(), name='login_api'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh_api'),
    path('logout/', TokenBlacklistView.as_view(), name='logout_api'),
    path('me/', views.me, name='me_api'),
    path('shifts/publication/', views.shift_publication, name='shift_publication_api'),
    path('shifts/review/', views.shift_review, name='shift_review_api'),
    path('shifts/publish/', views.shift_publish, name='shift_publish_api'),
    path('shifts/auto-schedule/', views.shift_auto_schedule, name='shift_auto_schedule_api'),
] + router.urls
