from django import forms
from .models import Employee, EmployeeCompatibility, Schedule, Shift, ShiftAssignment, TimeOffRequest, Department
import datetime


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['name', 'department', 'position', 'contact_info', 'productivity_score', 'pay_rate', 'max_hours_per_week']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Alice Smith'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'position': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Senior Barista'}),
            'contact_info': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. alice@example.com / 555-0192'}),
            'productivity_score': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.1', 'min': '1.0', 'max': '10.0'}),
            'pay_rate': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.25', 'placeholder': 'e.g. 22.50 (optional)'}),
            'max_hours_per_week': forms.NumberInput(attrs={'class': 'form-input', 'min': '1', 'max': '80'}),
        }


class CompatibilityForm(forms.ModelForm):
    class Meta:
        model = EmployeeCompatibility
        fields = ['employee_a', 'employee_b', 'score', 'notes']
        widgets = {
            'employee_a': forms.Select(attrs={'class': 'form-select'}),
            'employee_b': forms.Select(attrs={'class': 'form-select'}),
            'score': forms.NumberInput(attrs={'class': 'form-input', 'step': '0.5', 'min': '1.0', 'max': '10.0', 'placeholder': '1 = friction, 5 = neutral, 10 = synergy'}),
            'notes': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Reason or collaboration notes (optional)'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        emp_a = cleaned_data.get('employee_a')
        emp_b = cleaned_data.get('employee_b')
        if emp_a and emp_b and emp_a == emp_b:
            raise forms.ValidationError("Select two different employees.")
        return cleaned_data


class ScheduleForm(forms.ModelForm):
    class Meta:
        model = Schedule
        fields = ['department', 'title', 'week_start_date', 'status']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Week 42 - Store Frontline'}),
            'week_start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class ShiftForm(forms.ModelForm):
    class Meta:
        model = Shift
        fields = ['role_title', 'start_time', 'end_time', 'headcount_needed']
        widgets = {
            'role_title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Morning Lead'}),
            'start_time': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
            'headcount_needed': forms.NumberInput(attrs={'class': 'form-input', 'min': '1', 'value': '1'}),
        }


class ShiftAssignmentForm(forms.ModelForm):
    class Meta:
        model = ShiftAssignment
        fields = ['employee']
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
        }


class TimeOffRequestForm(forms.ModelForm):
    class Meta:
        model = TimeOffRequest
        fields = ['start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
            'reason': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Reason for leave (vacation, personal, etc.)'}),
        }
