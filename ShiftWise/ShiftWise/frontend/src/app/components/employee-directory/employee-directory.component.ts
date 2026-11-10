import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, CompatibilityGroup, Department, Employee } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-employee-directory',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './employee-directory.component.html',
  styleUrl: './employee-directory.component.scss'
})
export class EmployeeDirectoryComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  employees = signal<Employee[]>([]);
  departments = signal<Department[]>([]);
  loaded = signal(false);
  message = signal<{ kind: 'ok' | 'error'; text: string } | null>(null);

  searchQuery = '';
  selectedDeptId = '';

  isCeo = computed(() => this.auth.role === 'ceo');
  myProfileId = computed(() => this.auth.me()?.profile?.id ?? null);

  /** Departments the signed-in person can add roster employees to / make changes in. */
  editableDepartments = computed(() => {
    const ids = this.auth.me()?.profile?.managed_departments.map(d => d.id) ?? [];
    return this.departments().filter(d => ids.includes(d.id));
  });

  managerDepartments = computed(() => this.departments());

  // Remove modal
  employeeToDelete: Employee | null = null;
  isDeleting = false;

  // Edit modal
  editing: { id: number; name: string; roster: boolean; first_name: string; last_name: string; position: string;
             productivity_score: number | null; pay_rate: number | null; role: string; managed: number[];
             homeId: number; extra: number[];
             employment_type: 'full_time' | 'part_time'; allow_overtime: boolean; date_of_birth: string; age: number | null } | null = null;
  isSavingEdit = false;
  editError = '';

  // Add modal
  isAddModalOpen = false;
  isAdding = false;
  addError = '';
  newEmployee = this.blankNew();

  // Transfer modal
  transferring: Employee | null = null;
  transferTo: number | null = null;
  transferError = '';
  isTransferring = false;

  // Compatibility scores
  groups = signal<CompatibilityGroup[]>([]);
  selected = signal<number[]>([]);
  readonly scoreOptions = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  rating: { ids: number[]; names: string[]; score: number | null; existingId: number | null } | null = null;
  ratingError = '';
  isRating = false;
  groupToDelete: CompatibilityGroup | null = null;

  constructor() { this.reload(); }

  reload(): void {
    this.api.departments().subscribe(list => this.departments.set(list));
    this.reloadGroups();
    this.api.employees().subscribe({
      next: list => { this.employees.set(list); this.loaded.set(true); },
      error: err => { this.loaded.set(true); this.message.set({ kind: 'error', text: errorText(err) }); }
    });
  }

  reloadGroups(): void { this.api.compatibilityGroups().subscribe(list => this.groups.set(list)); }

  isSelected(id: number): boolean { return this.selected().includes(id); }

  toggleSelected(id: number): void {
    this.selected.update(list => list.includes(id) ? list.filter(x => x !== id) : [...list, id]);
  }

  get allShownSelected(): boolean { return this.shown.length > 0 && this.shown.every(e => this.isSelected(e.id)); }

  toggleAllShown(): void {
    const ids = this.shown.map(e => e.id);
    this.selected.update(list => this.allShownSelected ? list.filter(x => !ids.includes(x)) : [...new Set([...list, ...ids])]);
  }

  clearSelection(): void { this.selected.set([]); }

  /** Find the rating that already covers exactly this set of people. */
  private groupFor(ids: number[]): CompatibilityGroup | undefined {
    return this.groups().find(g => g.employees.length === ids.length && g.employees.every(e => ids.includes(e.id)));
  }

  openRating(): void {
    const ids = this.selected().filter(id => this.employees().some(e => e.id === id));
    if (ids.length < 2) { return; }
    const existing = this.groupFor(ids);
    this.rating = { ids, names: ids.map(id => this.employees().find(e => e.id === id)!.name),
                    score: existing?.score ?? null, existingId: existing?.id ?? null };
    this.ratingError = '';
  }

  editGroup(g: CompatibilityGroup): void {
    this.rating = { ids: g.employees.map(e => e.id), names: g.employees.map(e => e.name), score: g.score, existingId: g.id };
    this.ratingError = '';
  }

  saveRating(): void {
    const r = this.rating;
    if (!r || r.score === null || this.isRating) { this.ratingError = r && r.score === null ? 'Choose a score from 1 to 10.' : ''; return; }
    this.isRating = true;
    this.api.rateGroup(r.ids, r.score).subscribe({
      next: () => {
        this.isRating = false; this.rating = null; this.selected.set([]); this.reloadGroups();
        this.message.set({ kind: 'ok', text: 'Compatibility score saved.' });
      },
      error: err => { this.isRating = false; this.ratingError = errorText(err); }
    });
  }

  confirmDeleteGroup(): void {
    const g = this.groupToDelete;
    if (!g) { return; }
    this.api.deleteGroup(g.id).subscribe({
      next: () => { this.groupToDelete = null; this.reloadGroups(); },
      error: err => { this.groupToDelete = null; this.message.set({ kind: 'error', text: errorText(err) }); }
    });
  }

  groupNames(g: CompatibilityGroup): string { return g.employees.map(e => e.name).join(', '); }

  scoreBadge(score: number): string {
    if (score >= 8) { return 'bg-emerald-100 text-emerald-800'; }
    if (score >= 5) { return 'bg-amber-100 text-amber-800'; }
    return 'bg-rose-100 text-rose-800';
  }

  private blankNew() {
    return { first_name: '', last_name: '', position: '', department: null as number | null,
             employment_type: 'full_time' as 'full_time' | 'part_time', allow_overtime: false, date_of_birth: '',
             productivity_score: null as number | null, pay_rate: null as number | null };
  }

  private filter(all: Employee[]): Employee[] {
    let result = all;
    const query = this.searchQuery.trim().toLowerCase();
    if (query) {
      result = result.filter(e => e.name.toLowerCase().includes(query) || e.position.toLowerCase().includes(query));
    }
    if (this.selectedDeptId) {
      const id = Number(this.selectedDeptId);
      result = result.filter(e => e.department.id === id);
    }
    return result;
  }

  get shown(): Employee[] { return this.filter(this.employees()); }

  get hasActiveFilters(): boolean { return this.searchQuery.trim() !== '' || this.selectedDeptId !== ''; }

  clearFilters(): void { this.searchQuery = ''; this.selectedDeptId = ''; }

  deptName(id: number): string { return this.departments().find(d => d.id === id)?.name ?? ''; }

  extraNames(emp: Employee): string { return emp.extra_departments.map(d => d.name).join(', '); }

  managedNames(emp: Employee): string {
    return emp.managed_department_ids.map(id => this.deptName(id)).filter(Boolean).join(', ');
  }

  /** Can the signed-in person transfer / edit / remove this row? */
  canManage(emp: Employee): boolean {
    if (emp.role === 'ceo' || emp.id === this.myProfileId()) { return false; }
    if (this.isCeo()) { return true; }
    return emp.role === 'employee' && this.editableDepartments().some(d => d.id === emp.department.id);
  }

  getProductivityBarWidth(score: number | null): string { return score === null ? '0%' : Math.min(score * 10, 100) + '%'; }

  getProductivityBarColor(score: number | null): string {
    if (score === null) { return 'bg-slate-300'; }
    return score >= 8 ? 'bg-emerald-600' : score >= 5 ? 'bg-amber-500' : 'bg-rose-500';
  }

  getRoleBadgeClasses(role: string): string {
    return role === 'ceo' ? 'bg-purple-100 text-purple-800' : role === 'manager' ? 'bg-blue-100 text-blue-800' : 'bg-emerald-100 text-emerald-800';
  }

  getRoleLabel(role: string): string { return role === 'ceo' ? 'General Manager' : role === 'manager' ? 'Manager' : 'Employee'; }

  hoursLabel(emp: Employee): string { return emp.employment_type === 'part_time' ? 'Part time' : 'Full time'; }

  formatPayRate(rate: number | null): string { return rate === null ? '—' : '$' + rate.toFixed(2) + '/hr'; }

  // --- remove ---
  openDeleteModal(emp: Employee): void { this.employeeToDelete = emp; }
  closeDeleteModal(): void { if (!this.isDeleting) { this.employeeToDelete = null; } }

  confirmDelete(): void {
    const emp = this.employeeToDelete;
    if (!emp) { return; }
    this.isDeleting = true;
    this.api.removeEmployee(emp.id).subscribe({
      next: () => {
        this.isDeleting = false;
        this.employeeToDelete = null;
        this.message.set({ kind: 'ok', text: `${emp.name} was removed from the company.` });
        this.reload();
      },
      error: err => {
        this.isDeleting = false;
        this.employeeToDelete = null;
        this.message.set({ kind: 'error', text: errorText(err) });
      }
    });
  }

  // --- edit ---
  openEditModal(emp: Employee): void {
    this.editError = '';
    this.editing = { id: emp.id, name: emp.name, roster: emp.is_roster, first_name: emp.first_name, last_name: emp.last_name,
                     position: emp.position, productivity_score: emp.productivity_score, pay_rate: emp.pay_rate,
                     role: emp.role, managed: [...emp.managed_department_ids],
                     homeId: emp.department.id, extra: emp.extra_departments.map(d => d.id),
                     employment_type: emp.employment_type, allow_overtime: emp.allow_overtime,
                     date_of_birth: emp.date_of_birth ?? '', age: emp.age };
  }

  closeEditModal(): void { if (!this.isSavingEdit) { this.editing = null; } }

  toggleManaged(id: number): void {
    if (!this.editing) { return; }
    this.editing.managed = this.editing.managed.includes(id) ? this.editing.managed.filter(x => x !== id) : [...this.editing.managed, id];
  }

  toggleExtra(id: number): void {
    if (!this.editing) { return; }
    this.editing.extra = this.editing.extra.includes(id) ? this.editing.extra.filter(x => x !== id) : [...this.editing.extra, id];
  }

  /** Departments an employee could also work in: every one except their home department. */
  extraChoices(homeId: number): Department[] { return this.departments().filter(d => d.id !== homeId); }

  saveEdit(): void {
    const e = this.editing;
    if (!e) { return; }
    const body: Record<string, unknown> = {
      position: e.position,
      productivity_score: e.productivity_score === null || (e.productivity_score as unknown) === '' ? null : Number(e.productivity_score),
      pay_rate: e.pay_rate === null || (e.pay_rate as unknown) === '' ? null : Number(e.pay_rate)
    };
    body['employment_type'] = e.employment_type;
    body['allow_overtime'] = e.employment_type === 'full_time' && e.allow_overtime;
    if (e.roster) {
      body['first_name'] = e.first_name; body['last_name'] = e.last_name;
      if (e.date_of_birth) { body['date_of_birth'] = e.date_of_birth; }
    }
    if (e.role === 'manager' && this.isCeo()) { body['managed_department_ids'] = e.managed; }
    if (e.role === 'employee') { body['extra_department_ids'] = e.extra; }
    this.isSavingEdit = true;
    this.editError = '';
    this.api.updateEmployee(e.id, body).subscribe({
      next: () => { this.isSavingEdit = false; this.editing = null; this.message.set({ kind: 'ok', text: 'Saved.' }); this.reload(); },
      error: err => { this.isSavingEdit = false; this.editError = errorText(err); }
    });
  }

  // --- add (roster-only person, no login) ---
  openAddModal(): void {
    this.newEmployee = this.blankNew();
    this.newEmployee.department = this.editableDepartments()[0]?.id ?? null;
    this.addError = '';
    this.isAddModalOpen = true;
  }

  closeAddModal(): void { if (!this.isAdding) { this.isAddModalOpen = false; } }

  saveNewEmployee(): void {
    const n = this.newEmployee;
    if (!n.first_name.trim() || !n.last_name.trim() || !n.department) { this.addError = 'Enter a first name, last name and department.'; return; }
    this.isAdding = true;
    this.addError = '';
    this.api.addRosterEmployee({
      first_name: n.first_name.trim(), last_name: n.last_name.trim(), position: n.position.trim(), department: Number(n.department),
      ...(n.productivity_score !== null && (n.productivity_score as unknown) !== '' ? { productivity_score: Number(n.productivity_score) } : {}),
      ...(n.pay_rate !== null && (n.pay_rate as unknown) !== '' ? { pay_rate: Number(n.pay_rate) } : {}),
      employment_type: n.employment_type, allow_overtime: n.employment_type === 'full_time' && n.allow_overtime,
      ...(n.date_of_birth ? { date_of_birth: n.date_of_birth } : {})
    }).subscribe({
      next: () => { this.isAdding = false; this.isAddModalOpen = false; this.reload(); },
      error: err => { this.isAdding = false; this.addError = errorText(err); }
    });
  }

  // --- transfer ---
  openTransfer(emp: Employee): void {
    this.transferring = emp;
    this.transferTo = this.departments().find(d => d.id !== emp.department.id)?.id ?? null;
    this.transferError = '';
  }

  closeTransfer(): void { if (!this.isTransferring) { this.transferring = null; } }

  confirmTransfer(): void {
    const emp = this.transferring;
    if (!emp || !this.transferTo) { return; }
    this.isTransferring = true;
    this.transferError = '';
    this.api.transfer(emp.id, Number(this.transferTo)).subscribe({
      next: result => {
        this.isTransferring = false;
        this.transferring = null;
        this.message.set({
          kind: 'ok',
          text: result.outcome === 'done'
            ? `${emp.name} was moved to ${result.employee.department.name}.`
            : `Request sent. ${emp.name} moves once the destination's manager accepts.`
        });
        this.reload();
      },
      error: err => { this.isTransferring = false; this.transferError = errorText(err); }
    });
  }
}
