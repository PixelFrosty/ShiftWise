from django import forms
from django.contrib import admin

from .models import (
    AvailabilitySlot,
    Company,
    CompatibilityScore,
    Department,
    EmployeeProfile,
    Project,
    Schedule,
    TimeOffRequest,
    User,
)


class DepartmentSelectWidget(forms.Select):
    """
    Select widget that annotates each <option> with a data-company attribute
    so client-side JS can filter department choices based on selected company.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dept_company_map = None

    def get_dept_company_map(self):
        if self._dept_company_map is None:
            self._dept_company_map = dict(Department.objects.values_list('id', 'company_id'))
        return self._dept_company_map

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        val = value.value if hasattr(value, 'value') else value
        if val:
            try:
                company_id = self.get_dept_company_map().get(int(val))
                if company_id is not None:
                    option['attrs']['data-company'] = str(company_id)
            except (ValueError, TypeError):
                pass
        return option


class EmployeeProfileForm(forms.ModelForm):
    class Meta:
        model = EmployeeProfile
        fields = '__all__'
        widgets = {
            'department': DepartmentSelectWidget(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company_id = None
        if self.instance and self.instance.pk and self.instance.company_id:
            company_id = self.instance.company_id
            if 'company' in self.fields:
                self.fields['company'].disabled = True
                self.fields['company'].help_text = (
                    'Company cannot be changed once assigned. Create a new employee profile instead.'
                )
        elif self.data:
            prefix = f"{self.prefix}-" if self.prefix else ""
            company_id = self.data.get(f"{prefix}company")
        if company_id:
            try:
                self.fields['department'].queryset = Department.objects.filter(company_id=int(company_id))
            except (ValueError, TypeError):
                pass

    def clean(self):
        cleaned_data = super().clean()
        company = cleaned_data.get('company')
        if self.instance and self.instance.pk:
            prefix = f"{self.prefix}-" if self.prefix else ""
            raw_company = self.data.get(f"{prefix}company") if self.data else None
            is_raw_tampered = raw_company is not None and str(raw_company) != str(self.instance.company_id)
            is_cleaned_mismatched = company and company.pk != self.instance.company_id
            if is_raw_tampered or is_cleaned_mismatched:
                self.add_error(
                    'company',
                    'Company cannot be changed once assigned. Create a new employee profile instead.'
                )
        department = cleaned_data.get('department')
        if company and department and department.company_id != company.pk:
            self.add_error('department', 'Department does not belong to the selected company.')
        return cleaned_data


class EmployeeProfileInline(admin.TabularInline):
    model = EmployeeProfile
    form = EmployeeProfileForm
    extra = 0
    fields = ('company', 'department', 'role', 'position', 'productivity_score', 'pay_rate')


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    inlines = [EmployeeProfileInline]
    list_display = ('email', 'username', 'first_name', 'last_name', 'date_of_birth')
    search_fields = ('email', 'username', 'first_name', 'last_name')

    class Media:
        js = ('api/js/filter_departments.js',)


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    form = EmployeeProfileForm
    list_display = ('id', 'user', 'company', 'department', 'role', 'position')
    list_filter = ('company', 'department', 'role')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'position')

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('company',)
        return self.readonly_fields

    class Media:
        js = ('api/js/filter_departments.js',)


admin.site.register(Company)
admin.site.register(Department)
admin.site.register(Schedule)
admin.site.register(CompatibilityScore)
admin.site.register(AvailabilitySlot)
admin.site.register(TimeOffRequest)
admin.site.register(Project)
