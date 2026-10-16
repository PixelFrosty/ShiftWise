from django.urls import path
from . import views

urlpatterns = [
    # Auth & Dashboard
    path('', views.dashboard_view, name='dashboard'),
    path('accounts/login/', views.login_view, name='login'),
    path('accounts/logout/', views.logout_view, name='logout'),

    # Phase 1: Employees & Compatibility
    path('employees/', views.employee_list_view, name='employee_list'),
    path('employees/add/', views.employee_create_view, name='employee_create'),
    path('employees/<int:pk>/edit/', views.employee_update_view, name='employee_update'),
    path('employees/<int:pk>/delete/', views.employee_delete_view, name='employee_delete'),
    path('compatibility/', views.compatibility_list_view, name='compatibility_list'),
    path('compatibility/<int:pk>/delete/', views.compatibility_delete_view, name='compatibility_delete'),

    # Phase 2 & 5: Schedules, Shifts, Manual Editor & Solver
    path('schedules/', views.schedule_list_view, name='schedule_list'),
    path('schedules/add/', views.schedule_create_view, name='schedule_create'),
    path('schedules/<int:pk>/', views.schedule_detail_view, name='schedule_detail'),
    path('schedules/<int:pk>/status/', views.schedule_update_status_view, name='schedule_update_status'),
    path('schedules/<int:pk>/solve/', views.schedule_run_solver_view, name='schedule_run_solver'),
    path('schedules/<int:schedule_pk>/shifts/add/', views.shift_create_view, name='shift_create'),
    path('shifts/<int:pk>/delete/', views.shift_delete_view, name='shift_delete'),
    path('shifts/<int:shift_pk>/assign/', views.assign_employee_view, name='assign_employee'),
    path('assignments/<int:assignment_pk>/delete/', views.unassign_employee_view, name='unassign_employee'),

    # Phase 3: Time Off & Pileup Tracker
    path('time-off/', views.time_off_list_view, name='time_off_list'),
    path('time-off/request/', views.time_off_create_view, name='time_off_create'),
    path('time-off/<int:pk>/review/', views.time_off_review_view, name='time_off_review'),
]
