"""Group compatibility scores: managers and the General Manager rate (1-10) how well 2+ employees work together."""
from django.db import transaction
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from . import access, services
from .models import CompatibilityGroup, EmployeeProfile

MAX_GROUP = 25


def group_data(group):
    members = sorted(group.members.all(), key=lambda p: services.display_name(p.user).lower())
    return {
        'id': group.id,
        'score': group.score,
        'employees': [{'id': p.id, 'name': services.display_name(p.user), 'department': p.department.name}
                      for p in members],
        'rated_by': services.display_name(group.rated_by) if group.rated_by else None,
        'updated_at': group.updated_at.isoformat(),
    }


def parse_score(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).strip().lstrip('-').isdigit():
        raise ValidationError({'score': 'Score must be a whole number from 1 to 10.'})
    score = int(value)
    if not CompatibilityGroup.MIN_SCORE <= score <= CompatibilityGroup.MAX_SCORE:
        raise ValidationError({'score': 'Score must be a whole number from 1 to 10.'})
    return score


class CompatibilityGroupViewSet(viewsets.ViewSet):
    """
    list   GET    /compatibility-groups/
    create POST   /compatibility-groups/       {employees: [ids], score}   (re-rating the same people updates it)
    update PATCH  /compatibility-groups/<id>/  {score}
    delete DELETE /compatibility-groups/<id>/
    A manager only works with people in the departments they manage; the General Manager with everyone in the company.
    """
    permission_classes = [IsAuthenticated, access.StaffOnly]

    def _profile(self, request):
        return access.get_profile(request.user)

    def _people(self, request):
        """Employees this person is allowed to rate."""
        profile = self._profile(request)
        people = EmployeeProfile.objects.filter(company_id=profile.company_id)
        if not access.is_ceo(profile):
            people = people.filter(department_id__in=access.managed_department_ids(profile))
        return people

    def _queryset(self, request):
        profile = self._profile(request)
        outside = EmployeeProfile.objects.filter(company_id=profile.company_id).exclude(
            id__in=self._people(request).values('id'))
        qs = (CompatibilityGroup.objects.filter(company_id=profile.company_id)
              .annotate(size=Count('members', distinct=True)).filter(size__gte=2)
              .exclude(members__in=outside)
              .select_related('rated_by').prefetch_related('members__user', 'members__department'))
        return qs

    def list(self, request):
        return Response([group_data(g) for g in self._queryset(request)])

    @transaction.atomic
    def create(self, request):
        ids = request.data.get('employees')
        if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            raise ValidationError({'employees': 'Send a list of employee ids.'})
        ids = set(ids)
        if len(ids) < 2:
            raise ValidationError({'employees': 'Pick at least 2 different employees.'})
        if len(ids) > MAX_GROUP:
            raise ValidationError({'employees': f'Pick at most {MAX_GROUP} employees.'})
        score = parse_score(request.data.get('score'))
        members = list(self._people(request).filter(id__in=ids))
        if len(members) != len(ids):
            raise ValidationError({'employees': 'You can only rate employees in departments you manage.'})

        profile = self._profile(request)
        existing = None
        # the same set of people already has a rating? then update it instead of adding a second one
        candidates = (CompatibilityGroup.objects.filter(company_id=profile.company_id)
                      .annotate(size=Count('members', distinct=True)).filter(size=len(ids)))
        for member_id in ids:
            candidates = candidates.filter(members__id=member_id)
        existing = candidates.first()
        created = existing is None
        group = existing or CompatibilityGroup.objects.create(company_id=profile.company_id, score=score,
                                                              rated_by=request.user)
        if created:
            group.members.set(members)
        else:
            group.score, group.rated_by = score, request.user
            group.save()
        group = self._queryset(request).get(pk=group.pk)
        return Response(group_data(group), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def partial_update(self, request, pk=None):
        group = get_object_or_404(self._queryset(request), pk=pk)
        group.score = parse_score(request.data.get('score'))
        group.rated_by = request.user
        group.save()
        return Response(group_data(self._queryset(request).get(pk=group.pk)))

    def destroy(self, request, pk=None):
        get_object_or_404(self._queryset(request), pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
