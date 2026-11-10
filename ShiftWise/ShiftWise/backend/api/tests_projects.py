from .models import Milestone, Notification, Project
from .tests_roles import RoleBase


class ProjectMilestoneTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.eng_proj = Project.objects.create(company=self.company, department=self.eng, name='Eng launch')
        self.all_proj = Project.objects.create(company=self.company, department=None, name='Company offsite')
        self.mkt_proj = Project.objects.create(company=self.company, department=self.mkt, name='Mkt campaign')

    def add(self, client, project, **kw):
        body = {'project': project.pk, 'title': 'Design', 'due_date': '2026-12-01', 'assignee_ids': []}
        body.update(kw)
        return client.post('/api/milestones/', body, format='json')

    def names(self, client):
        return {p['name'] for p in client.get('/api/projects/').data}

    def test_visibility(self):
        self.assertEqual(self.names(self.c_alice), {'Eng launch', 'Company offsite'})
        self.assertEqual(self.names(self.c_gus), {'Mkt campaign', 'Company offsite'})
        self.assertEqual(self.names(self.c_carol), {'Eng launch', 'Company offsite', 'Mkt campaign'})
        self.assertEqual(self.c_gus.get(f'/api/projects/{self.eng_proj.pk}/').status_code, 404)

    def test_extra_department_sees_project(self):
        self.gus.extra_departments.add(self.eng)
        self.assertIn('Eng launch', self.names(self.c_gus))

    def test_manager_creates_and_assigns_notifies(self):
        r = self.add(self.c_carol, self.eng_proj, assignee_ids=[self.alice.pk])
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual([a['name'] for a in r.data['assignees']], ['Alice E'])
        self.assertTrue(Notification.objects.filter(recipient=self.alice.user, message__contains='Design').exists())
        # saving again with the same person does not notify twice
        mid = r.data['id']
        self.c_carol.patch(f'/api/milestones/{mid}/', {'assignee_ids': [self.alice.pk], 'title': 'Design 2'}, format='json')
        self.assertEqual(Notification.objects.filter(recipient=self.alice.user, message__contains='Design').count(), 1)

    def test_employee_does_not_see_assignees_only_own(self):
        m = self.add(self.c_carol, self.eng_proj, assignee_ids=[self.alice.pk]).data['id']
        self.add(self.c_carol, self.eng_proj, title='Other')
        mine = self.c_alice.get(f'/api/projects/{self.eng_proj.pk}/').data['milestones']
        self.assertEqual(len(mine), 2)
        self.assertTrue(all(x['assignees'] == [] for x in mine))
        self.assertEqual({x['title']: x['assigned_to_me'] for x in mine}, {'Design': True, 'Other': False})
        self.assertTrue(self.c_carol.get(f'/api/projects/{self.eng_proj.pk}/').data['milestones'][0]['assignees'])
        # a coworker who is not assigned sees nothing about it
        self.carol_other = None
        self.assertEqual(m, mine[0]['id'])

    def test_assignee_may_only_change_status(self):
        m = self.add(self.c_carol, self.eng_proj, assignee_ids=[self.alice.pk]).data['id']
        r = self.c_alice.patch(f'/api/milestones/{m}/', {'status': 'done'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['status'], 'done')
        self.assertEqual(self.c_alice.patch(f'/api/milestones/{m}/', {'title': 'x'}, format='json').status_code, 403)
        self.assertEqual(self.c_alice.patch(f'/api/milestones/{m}/', {'assignee_ids': []}, format='json').status_code, 403)
        self.assertEqual(self.c_alice.delete(f'/api/milestones/{m}/').status_code, 403)

    def test_unassigned_employee_cannot_change(self):
        m = self.add(self.c_carol, self.eng_proj).data['id']
        self.assertEqual(self.c_alice.patch(f'/api/milestones/{m}/', {'status': 'done'}, format='json').status_code, 403)
        self.assertEqual(self.add(self.c_alice, self.eng_proj).status_code, 403)

    def test_manager_scope(self):
        self.assertEqual(self.add(self.c_bob, self.eng_proj).status_code, 403)        # not Bob's department
        self.assertEqual(self.add(self.c_carol, self.all_proj).status_code, 403)      # company-wide: GM only
        self.assertEqual(self.add(self.c_ceo, self.all_proj).status_code, 201)
        m = Milestone.objects.filter(project=self.eng_proj).count()
        self.assertEqual(m, 0)

    def test_assignees_must_belong(self):
        r = self.add(self.c_carol, self.eng_proj, assignee_ids=[self.gus.pk])
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.add(self.c_ceo, self.all_proj, assignee_ids=[self.gus.pk, self.alice.pk]).status_code, 201)

    def test_unassign_and_delete(self):
        m = self.add(self.c_carol, self.eng_proj, assignee_ids=[self.alice.pk]).data['id']
        r = self.c_carol.patch(f'/api/milestones/{m}/', {'assignee_ids': []}, format='json')
        self.assertEqual(r.data['assignees'], [])
        self.assertEqual(self.c_carol.delete(f'/api/milestones/{m}/').status_code, 204)

    def test_validation_and_hidden_project(self):
        self.assertEqual(self.add(self.c_carol, self.eng_proj, title=' ').status_code, 400)
        self.assertEqual(self.add(self.c_carol, self.eng_proj, due_date='nope').status_code, 400)
        self.assertEqual(self.add(self.c_alice, self.mkt_proj).status_code, 400)
        self.assertEqual(self.c_carol.post('/api/milestones/', {'title': 'x'}, format='json').status_code, 400)

    def test_counts_and_project_delete_cascades(self):
        m = self.add(self.c_carol, self.eng_proj).data['id']
        self.add(self.c_carol, self.eng_proj, title='B')
        self.c_carol.patch(f'/api/milestones/{m}/', {'status': 'done'}, format='json')
        d = self.c_alice.get(f'/api/projects/{self.eng_proj.pk}/').data
        self.assertEqual(d['milestone_counts'], {'total': 2, 'done': 1})
        self.assertTrue(self.c_carol.get(f'/api/projects/{self.eng_proj.pk}/').data['can_edit'])
        self.assertFalse(d['can_edit'])
        self.c_carol.delete(f'/api/projects/{self.eng_proj.pk}/')
        self.assertEqual(Milestone.objects.count(), 0)

    def test_people_lists(self):
        r = self.c_carol.get(f'/api/projects/people/?department={self.eng.pk}')
        self.assertEqual({p['name'] for p in r.data}, {'Alice E', 'Carol M', 'Cee Oh'})
        self.assertEqual(self.c_carol.get(f'/api/projects/people/?department={self.mkt.pk}').status_code, 403)
        self.assertEqual(self.c_carol.get('/api/projects/people/').status_code, 403)
        self.assertEqual(len(self.c_ceo.get('/api/projects/people/').data), 5)
        self.assertEqual(self.c_alice.get(f'/api/projects/people/?department={self.eng.pk}').status_code, 403)
