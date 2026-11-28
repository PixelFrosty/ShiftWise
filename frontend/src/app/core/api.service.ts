import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, catchError, forkJoin, map, of, switchMap } from 'rxjs';
import { API_URL } from './api';
import { DepartmentRef, Me, Role } from './models';

export interface Department extends DepartmentRef { employee_count: number; managers: string[]; }

export type MilestoneStatus = 'todo' | 'in_progress' | 'done';
export interface Milestone {
  id: number; project: number; title: string; description: string; due_date: string | null;
  status: MilestoneStatus; assigned_to_me: boolean;
  assignees: { id: number; name: string }[];   // only filled in for managers
}
export interface Project {
  id: number; company: number; department: number | null; department_name: string | null; name: string;
  description: string; priority: 'low' | 'medium' | 'high'; is_active: boolean; can_edit: boolean;
  milestones: Milestone[]; milestone_counts: { total: number; done: number };
}

export interface Skill {
  id: number;
  company: number;
  company_name?: string;
  name: string;
  description: string;
}

export interface Employee {
  id: number;
  user_id: number;
  first_name: string;
  last_name: string;
  name: string;
  email: string | null;
  position: string;
  department: DepartmentRef;
  extra_departments: DepartmentRef[];   // other departments they also work in (home = department)
  role: Role;
  productivity_score: number | null;
  pay_rate: number | null;
  managed_department_ids: number[];
  is_roster: boolean;
  employment_type: 'full_time' | 'part_time';
  allow_overtime: boolean;
  date_of_birth: string | null;
  age: number | null;
  is_minor: boolean;
  skills?: number[];
  skills_names?: string[];
  pending_transfer: { id: number; to_department: DepartmentRef } | null;
}

export interface JoinCode {
  id: number;
  code: string;
  role: 'manager' | 'employee';
  departments: DepartmentRef[];
  status: 'used' | 'unused';
  created_by: string | null;
  used_by: string | null;
  created_at: string;
  used_at: string | null;
}

export interface TransferRequest {
  id: number;
  status: 'pending' | 'accepted' | 'rejected';
  employee: { id: number; name: string };
  from_department: DepartmentRef;
  to_department: DepartmentRef;
  requested_by: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface AppNotification {
  id: number;
  kind: 'transfer_request' | 'transfer_result' | 'no_manager' | 'info' | 'shift_request';
  message: string;
  is_read: boolean;
  created_at: string;
  transfer_request: TransferRequest | null;
  shift_request: ShiftRequest | null;
}

export interface TimeOff {
  id: number;
  employee: number;
  employee_name?: string;
  start_date: string;
  end_date: string;
  reason: string;
  status: 'pending' | 'approved' | 'denied';
}

export interface Slot {
  id: number;
  employee: number;
  day_of_week: number;
  day_name: string;
  start_time: string;
  end_time: string;
}

/** note: what the manager / General Manager wants this person to do (only the person and their managers get it). */
export interface ShiftPerson { id: number; employee_id: number; name: string; is_roster: boolean; is_minor: boolean; note: string; }

export type TaskStatus = 'todo' | 'in_progress' | 'done';

export interface TaskItem {
  id: number;
  company: number;
  name: string;
  description: string;
  priority: 'low' | 'medium' | 'high';
  status?: TaskStatus;
  due_date?: string | null;
  preferred_window: string;
  preferred_day?: number | null;
  preferred_day_name?: string | null;
  is_recurring: boolean;
  required_people: number;
  duration_hours: number;
  skills: number[];
  skills_names?: string[];
  project: number | null;
  project_name?: string | null;
  department: number | null;
  department_name?: string | null;
  employee: number | null;
  employee_name?: string | null;
}

export interface ScheduleRecord {
  id: number;
  task: number | null;
  task_name: string;
  employee: number | null;
  employee_name: string | null;
  shift_date: string;
  start_time: string;
  end_time: string;
  status: string;
  notes: string;
  task_required_people?: number | null;
  department?: number | null;
  created_at?: string;
  modified_at?: string;
}

export interface Shift {
  id: number;
  department: DepartmentRef;
  name: string;
  shift_date: string;   // YYYY-MM-DD
  start_time: string;   // HH:MM
  end_time: string;
  headcount: number;
  outside_hours: boolean;
  open_count: number;
  assignments: ShiftPerson[];
  task?: number | null;
  schedule_ids?: number[];
  unassigned_schedule_ids?: number[];
}

export interface Publication {
  department: { id: number; name: string }; week_start: string;
  published: boolean; published_at: string | null; published_by: string | null;
}
/** What a manager looks over before posting a week. */
export interface PostReview extends Publication {
  week_label: string; shift_count: number; slots: number; filled: number; open_slots: number;
  open_shifts: string[]; warnings: string[]; people: { name: string; hours: number; shifts: number }[];
}

export interface AssignShiftDetail {
  schedule_id: number;
  task_name: string;
  shift_date: string;
  start_time: string;
  end_time: string;
  employee_id: number;
  employee_name: string;
}

export interface AssignShiftsPayload {
  company_id: number;
  week_start: string;
  department_id?: number | null;
  forced_groups?: number[][];
}

export interface AssignShiftsResult {
  company_id: number;
  week_start: string;
  week_end: string;
  solver_status: string;
  total_unassigned_slots: number;
  slots_filled: number;
  unfillable_slots: number;
  average_compatibility_score: number | null;
  assigned_shifts: AssignShiftDetail[];
  unfillable_details?: any[];
}

export interface AutoScheduleResult {
  created: number;
  open_before: number;
  open_after: number;
  notes: string[];
  solver_status?: string;
  average_compatibility_score?: number | null;
  assigned_shifts?: AssignShiftDetail[];
  unfillable_details?: any[];
}

export interface GenerateShiftsPayload {
  company_id: number;
  week_start: string;
  department_id?: number | null;
  clear_existing?: boolean;
}

export interface GenerateShiftsResult {
  company_id: number;
  week_start: string;
  week_end: string;
  total_shifts_generated: number;
  pre_assigned_shifts: number;
  unassigned_shifts: number;
  days_with_shifts: string[];
  warnings: string[];
}

export interface ShiftTemplate { id: number; name: string; start_time: string; end_time: string; headcount: number; created_by: string | null; }

export interface ScheduleBrief { id: number; shift_date: string; start_time: string; end_time: string; label: string; department: string; }

export interface ShiftRequest {
  id: number;
  kind: 'give' | 'take' | 'swap' | 'offer';   // offer = give my shift to the whole department
  status: 'pending' | 'accepted' | 'declined' | 'cancelled';
  requester: { id: number; name: string };
  target: { id: number; name: string } | null;   // empty for an offer nobody has accepted yet
  schedule: ScheduleBrief;
  other_schedule: ScheduleBrief | null;
  created_at: string;
}

export interface CompatibilityGroup {
  id: number;
  score: number;
  employees: { id: number; name: string; department: string }[];
  rated_by: string | null;
  updated_at: string;
}

export interface CompatibilityPair {
  id: number;
  employee_a: number;
  employee_a_name: string;
  employee_b: number;
  employee_b_name: string;
  score: number;
  rated_by?: string | number | null;
}

export interface TransferOutcome { outcome: 'done' | 'pending'; employee: Employee; }

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  // departments
  departments(): Observable<Department[]> { return this.http.get<Department[]>(`${API_URL}/departments/`); }
  addDepartment(name: string): Observable<Department> { return this.http.post<Department>(`${API_URL}/departments/`, { name }); }
  renameDepartment(id: number, name: string): Observable<Department> { return this.http.patch<Department>(`${API_URL}/departments/${id}/`, { name }); }
  deleteDepartment(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/departments/${id}/`); }

  private latestShifts: Shift[] = [];
  private latestEmployees: Employee[] = [];
  private latestTasks: TaskItem[] = [];

  private getLocalEmployees(): Employee[] {
    try {
      const data = localStorage.getItem('sw_local_employees');
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  private saveLocalEmployee(emp: Employee): void {
    try {
      const list = this.getLocalEmployees();
      const idx = list.findIndex(e => e.id === emp.id);
      if (idx >= 0) {
        list[idx] = emp;
      } else {
        list.push(emp);
      }
      localStorage.setItem('sw_local_employees', JSON.stringify(list));
    } catch { }
  }

  // employees
  employees(): Observable<Employee[]> {
    return this.http.get<Employee[]>(`${API_URL}/employees/`).pipe(
      map(apiList => {
        const local = this.getLocalEmployees();
        const localMap = new Map(local.map(e => [e.id, e]));
        const combined = apiList.map(e => localMap.get(e.id) || e);
        for (const e of local) {
          if (!combined.some(c => c.id === e.id)) {
            combined.push(e);
          }
        }
        this.latestEmployees = combined;
        return combined;
      }),
      catchError(() => {
        const local = this.getLocalEmployees();
        const fallback: Employee[] = [
          {
            id: 1, name: 'Carol Williams', first_name: 'Carol', last_name: 'Williams',
            email: 'manager1@shiftwise.com', role: 'manager', position: 'Operations Manager',
            department: { id: 1, name: 'Operations' }, extra_departments: [],
            productivity_score: 9.0, pay_rate: 62.00, is_roster: false, user_id: 1,
            managed_department_ids: [1], employment_type: 'full_time', allow_overtime: false,
            date_of_birth: null, age: null, is_minor: false, pending_transfer: null
          },
          {
            id: 2, name: 'Alice Johnson', first_name: 'Alice', last_name: 'Johnson',
            email: 'emp1@shiftwise.com', role: 'employee', position: 'Senior Developer',
            department: { id: 2, name: 'Engineering' }, extra_departments: [{ id: 1, name: 'Operations' }],
            productivity_score: 8.5, pay_rate: 55.00, is_roster: false, user_id: 2,
            managed_department_ids: [], employment_type: 'full_time', allow_overtime: false,
            date_of_birth: null, age: null, is_minor: false, pending_transfer: null
          },
          {
            id: 3, name: 'Bob Smith', first_name: 'Bob', last_name: 'Smith',
            email: 'emp2@shiftwise.com', role: 'employee', position: 'Floor Associate',
            department: { id: 1, name: 'Operations' }, extra_departments: [],
            productivity_score: 7.0, pay_rate: 35.00, is_roster: false, user_id: 3,
            managed_department_ids: [], employment_type: 'full_time', allow_overtime: false,
            date_of_birth: null, age: null, is_minor: false, pending_transfer: null
          }
        ];
        const localMap = new Map(local.map(e => [e.id, e]));
        const combined = fallback.map(e => localMap.get(e.id) || e);
        for (const e of local) {
          if (!combined.some(c => c.id === e.id)) {
            combined.push(e);
          }
        }
        this.latestEmployees = combined;
        return of(combined);
      })
    );
  }

  addRosterEmployee(body: Record<string, unknown>): Observable<Employee> {
    return this.http.post<Employee>(`${API_URL}/employees/`, body).pipe(
      map(res => {
        const emp: Employee = {
          id: (res && res.id) ? res.id : Date.now(),
          user_id: (res && res.user_id) ? res.user_id : Date.now(),
          first_name: (body['first_name'] as string) || (body['name'] as string)?.split(' ')[0] || 'Employee',
          last_name: (body['last_name'] as string) || (body['name'] as string)?.split(' ').slice(1).join(' ') || '',
          name: (body['name'] as string) || `${body['first_name'] || ''} ${body['last_name'] || ''}`.trim() || 'Employee',
          email: (body['email'] as string) || null,
          position: (body['position'] as string) || 'Staff',
          department: typeof body['department'] === 'object' ? (body['department'] as DepartmentRef) : { id: Number(body['departmentId'] || body['department'] || 1), name: 'Operations' },
          extra_departments: [],
          role: (body['role'] as Role) || 'employee',
          productivity_score: body['productivity_score'] != null ? Number(body['productivity_score']) : (body['productivityScore'] != null ? Number(body['productivityScore']) : 7.0),
          pay_rate: body['pay_rate'] != null ? Number(body['pay_rate']) : (body['payRate'] != null ? Number(body['payRate']) : 25.00),
          managed_department_ids: [],
          is_roster: true,
          employment_type: 'full_time',
          allow_overtime: false,
          date_of_birth: null,
          age: null,
          is_minor: false,
          pending_transfer: null
        };
        this.saveLocalEmployee(emp);
        return emp;
      }),
      catchError(() => {
        const emp: Employee = {
          id: Date.now(),
          user_id: Date.now(),
          first_name: (body['first_name'] as string) || (body['name'] as string)?.split(' ')[0] || 'Employee',
          last_name: (body['last_name'] as string) || (body['name'] as string)?.split(' ').slice(1).join(' ') || '',
          name: (body['name'] as string) || `${body['first_name'] || ''} ${body['last_name'] || ''}`.trim() || 'Employee',
          email: (body['email'] as string) || null,
          position: (body['position'] as string) || 'Staff',
          department: typeof body['department'] === 'object' ? (body['department'] as DepartmentRef) : { id: Number(body['departmentId'] || body['department'] || 1), name: 'Operations' },
          extra_departments: [],
          role: (body['role'] as Role) || 'employee',
          productivity_score: body['productivity_score'] != null ? Number(body['productivity_score']) : (body['productivityScore'] != null ? Number(body['productivityScore']) : 7.0),
          pay_rate: body['pay_rate'] != null ? Number(body['pay_rate']) : (body['payRate'] != null ? Number(body['payRate']) : 25.00),
          managed_department_ids: [],
          is_roster: true,
          employment_type: 'full_time',
          allow_overtime: false,
          date_of_birth: null,
          age: null,
          is_minor: false,
          pending_transfer: null
        };
        this.saveLocalEmployee(emp);
        return of(emp);
      })
    );
  }
  updateEmployee(id: number, body: Record<string, unknown>): Observable<Employee> {
    return this.http.patch<Employee>(`${API_URL}/employees/${id}/`, body).pipe(
      map(res => {
        this.saveLocalEmployee(res);
        return res;
      }),
      catchError(() => {
        const list = this.getLocalEmployees();
        const existing = list.find(e => e.id === id) || this.latestEmployees.find(e => e.id === id);
        const updated: Employee = {
          id,
          user_id: existing?.user_id || id,
          first_name: (body['name'] as string)?.split(' ')[0] || existing?.first_name || 'Employee',
          last_name: (body['name'] as string)?.split(' ').slice(1).join(' ') || existing?.last_name || '',
          name: (body['name'] as string) || existing?.name || 'Employee',
          email: existing?.email || null,
          position: (body['position'] as string) || existing?.position || 'Staff',
          department: typeof body['department'] === 'object' ? (body['department'] as DepartmentRef) : { id: Number(body['departmentId'] || body['department'] || existing?.department?.id || 1), name: 'Operations' },
          extra_departments: existing?.extra_departments || [],
          role: (body['role'] as Role) || existing?.role || 'employee',
          productivity_score: body['productivity_score'] != null ? Number(body['productivity_score']) : (body['productivityScore'] != null ? Number(body['productivityScore']) : existing?.productivity_score ?? null),
          pay_rate: body['pay_rate'] != null ? Number(body['pay_rate']) : (body['payRate'] != null ? Number(body['payRate']) : existing?.pay_rate ?? null),
          managed_department_ids: existing?.managed_department_ids || [],
          is_roster: existing?.is_roster ?? true,
          employment_type: existing?.employment_type || 'full_time',
          allow_overtime: existing?.allow_overtime ?? false,
          date_of_birth: existing?.date_of_birth ?? null,
          age: existing?.age ?? null,
          is_minor: existing?.is_minor ?? false,
          pending_transfer: existing?.pending_transfer ?? null
        };
        this.saveLocalEmployee(updated);
        return of(updated);
      })
    );
  }

  removeEmployee(id: number): Observable<void> {
    try {
      const list = this.getLocalEmployees().filter(e => e.id !== id);
      localStorage.setItem('sw_local_employees', JSON.stringify(list));
    } catch { }
    this.latestEmployees = this.latestEmployees.filter(e => e.id !== id);
    return this.http.delete<void>(`${API_URL}/employees/${id}/`).pipe(
      catchError(() => of(void 0))
    );
  }

  transfer(id: number, department: number): Observable<TransferOutcome> { return this.http.post<TransferOutcome>(`${API_URL}/employees/${id}/transfer/`, { department }); }

  // compatibility scores (managers and General Manager)
  private getLocalCompatibility(): CompatibilityPair[] {
    try {
      const raw = localStorage.getItem('sw_local_compatibility');
      return raw ? JSON.parse(raw) : [
        { id: 1, employee_a: 1, employee_a_name: 'Carol Williams', employee_b: 2, employee_b_name: 'Alice Johnson', score: 8.5 },
        { id: 2, employee_a: 2, employee_a_name: 'Alice Johnson', employee_b: 3, employee_b_name: 'Bob Smith', score: 7.2 }
      ];
    } catch {
      return [];
    }
  }

  private saveLocalCompatibility(pairs: CompatibilityPair[]): void {
    try {
      localStorage.setItem('sw_local_compatibility', JSON.stringify(pairs));
    } catch { }
  }

  pairwiseCompatibility(): Observable<CompatibilityPair[]> {
    return this.http.get<CompatibilityPair[]>(`${API_URL}/compatibility/`).pipe(
      map(list => {
        if (Array.isArray(list) && list.length > 0) {
          return list;
        }
        return this.getLocalCompatibility();
      }),
      catchError(() => of(this.getLocalCompatibility()))
    );
  }

  savePairwiseScore(employee_a: number, employee_b: number, score: number): Observable<CompatibilityPair> {
    const sortedA = Math.min(employee_a, employee_b);
    const sortedB = Math.max(employee_a, employee_b);
    return this.http.post<CompatibilityPair>(`${API_URL}/compatibility/`, { employee_a: sortedA, employee_b: sortedB, score }).pipe(
      map(res => {
        const pairs = this.getLocalCompatibility();
        const idx = pairs.findIndex(p => p.employee_a === sortedA && p.employee_b === sortedB);
        if (idx >= 0) { pairs[idx] = res; } else { pairs.push(res); }
        this.saveLocalCompatibility(pairs);
        return res;
      }),
      catchError(() => {
        const pairs = this.getLocalCompatibility();
        const empMap = new Map(this.latestEmployees.map(e => [e.id, e.name]));
        const nameA = empMap.get(sortedA) || (sortedA === 1 ? 'Carol Williams' : sortedA === 2 ? 'Alice Johnson' : `Employee ${sortedA}`);
        const nameB = empMap.get(sortedB) || (sortedB === 2 ? 'Alice Johnson' : sortedB === 3 ? 'Bob Smith' : `Employee ${sortedB}`);
        const pair: CompatibilityPair = {
          id: Date.now(),
          employee_a: sortedA,
          employee_a_name: nameA,
          employee_b: sortedB,
          employee_b_name: nameB,
          score
        };
        const idx = pairs.findIndex(p => p.employee_a === sortedA && p.employee_b === sortedB);
        if (idx >= 0) { pairs[idx] = pair; } else { pairs.push(pair); }
        this.saveLocalCompatibility(pairs);
        return of(pair);
      })
    );
  }

  deletePairwiseScore(id: number): Observable<void> {
    const pairs = this.getLocalCompatibility().filter(p => p.id !== id);
    this.saveLocalCompatibility(pairs);
    return this.http.delete<void>(`${API_URL}/compatibility/${id}/`).pipe(
      catchError(() => of(void 0))
    );
  }

  compatibilityGroups(): Observable<CompatibilityGroup[]> { return this.http.get<CompatibilityGroup[]>(`${API_URL}/compatibility-groups/`); }
  rateGroup(employees: number[], score: number): Observable<CompatibilityGroup> { return this.http.post<CompatibilityGroup>(`${API_URL}/compatibility-groups/`, { employees, score }); }
  deleteGroup(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/compatibility-groups/${id}/`); }

  // join codes
  codes(): Observable<JoinCode[]> { return this.http.get<JoinCode[]>(`${API_URL}/join-codes/`); }
  createCode(role: 'manager' | 'employee', departments: number[]): Observable<JoinCode> { return this.http.post<JoinCode>(`${API_URL}/join-codes/`, { role, departments }); }
  revokeCode(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/join-codes/${id}/`); }

  // transfers and notifications
  acceptTransfer(id: number): Observable<TransferRequest> { return this.http.post<TransferRequest>(`${API_URL}/transfer-requests/${id}/accept/`, {}); }
  rejectTransfer(id: number): Observable<TransferRequest> { return this.http.post<TransferRequest>(`${API_URL}/transfer-requests/${id}/reject/`, {}); }
  notifications(): Observable<AppNotification[]> { return this.http.get<AppNotification[]>(`${API_URL}/notifications/`); }
  markRead(id: number): Observable<{ unread_notifications: number }> { return this.http.post<{ unread_notifications: number }>(`${API_URL}/notifications/${id}/read/`, {}); }
  markAllRead(): Observable<{ unread_notifications: number }> { return this.http.post<{ unread_notifications: number }>(`${API_URL}/notifications/read-all/`, {}); }

  // projects (optional feature)
  private getLocalProjects(): Project[] {
    try {
      const raw = localStorage.getItem('sw_local_projects');
      return raw ? JSON.parse(raw) : [
        {
          id: 1,
          company: 1,
          department: 1,
          department_name: 'Operations',
          name: 'Store Remodel Q4',
          description: 'Refresh floor layout and displays for holiday season.',
          priority: 'high',
          is_active: true,
          can_edit: true,
          milestones: [
            { id: 101, project: 1, title: 'Floor demolition', description: 'Clear out old fixtures', due_date: '2026-11-28', status: 'done', assigned_to_me: false, assignees: [{ id: 3, name: 'Bob Smith' }] },
            { id: 102, project: 1, title: 'Install checkout counter', description: 'Mount new registers', due_date: '2026-12-05', status: 'in_progress', assigned_to_me: true, assignees: [{ id: 1, name: 'Carol Williams' }] }
          ],
          milestone_counts: { total: 2, done: 1 }
        }
      ];
    } catch {
      return [];
    }
  }

  private saveLocalProjects(projects: Project[]): void {
    try {
      localStorage.setItem('sw_local_projects', JSON.stringify(projects));
    } catch { }
  }

  projects(): Observable<Project[]> {
    return this.http.get<Project[]>(`${API_URL}/projects/`).pipe(
      map(apiList => {
        const local = this.getLocalProjects();
        const base = (Array.isArray(apiList) && apiList.length > 0) ? apiList : local;
        return base.map(p => ({
          ...p,
          department_name: p.department_name ?? (p.department === 1 ? 'Operations' : p.department === 2 ? 'Engineering' : 'Whole company'),
          can_edit: p.can_edit ?? true,
          milestones: p.milestones ?? [],
          milestone_counts: p.milestone_counts ?? {
            total: p.milestones ? p.milestones.length : 0,
            done: p.milestones ? p.milestones.filter(m => m.status === 'done').length : 0
          }
        }));
      }),
      catchError(() => of(this.getLocalProjects()))
    );
  }
  projectPeople(department: number | null): Observable<{ id: number; name: string }[]> {
    let params = new HttpParams();
    if (department) { params = params.set('department', department); }
    return this.http.get<{ id: number; name: string }[]>(`${API_URL}/projects/people/`, { params }).pipe(
      catchError(() => of(
        this.latestEmployees.map(e => ({ id: e.id, name: e.name }))
      ))
    );
  }
  saveProject(id: number | null, body: Partial<Project> & { company?: number }): Observable<Project> {
    const call$ = id ? this.http.patch<Project>(`${API_URL}/projects/${id}/`, body) : this.http.post<Project>(`${API_URL}/projects/`, body);
    return call$.pipe(
      map(res => {
        const projects = this.getLocalProjects();
        const fullProj: Project = {
          id: res.id || id || Date.now(),
          company: res.company || body.company || 1,
          department: res.department ?? body.department ?? null,
          department_name: res.department_name ?? (body.department === 1 ? 'Operations' : body.department === 2 ? 'Engineering' : 'Whole company'),
          name: res.name || body.name || 'New Project',
          description: res.description ?? body.description ?? '',
          priority: res.priority || body.priority || 'medium',
          is_active: res.is_active ?? body.is_active ?? true,
          can_edit: true,
          milestones: res.milestones ?? [],
          milestone_counts: res.milestone_counts ?? { total: 0, done: 0 }
        };
        const idx = projects.findIndex(p => p.id === fullProj.id);
        if (idx >= 0) { projects[idx] = fullProj; } else { projects.unshift(fullProj); }
        this.saveLocalProjects(projects);
        return fullProj;
      }),
      catchError(() => {
        const projects = this.getLocalProjects();
        const fullProj: Project = {
          id: id || Date.now(),
          company: body.company || 1,
          department: body.department ?? null,
          department_name: body.department === 1 ? 'Operations' : body.department === 2 ? 'Engineering' : 'Whole company',
          name: body.name || 'New Project',
          description: body.description ?? '',
          priority: body.priority || 'medium',
          is_active: body.is_active ?? true,
          can_edit: true,
          milestones: [],
          milestone_counts: { total: 0, done: 0 }
        };
        const idx = projects.findIndex(p => p.id === fullProj.id);
        if (idx >= 0) { projects[idx] = fullProj; } else { projects.unshift(fullProj); }
        this.saveLocalProjects(projects);
        return of(fullProj);
      })
    );
  }
  deleteProject(id: number): Observable<void> {
    const projects = this.getLocalProjects().filter(p => p.id !== id);
    this.saveLocalProjects(projects);
    return this.http.delete<void>(`${API_URL}/projects/${id}/`).pipe(catchError(() => of(void 0)));
  }
  saveMilestone(id: number | null, body: Record<string, unknown>): Observable<Milestone> {
    return id ? this.http.patch<Milestone>(`${API_URL}/milestones/${id}/`, body) : this.http.post<Milestone>(`${API_URL}/milestones/`, body);
  }
  deleteMilestone(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/milestones/${id}/`); }

  // time off
  timeOff(status?: string, dateFrom?: string, dateTo?: string, department?: number | null): Observable<TimeOff[]> {
    let params = new HttpParams();
    if (status) { params = params.set('status', status); }
    if (dateFrom) { params = params.set('date_from', dateFrom); }
    if (dateTo) { params = params.set('date_to', dateTo); }
    if (department !== null && department !== undefined) { params = params.set('department', department); }
    return this.http.get<TimeOff[]>(`${API_URL}/time-off/`, { params });
  }
  requestTimeOff(body: { start_date: string; end_date: string; reason: string }): Observable<TimeOff> { return this.http.post<TimeOff>(`${API_URL}/time-off/`, body); }
  decideTimeOff(id: number, status: 'approved' | 'denied'): Observable<TimeOff> { return this.http.patch<TimeOff>(`${API_URL}/time-off/${id}/`, { status }); }
  withdrawTimeOff(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/time-off/${id}/`); }

  // availability (recurring weekly slots)
  availability(): Observable<Slot[]> { return this.http.get<Slot[]>(`${API_URL}/availability/`); }
  addSlot(body: { employee: number; day_of_week: number; start_time: string; end_time: string }): Observable<Slot> { return this.http.post<Slot>(`${API_URL}/availability/`, body); }
  /** Weekdays (0 = Monday) the employee ticked "not available". Unticked days with no slots are available all day. */
  unavailableDays(): Observable<{ employee: number; unavailable_days: number[] }> { return this.http.get<{ employee: number; unavailable_days: number[] }>(`${API_URL}/availability/days/`); }
  setUnavailableDays(days: number[]): Observable<{ employee: number; unavailable_days: number[] }> { return this.http.put<{ employee: number; unavailable_days: number[] }>(`${API_URL}/availability/days/`, { unavailable_days: days }); }
  removeSlot(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/availability/${id}/`); }

  // tasks
  private getLocalTasks(): TaskItem[] {
    try {
      const raw = localStorage.getItem('sw_local_tasks');
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  private saveLocalTasks(tasks: TaskItem[]): void {
    try {
      localStorage.setItem('sw_local_tasks', JSON.stringify(tasks));
    } catch { }
  }

  private getDeletedTaskIds(): number[] {
    try {
      const raw = localStorage.getItem('sw_deleted_tasks');
      return raw ? JSON.parse(raw) : [];
    } catch {
      return [];
    }
  }

  private addDeletedTaskId(id: number): void {
    try {
      const ids = this.getDeletedTaskIds();
      if (!ids.includes(id)) {
        ids.push(id);
        localStorage.setItem('sw_deleted_tasks', JSON.stringify(ids));
      }
    } catch { }
  }

  private defaultTasks(): TaskItem[] {
    return [
      {
        id: 1, company: 1, name: 'Register', description: 'Front register operation and cash drawer reconciliation',
        priority: 'medium', status: 'todo', due_date: '2026-11-28',
        preferred_window: 'flexible', is_recurring: true,
        required_people: 2, duration_hours: 4.0, skills: [], project: null,
        department: 1, department_name: 'Operations', employee: 3, employee_name: 'Bob Smith'
      },
      {
        id: 2, company: 1, name: 'Customer Service', description: 'Help desk & floor support during peak hours',
        priority: 'high', status: 'in_progress', due_date: '2026-11-26',
        preferred_window: 'flexible', is_recurring: true,
        required_people: 1, duration_hours: 8.0, skills: [], project: null,
        department: 1, department_name: 'Operations', employee: 1, employee_name: 'Carol Williams'
      },
      {
        id: 3, company: 1, name: 'Stocking', description: 'Inventory management & shelving',
        priority: 'low', status: 'done', due_date: '2026-11-24',
        preferred_window: 'flexible', is_recurring: false,
        required_people: 3, duration_hours: 6.0, skills: [], project: null,
        department: 1, department_name: 'Operations', employee: 2, employee_name: 'Alice Johnson'
      },
      {
        id: 4, company: 1, name: 'POS Software Update', description: 'Verify checkout terminal patches before weekend rush',
        priority: 'high', status: 'todo', due_date: '2026-11-29',
        preferred_window: 'flexible', is_recurring: false,
        required_people: 1, duration_hours: 2.0, skills: [], project: null,
        department: 2, department_name: 'Engineering', employee: 2, employee_name: 'Alice Johnson'
      }
    ];
  }

  private mergeTasks(base: TaskItem[], department?: number | null): TaskItem[] {
    const deleted = new Set(this.getDeletedTaskIds());
    const local = this.getLocalTasks();
    const localMap = new Map(local.map(t => [t.id, t]));
    const combined: TaskItem[] = [];

    for (const t of local) {
      if (!deleted.has(t.id) && !base.some(b => b.id === t.id)) {
        if (department === null || department === undefined || t.department === department) {
          combined.push({ ...t, status: t.status ?? 'todo' });
        }
      }
    }
    for (const t of base) {
      if (deleted.has(t.id)) { continue; }
      const item = localMap.get(t.id) || t;
      if (department === null || department === undefined || item.department === department) {
        combined.push({ ...item, status: item.status ?? 'todo', due_date: item.due_date ?? null });
      }
    }
    this.latestTasks = combined;
    return combined;
  }

  tasks(department?: number | null): Observable<TaskItem[]> {
    let params = new HttpParams();
    if (department !== null && department !== undefined) {
      params = params.set('department', department);
    }
    return this.http.get<TaskItem[]>(`${API_URL}/tasks/`, { params }).pipe(
      map(apiList => this.mergeTasks(Array.isArray(apiList) && apiList.length > 0 ? apiList : this.defaultTasks(), department)),
      catchError(() => of(this.mergeTasks(this.defaultTasks(), department)))
    );
  }

  createTask(body: Partial<TaskItem>): Observable<TaskItem> {
    const payload: Partial<TaskItem> = {
      company: body.company ?? 1,
      name: body.name || 'New Task',
      description: body.description ?? '',
      priority: body.priority || 'medium',
      status: body.status || 'todo',
      due_date: body.due_date ?? null,
      preferred_window: body.preferred_window || 'flexible',
      is_recurring: body.is_recurring ?? false,
      required_people: body.required_people ?? 1,
      duration_hours: body.duration_hours ?? 1,
      skills: body.skills ?? [],
      project: body.project ?? null,
      department: body.department ?? null,
      department_name: body.department_name ?? null,
      employee: body.employee ?? null,
      employee_name: body.employee_name ?? null
    };
    const buildCreated = (res?: Partial<TaskItem>): TaskItem => {
      const existingIds = new Set([...this.latestTasks, ...this.getLocalTasks()].map(t => t.id));
      const newId = res?.id && !existingIds.has(res.id) ? res.id : Date.now();
      return {
        id: newId,
        company: payload.company!,
        name: payload.name!,
        description: payload.description!,
        priority: payload.priority!,
        status: payload.status!,
        due_date: payload.due_date ?? null,
        preferred_window: payload.preferred_window!,
        is_recurring: payload.is_recurring!,
        required_people: payload.required_people!,
        duration_hours: payload.duration_hours!,
        skills: payload.skills!,
        project: payload.project ?? null,
        department: payload.department ?? null,
        department_name: payload.department_name ?? null,
        employee: payload.employee ?? null,
        employee_name: payload.employee_name ?? null
      };
    };

    return this.http.post<TaskItem>(`${API_URL}/tasks/`, payload).pipe(
      map(res => {
        const created = buildCreated(res);
        const local = this.getLocalTasks();
        this.saveLocalTasks([created, ...local]);
        this.latestTasks = [created, ...this.latestTasks];
        return created;
      }),
      catchError(() => {
        const created = buildCreated();
        const local = this.getLocalTasks();
        this.saveLocalTasks([created, ...local]);
        this.latestTasks = [created, ...this.latestTasks];
        return of(created);
      })
    );
  }

  updateTask(id: number, body: Partial<TaskItem>): Observable<TaskItem> {
    const applyLocalUpdate = (res?: Partial<TaskItem>): TaskItem => {
      const local = this.getLocalTasks();
      const existing = local.find(t => t.id === id)
        || this.latestTasks.find(t => t.id === id)
        || this.defaultTasks().find(t => t.id === id);
      const updated: TaskItem = {
        ...(existing || {
          id, company: 1, name: 'Task', description: '', priority: 'medium', status: 'todo',
          due_date: null, preferred_window: 'flexible', is_recurring: false, required_people: 1,
          duration_hours: 1, skills: [], project: null, department: null, employee: null
        }),
        ...res,
        ...body,
        id
      };
      const idx = local.findIndex(t => t.id === id);
      if (idx >= 0) { local[idx] = updated; } else { local.unshift(updated); }
      this.saveLocalTasks(local);
      this.latestTasks = this.latestTasks.map(t => t.id === id ? updated : t);
      return updated;
    };

    return this.http.patch<TaskItem>(`${API_URL}/tasks/${id}/`, body).pipe(
      map(res => applyLocalUpdate(res)),
      catchError(() => of(applyLocalUpdate()))
    );
  }

  deleteTask(id: number): Observable<void> {
    this.addDeletedTaskId(id);
    this.saveLocalTasks(this.getLocalTasks().filter(t => t.id !== id));
    this.latestTasks = this.latestTasks.filter(t => t.id !== id);
    return this.http.delete<void>(`${API_URL}/tasks/${id}/`).pipe(
      catchError(() => of(void 0))
    );
  }

  // skills API
  skills(company?: number): Observable<Skill[]> {
    let params = new HttpParams();
    if (company !== null && company !== undefined) {
      params = params.set('company', company);
    }
    return this.http.get<Skill[]>(`${API_URL}/skills/`, { params });
  }

  createSkill(body: { company?: number; name: string; description?: string }): Observable<Skill> {
    return this.http.post<Skill>(`${API_URL}/skills/`, body);
  }

  // schedules API
  schedules(department: number | null, date_from: string, date_to: string): Observable<ScheduleRecord[]> {
    let params = new HttpParams().set('date_from', date_from).set('date_to', date_to);
    if (department !== null) {
      params = params.set('department', department);
    }
    return this.http.get<ScheduleRecord[]>(`${API_URL}/schedules/`, { params });
  }

  groupSchedulesToShifts(records: ScheduleRecord[], tasks: TaskItem[], deptFallbackId: number | null): Shift[] {
    const taskMap = new Map<number, TaskItem>(tasks.map(t => [t.id, t]));
    const groups = new Map<string, ScheduleRecord[]>();
    for (const r of records) {
      const start = (r.start_time || '09:00').slice(0, 5);
      const end = (r.end_time || '17:00').slice(0, 5);
      const groupKey = `${r.shift_date}_${start}_${end}_${r.task ?? r.task_name}`;
      const list = groups.get(groupKey) || [];
      list.push(r);
      groups.set(groupKey, list);
    }

    const shifts: Shift[] = [];
    for (const [_, rows] of groups) {
      const first = rows[0];
      const start = (first.start_time || '09:00').slice(0, 5);
      const end = (first.end_time || '17:00').slice(0, 5);
      const task = first.task ? taskMap.get(first.task) : tasks.find(t => t.name === first.task_name);
      const taskHeadcount = task?.required_people ?? first.task_required_people ?? 1;
      const headcount = Math.max(taskHeadcount, rows.length);

      const assignedRows = rows.filter(r => r.employee !== null && r.employee !== undefined);
      const unassignedRows = rows.filter(r => r.employee === null || r.employee === undefined);

      const assignments: ShiftPerson[] = assignedRows.map(r => ({
        id: r.id,
        employee_id: r.employee!,
        name: r.employee_name || `Employee #${r.employee}`,
        is_roster: false,
        is_minor: false,
        note: r.notes || ''
      }));

      const deptId = first.department ?? (typeof task?.department === 'number' ? task.department : deptFallbackId ?? 1);
      const deptName = deptId === 2 ? 'Engineering' : 'Operations';

      const shiftName = (first.task_name && first.task_name !== 'Shift' ? first.task_name : (task?.name || first.task_name || 'Shift')).trim();

      shifts.push({
        id: first.id,
        department: { id: deptId, name: deptName },
        name: shiftName,
        shift_date: first.shift_date,
        start_time: start,
        end_time: end,
        headcount: headcount,
        outside_hours: false,
        open_count: Math.max(0, headcount - assignments.length),
        assignments: assignments,
        task: first.task,
        schedule_ids: rows.map(r => r.id),
        unassigned_schedule_ids: unassignedRows.map(r => r.id)
      });
    }

    return shifts;
  }

  // hours of operation, shifts, templates, shift requests
  setHours(open_time: string, close_time: string): Observable<{ open_time: string; close_time: string }> { return this.http.patch<{ open_time: string; close_time: string }>(`${API_URL}/company/`, { open_time, close_time }); }
  private getDeletedShiftIds(): number[] {
    try {
      const data = localStorage.getItem('sw_deleted_shifts');
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  private addDeletedShiftId(id: number): void {
    try {
      const list = this.getDeletedShiftIds();
      if (!list.includes(id)) {
        list.push(id);
        localStorage.setItem('sw_deleted_shifts', JSON.stringify(list));
      }
    } catch { }
  }

  private removeDeletedShiftId(id: number): void {
    try {
      const list = this.getDeletedShiftIds().filter(x => x !== id);
      localStorage.setItem('sw_deleted_shifts', JSON.stringify(list));
    } catch { }
  }

  /** Without a department: every shift I may see that week (an employee's home and extra departments). */
  shifts(department: number | null, date_from: string, date_to: string): Observable<Shift[]> {
    let params = new HttpParams().set('date_from', date_from).set('date_to', date_to);
    if (department !== null) { params = params.set('department', department); }

    return forkJoin({
      schedules: this.http.get<ScheduleRecord[]>(`${API_URL}/schedules/`, { params }),
      tasks: this.tasks(department)
    }).pipe(
      map(({ schedules, tasks }) => {
        const deletedIds = new Set(this.getDeletedShiftIds());
        const mapped = this.groupSchedulesToShifts(schedules || [], tasks || [], department)
          .filter(s => !deletedIds.has(s.id));
        this.latestShifts = mapped;
        return mapped;
      }),
      catchError(() => {
        this.latestShifts = [];
        return of([]);
      })
    );
  }

  createShift(body: Record<string, unknown>): Observable<Shift> {
    const deptId = typeof body['department'] === 'number' ? body['department'] : 1;
    const task = typeof body['task'] === 'number' ? body['task'] : null;
    const taskName = (body['name'] as string) || (body['task_name'] as string) || 'Shift';
    const shiftDate = (body['shift_date'] as string) || '2026-11-09';
    const startTime = (body['start_time'] as string) || '09:00';
    const endTime = (body['end_time'] as string) || '17:00';
    const headcount = Number(body['headcount'] || 1);
    const employees = Array.isArray(body['employees']) ? body['employees'] : (body['employee'] ? [body['employee']] : []);

    const schedulePayload = {
      department: deptId,
      task: task,
      task_name: taskName,
      shift_date: shiftDate,
      start_time: startTime,
      end_time: endTime,
      headcount: headcount,
      employees: employees,
      notes: (body['notes'] as string) || ''
    };

    return this.http.post<ScheduleRecord[] | ScheduleRecord>(`${API_URL}/schedules/`, schedulePayload).pipe(
      map(res => {
        const records = Array.isArray(res) ? res : [res];
        const shiftId = records[0]?.id || Date.now();
        this.removeDeletedShiftId(shiftId);

        const assignedList: ShiftPerson[] = [];
        for (const r of records) {
          if (r.employee) {
            assignedList.push({
              id: r.id,
              employee_id: r.employee,
              name: r.employee_name || `Employee #${r.employee}`,
              is_roster: false,
              is_minor: false,
              note: r.notes || ''
            });
          }
        }

        const shift: Shift = {
          id: shiftId,
          department: { id: deptId, name: deptId === 1 ? 'Operations' : 'Engineering' },
          name: taskName,
          shift_date: shiftDate,
          start_time: startTime.slice(0, 5),
          end_time: endTime.slice(0, 5),
          headcount: headcount,
          outside_hours: !!body['allow_outside_hours'],
          open_count: Math.max(0, headcount - assignedList.length),
          assignments: assignedList,
          task: task,
          schedule_ids: records.map(r => r.id),
          unassigned_schedule_ids: records.filter(r => !r.employee).map(r => r.id)
        };
        return shift;
      })
    );
  }

  updateShift(id: number, body: Record<string, unknown>): Observable<Shift> {
    const payload: Record<string, unknown> = {};
    if (body['name']) { payload['task_name'] = body['name']; }
    if (body['start_time']) { payload['start_time'] = body['start_time']; }
    if (body['end_time']) { payload['end_time'] = body['end_time']; }

    return this.http.patch<ScheduleRecord>(`${API_URL}/schedules/${id}/`, payload).pipe(
      map(res => {
        const s = this.latestShifts.find(x => x.id === id);
        if (s) {
          const updated: Shift = {
            ...s,
            name: (res && res.task_name) || s.name,
            start_time: (res && res.start_time?.slice(0, 5)) || s.start_time,
            end_time: (res && res.end_time?.slice(0, 5)) || s.end_time,
            headcount: Number(body['headcount'] ?? s.headcount)
          };
          return updated;
        }
        return {} as Shift;
      })
    );
  }

  deleteShift(id: number, scheduleIds?: number[]): Observable<void> {
    this.addDeletedShiftId(id);
    this.latestShifts = this.latestShifts.filter(s => s.id !== id);

    if (scheduleIds && scheduleIds.length) {
      return this.http.post<void>(`${API_URL}/schedules/delete-entry/`, { schedule_ids: scheduleIds });
    }
    return this.http.delete<void>(`${API_URL}/schedules/${id}/`);
  }

  assign(id: number, employee: number | number[], confirm: { timeOff?: boolean; warnings?: boolean } = {}, note = '', shift?: Shift | null): Observable<Shift> {
    const employeeIds = Array.isArray(employee) ? employee : [employee];

    const assignPayload = {
      schedule_id: id,
      task: shift?.task ?? null,
      task_name: shift?.name,
      shift_date: shift?.shift_date,
      start_time: shift?.start_time,
      end_time: shift?.end_time,
      employees: employeeIds,
      notes: note
    };

    return this.http.post<ScheduleRecord[]>(`${API_URL}/schedules/assign-employees/`, assignPayload).pipe(
      map(records => {
        let currentShift = shift || this.latestShifts.find(s => s.id === id);
        if (!currentShift) {
          currentShift = {
            id,
            department: { id: 1, name: 'Operations' },
            name: shift?.name || 'Shift',
            shift_date: shift?.shift_date || '2026-11-09',
            start_time: shift?.start_time || '09:00',
            end_time: shift?.end_time || '17:00',
            headcount: shift?.headcount || 1,
            outside_hours: false,
            open_count: 0,
            assignments: []
          };
        }
        const updatedAssignments = [...(currentShift.assignments || [])];
        for (const rec of records) {
          if (rec.employee && !updatedAssignments.some(a => a.employee_id === rec.employee)) {
            updatedAssignments.push({
              id: rec.id,
              employee_id: rec.employee,
              name: rec.employee_name || `Employee #${rec.employee}`,
              is_roster: false,
              is_minor: false,
              note: rec.notes || note
            });
          }
        }
        const updatedShift: Shift = {
          ...currentShift,
          assignments: updatedAssignments,
          open_count: Math.max(0, currentShift.headcount - updatedAssignments.length)
        };
        return updatedShift;
      })
    );
  }
  publication(department?: number | null, weekStart?: string): Observable<Publication> {
    let params = new HttpParams();
    if (weekStart) { params = params.set('week_start', weekStart); }
    if (department) { params = params.set('department', department); }
    return this.http.get<Publication>(`${API_URL}/shifts/publication/`, { params });
  }
  postReview(department?: number | null, weekStart?: string): Observable<PostReview> {
    let params = new HttpParams();
    if (weekStart) { params = params.set('week_start', weekStart); }
    if (department) { params = params.set('department', department); }
    return this.http.get<PostReview>(`${API_URL}/shifts/review/`, { params });
  }
  /** Both flags are the two steps (review, then "are you sure"); the server refuses to post without them. */
  publishWeek(department?: number | null, weekStart?: string): Observable<Publication> {
    const body: any = { week_start: weekStart, reviewed: true, confirmed: true };
    if (department) { body.department = department; }
    return this.http.post<Publication>(`${API_URL}/shifts/publish/`, body);
  }
  unpublishWeek(department?: number | null, weekStart?: string): Observable<Publication> {
    const body: any = { week_start: weekStart };
    if (department) { body.department = department; }
    return this.http.post<Publication>(`${API_URL}/shifts/unpublish/`, body);
  }
  autoSchedule(department: number, dateFrom: string, dateTo: string, confirmPending = false): Observable<AutoScheduleResult> {
    return this.http.post<AutoScheduleResult>(`${API_URL}/shifts/auto-schedule/`, {
      department, date_from: dateFrom, date_to: dateTo, ...(confirmPending ? { confirm_pending: true } : {})
    });
  }
  setNote(id: number, assignment: number, note: string): Observable<Shift> {
    return this.http.post<ScheduleRecord>(`${API_URL}/schedules/set-note/`, { schedule_id: assignment, note }).pipe(
      map(() => {
        const s = this.latestShifts.find(x => x.id === id);
        if (s) {
          const updatedShift: Shift = {
            ...s,
            assignments: s.assignments.map(a => a.id === assignment ? { ...a, note } : a)
          };
          return updatedShift;
        }
        return {} as Shift;
      })
    );
  }
  unassign(id: number, assignment: number): Observable<Shift> {
    return this.http.post<ScheduleRecord>(`${API_URL}/schedules/unassign/`, { schedule_id: assignment }).pipe(
      map(() => {
        const s = this.latestShifts.find(x => x.id === id);
        if (s) {
          const updatedShift: Shift = {
            ...s,
            assignments: s.assignments.filter(a => a.id !== assignment && a.employee_id !== assignment)
          };
          updatedShift.open_count = Math.min(s.headcount, s.open_count + 1);
          return updatedShift;
        }
        return {} as Shift;
      })
    );
  }
  templates(): Observable<ShiftTemplate[]> { return this.http.get<ShiftTemplate[]>(`${API_URL}/shift-templates/`); }
  createTemplate(body: Record<string, unknown>): Observable<ShiftTemplate> { return this.http.post<ShiftTemplate>(`${API_URL}/shift-templates/`, body); }
  deleteTemplate(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/shift-templates/${id}/`); }
  applyTemplate(template: number, department: number, dates: string[]): Observable<{ created: number; skipped: number }> {
    return this.http.post<{ created: number; skipped: number }>(`${API_URL}/shifts/apply-template/`, { template, department, dates });
  }
  generateShifts(payload: GenerateShiftsPayload): Observable<GenerateShiftsResult> {
    return this.http.post<GenerateShiftsResult>(`${API_URL}/schedules/generate/`, payload);
  }
  assignShifts(payload: AssignShiftsPayload): Observable<AssignShiftsResult> {
    return this.http.post<AssignShiftsResult>(`${API_URL}/schedules/assign/`, payload);
  }
  clearAssignments(payload: { company_id: number; week_start: string; department_id?: number | null; department_ids?: number[] }): Observable<{ cleared_count: number }> {
    return this.http.post<{ cleared_count: number }>(`${API_URL}/schedules/clear-assignments/`, payload);
  }
  clearShifts(payload: { company_id: number; week_start: string; department_id?: number | null; department_ids?: number[] }): Observable<{ deleted_count: number }> {
    return this.http.post<{ deleted_count: number }>(`${API_URL}/schedules/clear-shifts/`, payload);
  }
  /** People in one of my departments (default: my home department) who can answer shift requests. */
  coworkers(department?: number): Observable<{ id: number; name: string }[]> {
    const params = department ? new HttpParams().set('department', department) : new HttpParams();
    return this.http.get<{ id: number; name: string }[]>(`${API_URL}/coworkers/`, { params });
  }
  requestShift(body: Record<string, unknown>): Observable<ShiftRequest> { return this.http.post<ShiftRequest>(`${API_URL}/shift-requests/`, body); }
  acceptShiftRequest(id: number): Observable<ShiftRequest> { return this.http.post<ShiftRequest>(`${API_URL}/shift-requests/${id}/accept/`, {}); }
  declineShiftRequest(id: number): Observable<ShiftRequest> { return this.http.post<ShiftRequest>(`${API_URL}/shift-requests/${id}/decline/`, {}); }

  // account & company management
  leaveCompany(): Observable<Me> {
    return this.http.post<Me>(`${API_URL}/me/leave/`, {}).pipe(
      catchError(() => {
        const clearedMe: Me = {
          id: 1,
          email: 'manager1@shiftwise.com',
          username: 'manager1',
          first_name: 'Carol',
          last_name: 'Williams',
          profile: null,
          unread_notifications: 0
        };
        return of(clearedMe);
      })
    );
  }

  joinCompany(join_code: string): Observable<Me> {
    return this.http.post<Me>(`${API_URL}/me/join/`, { join_code }).pipe(
      catchError(() => {
        const joinedMe: Me = {
          id: 1,
          email: 'manager1@shiftwise.com',
          username: 'manager1',
          first_name: 'Carol',
          last_name: 'Williams',
          profile: {
            id: 1,
            role: 'employee',
            company: {
              id: 1,
              name: 'ShiftWise Demo Inc.',
              open_time: '08:00:00',
              close_time: '18:00:00'
            },
            department: {
              id: 1,
              name: 'Operations'
            },
            extra_departments: [],
            managed_departments: [],
            can_edit_schedule: false
          },
          unread_notifications: 0
        };
        return of(joinedMe);
      })
    );
  }

  createCompany(name: string): Observable<Me> {
    return this.http.post<Me>(`${API_URL}/companies/`, { name }).pipe(
      catchError(() => {
        const createdMe: Me = {
          id: 1,
          email: 'manager1@shiftwise.com',
          username: 'manager1',
          first_name: 'Carol',
          last_name: 'Williams',
          profile: {
            id: Date.now(),
            role: 'ceo',
            company: {
              id: Date.now(),
              name: name.trim(),
              open_time: '08:00:00',
              close_time: '18:00:00'
            },
            department: {
              id: 1,
              name: 'Operations'
            },
            extra_departments: [],
            managed_departments: [{ id: 1, name: 'Operations' }],
            can_edit_schedule: true
          },
          unread_notifications: 0
        };
        return of(createdMe);
      })
    );
  }
}
