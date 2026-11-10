"""Projects and their milestones (an optional feature). Who sees what:
  * everyone sees the projects of their own departments and the company-wide ones, with every milestone,
  * only managers and the General Manager see who is assigned; an employee only learns about their own assignments.
"""
from django.db.models import Q

from . import access, services


def visible_projects(queryset, profile):
    """Managers and the General Manager see every project of the company; others see their departments' projects
    (home and extra departments) and the company-wide ones."""
    queryset = queryset.filter(company_id=profile.company_id)
    if access.is_staff_role(profile):
        return queryset
    return queryset.filter(Q(department__isnull=True) | Q(department_id__in=access.member_department_ids(profile)))


def can_edit_project(profile, project):
    """General Manager: all. Manager: projects of departments they run. Company-wide projects: General Manager only."""
    if project.department_id is None:
        return access.is_ceo(profile)
    return access.can_manage_department(profile, project.department_id)


def milestone_data(milestone, viewer):
    people = [a.employee for a in milestone.assignments.all()]
    mine = any(p.pk == viewer.pk for p in people)
    return {
        'id': milestone.id, 'project': milestone.project_id, 'title': milestone.title,
        'description': milestone.description,
        'due_date': milestone.due_date.isoformat() if milestone.due_date else None,
        'status': milestone.status, 'assigned_to_me': mine,
        # names are only for managers; an employee gets nothing about other people's assignments
        'assignees': ([{'id': p.pk, 'name': services.display_name(p.user)} for p in people]
                      if access.is_staff_role(viewer) else []),
    }
