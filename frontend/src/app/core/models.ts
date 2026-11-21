export type Role = 'ceo' | 'manager' | 'employee';

export interface DepartmentRef { id: number; name: string; }

export interface MyProfile {
  id: number;
  role: Role;
  company: { id: number; name: string; open_time: string; close_time: string };
  department: DepartmentRef;
  /** Other departments this person also works in (a manager schedules them there by hand). */
  extra_departments: DepartmentRef[];
  /** Departments this person can edit (General Manager: all, manager: assigned ones, employee: none). */
  managed_departments: DepartmentRef[];
  can_edit_schedule: boolean;
}

export interface Me {
  id: number;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  profile: MyProfile | null;
  unread_notifications: number;
}

export function roleLabel(role: Role | undefined): string {
  return role === 'ceo' ? 'General Manager' : role === 'manager' ? 'Manager' : role === 'employee' ? 'Employee' : '';
}

/** Turns a DRF error body ({field: [msgs]} or {detail}) into one readable line. */
export function errorText(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const body = (err as { error?: unknown })?.error;
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    if (typeof obj['detail'] === 'string') { return obj['detail']; }
    const parts: string[] = [];
    for (const value of Object.values(obj)) {
      if (Array.isArray(value)) { parts.push(...value.map(String)); }
      else if (typeof value === 'string') { parts.push(value); }
    }
    if (parts.length) { return parts.join(' '); }
  }
  return fallback;
}
