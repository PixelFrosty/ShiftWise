from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Department, Employee, EmployeeCompatibility,
    Schedule, Shift, ShiftAssignment, TimeOffRequest
)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Scheduling App Role', {'fields': ('role',)}),
    )
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_staff']
    list_filter = ['role', 'is_staff', 'is_superuser', 'is_active']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'created_at']
    search_fields = ['name', 'code']


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['name', 'department', 'position', 'productivity_score', 'pay_rate', 'max_hours_per_week', 'user']
    list_filter = ['department', 'position']
    search_fields = ['name', 'position', 'contact_info']


@admin.register(EmployeeCompatibility)
class EmployeeCompatibilityAdmin(admin.ModelAdmin):
    list_display = ['employee_a', 'employee_b', 'score', 'updated_at']
    list_filter = ['score']
    search_fields = ['employee_a__name', 'employee_b__name', 'notes']


class ShiftInline(admin.TabularInline):
    model = Shift
    extra = 1


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ['title', 'department', 'week_start_date', 'status', 'created_by', 'created_at']
    list_filter = ['department', 'status', 'week_start_date']
    search_fields = ['title', 'department__name']
    inlines = [ShiftInline]


class ShiftAssignmentInline(admin.TabularInline):
    model = ShiftAssignment
    extra = 1


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ['role_title', 'schedule', 'start_time', 'end_time', 'headcount_needed', 'assigned_count', 'is_filled']
    list_filter = ['schedule__department', 'schedule', 'role_title']
    inlines = [ShiftAssignmentInline]


@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ['shift', 'employee', 'assigned_by', 'is_auto_scheduled', 'assigned_at']
    list_filter = ['is_auto_scheduled', 'assigned_at']
    search_fields = ['employee__name', 'shift__role_title']


@admin.register(TimeOffRequest)
class TimeOffRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'start_date', 'end_date', 'status', 'reviewed_by', 'reviewed_at']
    list_filter = ['status', 'start_date']
    search_fields = ['employee__name', 'reason']
