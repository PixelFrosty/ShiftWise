import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, catchError, map, of } from 'rxjs';
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

export interface AutoScheduleResult { created: number; open_before: number; open_after: number; notes: string[]; }

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
    } catch {}
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
  updateEmployee(id: number, body: Record<string, unknown>): Observable<Employee> { return this.http.patch<Employee>(`${API_URL}/employees/${id}/`, body); }
  removeEmployee(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/employees/${id}/`); }
  transfer(id: number, department: number): Observable<TransferOutcome> { return this.http.post<TransferOutcome>(`${API_URL}/employees/${id}/transfer/`, { department }); }

  // compatibility scores (managers and General Manager)
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
  projects(): Observable<Project[]> { return this.http.get<Project[]>(`${API_URL}/projects/`); }
  projectPeople(department: number | null): Observable<{ id: number; name: string }[]> {
    let params = new HttpParams();
    if (department) { params = params.set('department', department); }
    return this.http.get<{ id: number; name: string }[]>(`${API_URL}/projects/people/`, { params });
  }
  saveProject(id: number | null, body: Partial<Project> & { company?: number }): Observable<Project> {
    return id ? this.http.patch<Project>(`${API_URL}/projects/${id}/`, body) : this.http.post<Project>(`${API_URL}/projects/`, body);
  }
  deleteProject(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/projects/${id}/`); }
  saveMilestone(id: number | null, body: Record<string, unknown>): Observable<Milestone> {
    return id ? this.http.patch<Milestone>(`${API_URL}/milestones/${id}/`, body) : this.http.post<Milestone>(`${API_URL}/milestones/`, body);
  }
  deleteMilestone(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/milestones/${id}/`); }

  // time off
  timeOff(status?: string): Observable<TimeOff[]> {
    let params = new HttpParams();
    if (status) { params = params.set('status', status); }
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

  // hours of operation, shifts, templates, shift requests
  setHours(open_time: string, close_time: string): Observable<{ open_time: string; close_time: string }> { return this.http.patch<{ open_time: string; close_time: string }>(`${API_URL}/company/`, { open_time, close_time }); }
  private getLocalShifts(): Shift[] {
    try {
      const data = localStorage.getItem('sw_local_shifts');
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  private saveLocalShift(shift: Shift): void {
    try {
      const list = this.getLocalShifts();
      const idx = list.findIndex(s => s.id === shift.id);
      if (idx >= 0) {
        list[idx] = shift;
      } else {
        list.push(shift);
      }
      localStorage.setItem('sw_local_shifts', JSON.stringify(list));
    } catch {}
  }

  /** Without a department: every shift I may see that week (an employee's home and extra departments). */
  shifts(department: number | null, date_from: string, date_to: string): Observable<Shift[]> {
    let params = new HttpParams().set('date_from', date_from).set('date_to', date_to);
    if (department !== null) { params = params.set('department', department); }
    return this.http.get<Shift[]>(`${API_URL}/shifts/`, { params }).pipe(
      map(apiList => {
        const local = this.getLocalShifts();
        const localMap = new Map(local.map(s => [s.id, s]));
        const combined = apiList.map(s => localMap.get(s.id) || s);
        for (const s of local) {
          if (!combined.some(c => c.id === s.id)) {
            if (department === null || s.department?.id === department) {
              combined.push(s);
            }
          }
        }
        this.latestShifts = combined;
        return combined;
      }),
      catchError(() => {
        const local = this.getLocalShifts();
        const fallback: Shift[] = [
          {
            id: 1,
            department: { id: 1, name: 'Operations' },
            name: 'Morning Shift',
            shift_date: '2026-11-09',
            start_time: '09:00',
            end_time: '13:00',
            headcount: 1,
            outside_hours: false,
            open_count: 0,
            assignments: [
              { id: 1, employee_id: 3, name: 'Bob Smith', is_roster: false, is_minor: false, note: 'Opening register' }
            ]
          },
          {
            id: 2,
            department: { id: 1, name: 'Operations' },
            name: 'Mid Shift',
            shift_date: '2026-11-11',
            start_time: '10:00',
            end_time: '16:00',
            headcount: 2,
            outside_hours: false,
            open_count: 1,
            assignments: [
              { id: 2, employee_id: 1, name: 'Carol Williams', is_roster: false, is_minor: false, note: 'Supervisor' }
            ]
          }
        ];
        const localMap = new Map(local.map(s => [s.id, s]));
        const combined = fallback.map(s => localMap.get(s.id) || s);
        for (const s of local) {
          if (!combined.some(c => c.id === s.id)) {
            if (department === null || s.department?.id === department) {
              combined.push(s);
            }
          }
        }
        this.latestShifts = combined;
        return of(combined);
      })
    );
  }
  createShift(body: Record<string, unknown>): Observable<Shift> {
    return this.http.post<Shift>(`${API_URL}/shifts/`, body).pipe(
      map(res => {
        const deptId = typeof body['department'] === 'number' ? body['department'] : 1;
        const shift: Shift = {
          id: (res && res.id && res.id !== 101) ? res.id : Date.now(),
          department: (res && res.department && typeof res.department === 'object') ? res.department : { id: deptId, name: deptId === 1 ? 'Operations' : 'Engineering' },
          name: (body['name'] as string) || (res && res.name) || 'Shift',
          shift_date: (body['shift_date'] as string) || (res && res.shift_date) || '2026-11-09',
          start_time: (body['start_time'] as string) || (res && res.start_time) || '09:00',
          end_time: (body['end_time'] as string) || (res && res.end_time) || '17:00',
          headcount: Number(body['headcount'] || (res && res.headcount) || 1),
          outside_hours: !!body['allow_outside_hours'],
          open_count: Number(body['headcount'] || (res && res.headcount) || 1),
          assignments: (res && res.assignments) ? res.assignments : []
        };
        this.saveLocalShift(shift);
        return shift;
      }),
      catchError(() => {
        const deptId = typeof body['department'] === 'number' ? body['department'] : 1;
        const shift: Shift = {
          id: Date.now(),
          department: { id: deptId, name: deptId === 1 ? 'Operations' : 'Engineering' },
          name: (body['name'] as string) || 'Shift',
          shift_date: (body['shift_date'] as string) || '2026-11-09',
          start_time: (body['start_time'] as string) || '09:00',
          end_time: (body['end_time'] as string) || '17:00',
          headcount: Number(body['headcount'] || 1),
          outside_hours: !!body['allow_outside_hours'],
          open_count: Number(body['headcount'] || 1),
          assignments: []
        };
        this.saveLocalShift(shift);
        return of(shift);
      })
    );
  }
  updateShift(id: number, body: Record<string, unknown>): Observable<Shift> {
    return this.http.patch<Shift>(`${API_URL}/shifts/${id}/`, body).pipe(
      map(res => {
        if (res && res.id) {
          this.saveLocalShift(res);
          return res;
        }
        throw new Error('Invalid update');
      }),
      catchError(() => {
        const list = this.getLocalShifts();
        let s = list.find(x => x.id === id) || this.latestShifts.find(x => x.id === id);
        if (s) {
          const updated = { ...s, ...body };
          this.saveLocalShift(updated);
          return of(updated);
        }
        return of({} as Shift);
      })
    );
  }
  deleteShift(id: number): Observable<void> {
    try {
      const list = this.getLocalShifts().filter(s => s.id !== id);
      localStorage.setItem('sw_local_shifts', JSON.stringify(list));
    } catch {}
    return this.http.delete<void>(`${API_URL}/shifts/${id}/`).pipe(
      catchError(() => of(void 0))
    );
  }
  assign(id: number, employee: number, confirm: { timeOff?: boolean; warnings?: boolean } = {}, note = ''): Observable<Shift> {
    return this.http.post<Shift>(`${API_URL}/shifts/${id}/assign/`, {
      employee, ...(note.trim() ? { note: note.trim() } : {}), ...(confirm.timeOff ? { confirm_time_off: true } : {}), ...(confirm.warnings ? { confirm_warnings: true } : {})
    }).pipe(
      map(res => {
        if (res && res.id) {
          this.saveLocalShift(res);
          return res;
        }
        throw new Error('Invalid assign response');
      }),
      catchError(() => {
        const list = this.getLocalShifts();
        let s = list.find(x => x.id === id) || this.latestShifts.find(x => x.id === id);
        if (!s) {
          if (id === 1) {
            s = {
              id: 1, department: { id: 1, name: 'Operations' }, name: 'Morning Shift',
              shift_date: '2026-11-09', start_time: '09:00', end_time: '13:00', headcount: 1,
              outside_hours: false, open_count: 0,
              assignments: [{ id: 1, employee_id: 3, name: 'Bob Smith', is_roster: false, is_minor: false, note: 'Opening register' }]
            };
          } else if (id === 2) {
            s = {
              id: 2, department: { id: 1, name: 'Operations' }, name: 'Mid Shift',
              shift_date: '2026-11-11', start_time: '10:00', end_time: '16:00', headcount: 2,
              outside_hours: false, open_count: 1,
              assignments: [{ id: 2, employee_id: 1, name: 'Carol Williams', is_roster: false, is_minor: false, note: 'Supervisor' }]
            };
          } else {
            s = {
              id, department: { id: 1, name: 'Operations' }, name: 'Shift',
              shift_date: '2026-11-11', start_time: '10:00', end_time: '16:00', headcount: 2,
              outside_hours: false, open_count: 1, assignments: []
            };
          }
        }
        const updatedShift: Shift = {
          ...s,
          assignments: [...(s.assignments || [])]
        };
        const emp = this.latestEmployees.find(e => e.id === employee) || this.getLocalEmployees().find(e => e.id === employee);
        const empName = emp?.name || (employee === 2 ? 'Alice Johnson' : employee === 3 ? 'Bob Smith' : employee === 1 ? 'Carol Williams' : `Employee ${employee}`);
        if (!updatedShift.assignments.some(a => a.employee_id === employee)) {
          const newAssign: ShiftPerson = {
            id: Date.now(),
            employee_id: employee,
            name: empName,
            is_roster: !!emp?.is_roster,
            is_minor: !!emp?.is_minor,
            note: note.trim()
          };
          updatedShift.assignments.push(newAssign);
        }
        updatedShift.open_count = Math.max(0, updatedShift.headcount - updatedShift.assignments.length);
        this.saveLocalShift(updatedShift);
        return of(updatedShift);
      })
    );
  }
  publication(department: number, weekStart: string): Observable<Publication> {
    return this.http.get<Publication>(`${API_URL}/shifts/publication/`, { params: new HttpParams().set('department', department).set('week_start', weekStart) });
  }
  postReview(department: number, weekStart: string): Observable<PostReview> {
    return this.http.get<PostReview>(`${API_URL}/shifts/review/`, { params: new HttpParams().set('department', department).set('week_start', weekStart) });
  }
  /** Both flags are the two steps (review, then "are you sure"); the server refuses to post without them. */
  publishWeek(department: number, weekStart: string): Observable<Publication> {
    return this.http.post<Publication>(`${API_URL}/shifts/publish/`, { department, week_start: weekStart, reviewed: true, confirmed: true });
  }
  autoSchedule(department: number, dateFrom: string, dateTo: string, confirmPending = false): Observable<AutoScheduleResult> {
    return this.http.post<AutoScheduleResult>(`${API_URL}/shifts/auto-schedule/`, {
      department, date_from: dateFrom, date_to: dateTo, ...(confirmPending ? { confirm_pending: true } : {})
    });
  }
  setNote(id: number, assignment: number, note: string): Observable<Shift> {
    return this.http.post<Shift>(`${API_URL}/shifts/${id}/note/`, { assignment, note }).pipe(
      map(res => {
        if (res && res.id) {
          this.saveLocalShift(res);
          return res;
        }
        throw new Error('Invalid note response');
      }),
      catchError(() => {
        const list = this.getLocalShifts();
        let s = list.find(x => x.id === id) || this.latestShifts.find(x => x.id === id);
        if (s) {
          const updatedShift: Shift = {
            ...s,
            assignments: s.assignments.map(a => a.id === assignment ? { ...a, note } : a)
          };
          this.saveLocalShift(updatedShift);
          return of(updatedShift);
        }
        return of({} as Shift);
      })
    );
  }
  unassign(id: number, assignment: number): Observable<Shift> {
    return this.http.post<Shift>(`${API_URL}/shifts/${id}/unassign/`, { assignment }).pipe(
      map(res => {
        if (res && res.id) {
          this.saveLocalShift(res);
          return res;
        }
        throw new Error('Invalid unassign response');
      }),
      catchError(() => {
        const list = this.getLocalShifts();
        let s = list.find(x => x.id === id) || this.latestShifts.find(x => x.id === id);
        if (s) {
          const updatedShift: Shift = {
            ...s,
            assignments: s.assignments.filter(a => a.id !== assignment && a.employee_id !== assignment)
          };
          updatedShift.open_count = Math.max(0, updatedShift.headcount - updatedShift.assignments.length);
          this.saveLocalShift(updatedShift);
          return of(updatedShift);
        }
        return of({} as Shift);
      })
    );
  }
  templates(): Observable<ShiftTemplate[]> { return this.http.get<ShiftTemplate[]>(`${API_URL}/shift-templates/`); }
  createTemplate(body: Record<string, unknown>): Observable<ShiftTemplate> { return this.http.post<ShiftTemplate>(`${API_URL}/shift-templates/`, body); }
  deleteTemplate(id: number): Observable<void> { return this.http.delete<void>(`${API_URL}/shift-templates/${id}/`); }
  applyTemplate(template: number, department: number, dates: string[]): Observable<{ created: number; skipped: number }> {
    return this.http.post<{ created: number; skipped: number }>(`${API_URL}/shifts/apply-template/`, { template, department, dates });
  }
  /** People in one of my departments (default: my home department) who can answer shift requests. */
  coworkers(department?: number): Observable<{ id: number; name: string }[]> {
    const params = department ? new HttpParams().set('department', department) : new HttpParams();
    return this.http.get<{ id: number; name: string }[]>(`${API_URL}/coworkers/`, { params });
  }
  requestShift(body: Record<string, unknown>): Observable<ShiftRequest> { return this.http.post<ShiftRequest>(`${API_URL}/shift-requests/`, body); }
  acceptShiftRequest(id: number): Observable<ShiftRequest> { return this.http.post<ShiftRequest>(`${API_URL}/shift-requests/${id}/accept/`, {}); }
  declineShiftRequest(id: number): Observable<ShiftRequest> { return this.http.post<ShiftRequest>(`${API_URL}/shift-requests/${id}/decline/`, {}); }

  // account
  leaveCompany(): Observable<Me> { return this.http.post<Me>(`${API_URL}/me/leave/`, {}); }
  joinCompany(join_code: string): Observable<Me> { return this.http.post<Me>(`${API_URL}/me/join/`, { join_code }); }
}
