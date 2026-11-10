# pyright: reportAttributeAccessIssue=false
from .models import CompatibilityGroup
from .tests_roles import RoleBase, person

URL = '/api/compatibility-groups/'


class CompatibilityGroupTests(RoleBase):
    def setUp(self):
        super().setUp()
        self.dan = person(self.company, self.eng, 'employee', 'dan@x.com', 'Dan', 'E')

    def rate(self, client, people, score):
        return client.post(URL, {'employees': [p.id for p in people], 'score': score}, format='json')

    def test_employees_cannot_use_it(self):
        self.assertEqual(self.c_alice.get(URL).status_code, 403)
        self.assertEqual(self.rate(self.c_alice, [self.alice, self.dan], 5).status_code, 403)

    def test_manager_rates_group_of_three(self):
        carol_dept_mate = person(self.company, self.eng, 'employee', 'eve@x.com', 'Eve', 'E')
        r = self.rate(self.c_carol, [self.alice, self.dan, carol_dept_mate], 8)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['score'], 8)
        self.assertEqual(sorted(e['name'] for e in r.data['employees']), ['Alice E', 'Dan E', 'Eve E'])
        self.assertEqual(len(self.c_carol.get(URL).data), 1)

    def test_same_people_update_instead_of_duplicate(self):
        self.assertEqual(self.rate(self.c_carol, [self.alice, self.dan], 4).status_code, 201)
        r = self.rate(self.c_ceo, [self.dan, self.alice], 9)
        self.assertEqual((r.status_code, r.data['score']), (200, 9))
        self.assertEqual(CompatibilityGroup.objects.count(), 1)
        # a different set is a different group
        self.assertEqual(self.rate(self.c_ceo, [self.alice, self.dan, self.carol], 6).status_code, 201)
        self.assertEqual(CompatibilityGroup.objects.count(), 2)

    def test_validation(self):
        self.assertEqual(self.rate(self.c_carol, [self.alice], 5).status_code, 400)
        self.assertEqual(self.rate(self.c_carol, [self.alice, self.alice], 5).status_code, 400)
        for bad in (0, 11, 'x', 5.5, None, True):
            self.assertEqual(self.rate(self.c_carol, [self.alice, self.dan], bad).status_code, 400, bad)
        self.assertEqual(self.c_carol.post(URL, {'employees': 'a', 'score': 5}, format='json').status_code, 400)
        self.assertEqual(CompatibilityGroup.objects.count(), 0)

    def test_manager_scope(self):
        # Carol manages Eng only: cannot rate Marketing people, General Manager can
        self.assertEqual(self.rate(self.c_carol, [self.alice, self.gus], 5).status_code, 400)
        self.assertEqual(self.rate(self.c_ceo, [self.alice, self.gus], 5).status_code, 201)
        # Carol cannot see a group that includes someone outside her departments; Bob cannot either (Alice is Eng)
        self.assertEqual(self.c_carol.get(URL).data, [])
        self.assertEqual(self.c_bob.get(URL).data, [])
        self.assertEqual(len(self.c_ceo.get(URL).data), 1)

    def test_update_and_delete(self):
        gid = self.rate(self.c_carol, [self.alice, self.dan], 3).data['id']
        self.assertEqual(self.c_carol.patch(f'{URL}{gid}/', {'score': 10}, format='json').data['score'], 10)
        self.assertEqual(self.c_carol.patch(f'{URL}{gid}/', {'score': 11}, format='json').status_code, 400)
        self.assertEqual(self.c_bob.delete(f'{URL}{gid}/').status_code, 404)
        self.assertEqual(self.c_carol.delete(f'{URL}{gid}/').status_code, 204)
        self.assertEqual(CompatibilityGroup.objects.count(), 0)

    def test_group_with_fewer_than_two_left_is_hidden(self):
        gid = self.rate(self.c_carol, [self.alice, self.dan], 3).data['id']
        self.dan.delete()
        self.assertEqual(self.c_carol.get(URL).data, [])
        self.assertEqual(self.c_carol.patch(f'{URL}{gid}/', {'score': 5}, format='json').status_code, 404)

    def test_other_company_isolated(self):
        from .models import Company, Department
        other = Company.objects.create(name='Other')
        d = Department.objects.create(company=other, name='X')
        stranger = person(other, d, 'employee', 's@y.com', 'S', 'Y')
        self.assertEqual(self.rate(self.c_ceo, [self.alice, stranger], 5).status_code, 400)
