from django.contrib import admin

from .models import User

admin.site.register(User)

from .models import (AvailabilitySlot, Company, CompatibilityScore, Department, EmployeeProfile, Project,
                     Schedule, TimeOffRequest)

admin.site.register(Company)
admin.site.register(Department)
admin.site.register(EmployeeProfile)
admin.site.register(Schedule)
admin.site.register(CompatibilityScore)
admin.site.register(AvailabilitySlot)
admin.site.register(TimeOffRequest)
admin.site.register(Project)
