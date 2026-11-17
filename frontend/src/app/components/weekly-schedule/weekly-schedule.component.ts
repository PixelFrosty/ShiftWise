import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { ApiService, AutoScheduleResult, Employee, PostReview, Publication, Shift, ShiftPerson, ShiftTemplate } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { DepartmentRef, errorText } from '../../core/models';
import { addDays, formatWeekRange, fromIso, mondayOf, toIso } from '../shared/week-utils';
import { EmployeeDirectoryComponent } from '../employee-directory/employee-directory.component';

const HOUR_PX = 60;
const DAY_SHORT = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
const DAY_LONG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function loadView(): 'grid' | 'list' {
  try { return localStorage.getItem('shiftwise.scheduleView') === 'list' ? 'list' : 'grid'; } catch { return 'grid'; }
}

export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

export function prettyTime(hhmm: string): string {
  const mins = toMinutes(hhmm);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  const hour = h % 12 || 12;
  return `${hour}${m ? ':' + String(m).padStart(2, '0') : ''} ${h < 12 ? 'AM' : 'PM'}`;
}

export interface DayColumn { iso: string; short: string; long: string; num: number; today: boolean; }

export interface PlacedShift { shift: Shift; top: number; height: number; left: number; width: number; }

type Panel = null | 'shift' | 'add' | 'templates' | 'hours';
type RequestMode = null | { kind: 'give' | 'take' | 'swap'; person?: ShiftPerson };

@Component({
  selector: 'app-weekly-schedule',
  standalone: true,
  imports: [RouterLink, FormsModule, EmployeeDirectoryComponent],
  templateUrl: './weekly-schedule.component.html'
})
export class WeeklyScheduleComponent implements OnDestroy {
  private auth = inject(AuthService);
  private api = inject(ApiService);
  private router = inject(Router);

  readonly dayLong = DAY_LONG;
  readonly hourPx = HOUR_PX;

  // The Monday of the viewed week. It is a signal so the day columns (computed) follow week changes.
  private weekStart = signal(mondayOf(new Date()));
  get monday(): Date { return this.weekStart(); }
  departments: DepartmentRef[] = [];
  /** Departments this person runs. Managers and General Managers can also look at the others (view only). */
  private managedIds = new Set<number>();
  deptId: number | null = null;

  /** Grid (hour-by-hour columns) or List (one card per shift under each day) - the list is easier to read when shifts overlap. */
  view = signal<'grid' | 'list'>(loadView());
  /** Is this department-week posted? Null until loaded. Drafts are only visible to managers. */
  pub = signal<Publication | null>(null);
  /** Step 1 of posting: the review of the week. Step 2 (postConfirm): the final "are you sure". */
  postReview: PostReview | null = null;
  postConfirm = false;
  postBusy = false;
  postError = '';

  /** Employees see only their own shifts until they expand to all shifts of the department. */
  showAll = signal(false);

  shifts = signal<Shift[]>([]);
  /** An employee's shifts in all their departments for the week (the hours card adds them all up). */
  weekAll = signal<Shift[]>([]);
  loading = signal(true);
  loadError = signal('');

  panel: Panel = null;
  activeShiftId: number | null = null;
  panelError = '';
  busy = false;

  // staff only
  deptPeople = signal<Employee[]>([]);
  templates = signal<ShiftTemplate[]>([]);
  toAdd: number | null = null;
  newNote = '';                       // optional note typed while adding a person
  noteEditId: number | null = null;   // the assignment whose note is being edited
  noteDraft = '';
  editing = false;
  edit = { name: '', start_time: '', end_time: '', headcount: 1 };
  newShift = { name: '', shift_date: '', start_time: '09:00', end_time: '13:00', headcount: 1 };
  newTemplate = { name: '', start_time: '09:00', end_time: '13:00', headcount: 1 };
  applyTemplateId: number | null = null;
  applyDays: boolean[] = [true, true, true, true, true, false, false];
  hoursForm = { open_time: '08:00', close_time: '18:00' };
  templateMessage = '';
  /** Shown when a shift would sit outside the hours of operation; Yes sends it again with allow_outside_hours. */
  outsidePrompt: { text: string; action: 'create' | 'edit' } | null = null;
  confirmPrompt: { kind: 'time_off' | 'warning'; text: string } | null = null;
  private confirmed = { timeOff: false, warnings: false };

  // automatic scheduler
  autoPrompt: { count: number; people: string[] } | null = null;
  autoResult: AutoScheduleResult | null = null;
  autoBusy = false;
  autoError = '';

  // employee requests
  requestMode: RequestMode = null;
  coworkers = signal<{ id: number; name: string }[]>([]);
  /** 'all' = offer the shift to everyone in the department; otherwise one coworker's id. */
  giveTo: number | 'all' | null = 'all';
  swapMine: number | null = null;
  requestDone = '';

  private sub: Subscription;

  constructor(private route: ActivatedRoute) {
    const profile = this.auth.me()?.profile;
    if (profile) {
      this.managedIds = new Set(profile.managed_departments.map(d => d.id));
      // Start on a department this person runs (their own if they run it), so the first view is one they can edit.
      // an employee can switch between their home department (first) and any extra ones they also work in
      const mine = profile.can_edit_schedule ? profile.managed_departments : [profile.department, ...(profile.extra_departments ?? [])];
      this.departments = mine.length ? mine : [profile.department];
      this.deptId = this.departments.find(d => d.id === profile.department.id)?.id ?? this.departments[0]?.id ?? null;
      if (profile.can_edit_schedule) {
        // add every other department of the company after the ones they run
        this.api.departments().subscribe(all => {
          const own = new Set(this.departments.map(d => d.id));
          this.departments = [...this.departments, ...all.filter(d => !own.has(d.id)).map(d => ({ id: d.id, name: d.name }))];
        });
      }
    }
    if (this.canEdit) { this.loadStaffData(); }
    this.sub = this.route.paramMap.subscribe(params => {
      const parsed = fromIso(params.get('start') ?? '');
      this.weekStart.set(parsed ? mondayOf(parsed) : mondayOf(new Date()));
      this.closePanel();
      this.reload();
    });
  }

  ngOnDestroy(): void { this.sub.unsubscribe(); }

  // --- basics ---
  get me() { return this.auth.me(); }
  get homeId(): number | null { return this.me?.profile?.department.id ?? null; }
  get myProfileId(): number | null { return this.me?.profile?.id ?? null; }
  /** Manager or General Manager (may look at every department). */
  get isStaff(): boolean { return !!this.me?.profile?.can_edit_schedule; }
  /** Staff may change only the departments they run; other departments are view only. */
  get canEdit(): boolean { return this.isStaff && this.deptId !== null && this.managedIds.has(this.deptId); }
  get isCeo(): boolean { return this.me?.profile?.role === 'ceo'; }
  get deptName(): string { return this.departments.find(d => d.id === this.deptId)?.name ?? ''; }
  get rangeLabel(): string { return formatWeekRange(this.monday); }

  get shortRange(): string {
    const end = addDays(this.monday, 6);
    const a = `${MONTHS[this.monday.getMonth()]} ${this.monday.getDate()}`;
    const b = this.monday.getMonth() === end.getMonth() ? `${end.getDate()}` : `${MONTHS[end.getMonth()]} ${end.getDate()}`;
    return `${a} – ${b}, ${end.getFullYear()}`;
  }

  get emptyText(): string {
    if (this.canEdit) { return 'No shifts this week yet. Use "+ Add shift" or apply a template.'; }
    if (!this.isStaff && !this.showAll() && this.shifts().length > 0) { return 'You have no shifts this week. Use "Show all shifts" to see the rest of the department.'; }
    return 'No shifts have been posted for this week yet.';
  }

  get openTime(): string { return this.me?.profile?.company.open_time ?? '08:00'; }
  get closeTime(): string { return this.me?.profile?.company.close_time ?? '18:00'; }
  get coverageText(): string { return `${prettyTime(this.openTime)} – ${prettyTime(this.closeTime)}`; }

  days = computed<DayColumn[]>(() => {
    const todayIso = toIso(new Date());
    return DAY_SHORT.map((short, i) => {
      const d = addDays(this.monday, i);
      return { iso: toIso(d), short, long: DAY_LONG[i], num: d.getDate(), today: toIso(d) === todayIso };
    });
  });

  // hour labels and the grid's pixel height follow the hours of operation
  // (widened when a manager placed a shift outside the hours of operation, so it still shows on the grid)
  get gridStartMin(): number {
    const earliest = Math.min(toMinutes(this.openTime), ...this.visibleShifts().map(s => toMinutes(s.start_time)));
    return Math.floor(earliest / 60) * 60;
  }
  get gridEndMin(): number {
    const latest = Math.max(toMinutes(this.closeTime), ...this.visibleShifts().map(s => toMinutes(s.end_time)));
    return Math.ceil(latest / 60) * 60;
  }
  get hourLabels(): string[] {
    const out: string[] = [];
    for (let m = this.gridStartMin; m < this.gridEndMin; m += 60) { out.push(prettyTime(`${Math.floor(m / 60)}:00`).replace(':00', '')); }
    return out;
  }
  get gridHeight(): number { return ((this.gridEndMin - this.gridStartMin) / 60) * HOUR_PX; }

  /** What is drawn: everything, except that an employee starts with only the shifts they are on. */
  visibleShifts = computed(() => {
    const all = this.shifts();
    return this.isStaff || this.showAll() ? all : all.filter(s => this.iAmOn(s));
  });

  /** Shifts placed in pixel positions per day; overlapping shifts sit side by side. */
  placed = computed(() => {
    const result: Record<string, PlacedShift[]> = {};
    const start = this.gridStartMin;
    for (const day of this.days()) {
      const list = this.visibleShifts().filter(s => s.shift_date === day.iso)
        .sort((a, b) => toMinutes(a.start_time) - toMinutes(b.start_time) || toMinutes(b.end_time) - toMinutes(a.end_time));
      const out: PlacedShift[] = [];
      let cluster: { shift: Shift; lane: number }[] = [];
      let clusterEnd = -1;
      const flush = () => {
        const lanes = Math.max(1, ...cluster.map(c => c.lane + 1));
        for (const c of cluster) {
          const s = toMinutes(c.shift.start_time);
          const e = toMinutes(c.shift.end_time);
          out.push({ shift: c.shift, top: ((s - start) / 60) * HOUR_PX, height: ((e - s) / 60) * HOUR_PX,
                     left: (c.lane / lanes) * 100, width: 100 / lanes });
        }
        cluster = [];
      };
      const laneEnds: number[] = [];
      for (const shift of list) {
        const s = toMinutes(shift.start_time);
        if (cluster.length && s >= clusterEnd) { flush(); laneEnds.length = 0; clusterEnd = -1; }
        let lane = laneEnds.findIndex(end => end <= s);
        if (lane === -1) { lane = laneEnds.length; laneEnds.push(0); }
        laneEnds[lane] = toMinutes(shift.end_time);
        clusterEnd = Math.max(clusterEnd, toMinutes(shift.end_time));
        cluster.push({ shift, lane });
      }
      flush();
      result[day.iso] = out;
    }
    return result;
  });

  scheduledSlots = computed(() => this.visibleShifts().reduce((n, s) => n + s.assignments.length, 0));
  openSlots = computed(() => this.visibleShifts().reduce((n, s) => n + s.open_count, 0));

  /** Hours the viewer is scheduled for in the shown week (all of their shifts, whatever is expanded). */
  myHours = computed(() => {
    const mins = (this.isStaff ? this.shifts() : this.weekAll()).filter(s => this.iAmOn(s)).reduce((n, s) => n + toMinutes(s.end_time) - toMinutes(s.start_time), 0);
    const h = Math.round((mins / 60) * 100) / 100;
    return `${h} ${h === 1 ? 'hour' : 'hours'}`;
  });

  /** List view: the shifts of each day, earliest first. */
  listDays = computed(() => this.days().map(day => ({
    day,
    shifts: this.visibleShifts().filter(s => s.shift_date === day.iso)
      .sort((a, b) => toMinutes(a.start_time) - toMinutes(b.start_time) || toMinutes(a.end_time) - toMinutes(b.end_time))
  })));

  openOnDay(iso: string): number { return this.visibleShifts().filter(s => s.shift_date === iso).reduce((n, s) => n + s.open_count, 0); }
  hasShifts(iso: string): boolean { return this.visibleShifts().some(s => s.shift_date === iso); }

  dayName(iso: string): string { return DAY_LONG[(new Date(iso + 'T00:00:00').getDay() + 6) % 7]; }

  blockClass(s: Shift): string {
    const base = 'w-full h-full text-left rounded-lg px-2.5 py-2 overflow-hidden cursor-pointer transition flex flex-col gap-0.5 ';
    return base + this.shiftLook(s);
  }

  /** Colours shared by grid blocks and list cards. The viewer's own shifts are bright green so they stand out. */
  shiftLook(s: Shift): string {
    const look = this.iAmOn(s)
      ? 'bg-emerald-200 hover:bg-emerald-300 border-l-4 border-emerald-600 ring-2 ring-emerald-600 '
      : s.assignments.length
        ? 'bg-slate-300 hover:bg-slate-400 border-l-4 border-slate-500 '
        : 'bg-white hover:bg-slate-50 border-2 border-dashed border-slate-700 ';
    return look + (this.activeShiftId === s.id ? 'outline outline-2 outline-offset-1 outline-slate-900' : '');
  }

  isMine(p: ShiftPerson): boolean { return p.employee_id === this.myProfileId; }
  iAmOn(s: Shift): boolean { return s.assignments.some(a => this.isMine(a)); }
  timeRange(s: { start_time: string; end_time: string }): string { return `${prettyTime(s.start_time)} – ${prettyTime(s.end_time)}`; }

  // --- loading ---
  goToWeek(delta: number): void { this.router.navigate(['/schedules/week', toIso(addDays(this.monday, delta * 7))]); }
  changeDepartment(): void { this.closePanel(); this.reload(); if (this.canEdit) { this.loadStaffData(); } }

  runs(id: number): boolean { return this.managedIds.has(id); }

  setView(v: 'grid' | 'list'): void {
    this.view.set(v);
    try { localStorage.setItem('shiftwise.scheduleView', v); } catch { /* storage may be blocked */ }
  }

  /** True for an employee looking at a week that has not been posted: there is nothing to show yet. */
  get notPosted(): boolean { const p = this.pub(); return !this.isStaff && !!p && !p.published; }

  postedOn(p: Publication): string {
    return p.published_at ? new Date(p.published_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';
  }

  openPost(): void {
    if (this.deptId === null || this.postBusy) { return; }
    this.postError = '';
    this.api.postReview(this.deptId, toIso(this.monday)).subscribe({
      next: r => { this.postReview = r; this.postConfirm = false; },
      error: err => { this.autoError = errorText(err); }
    });
  }

  cancelPost(): void { this.postReview = null; this.postConfirm = false; this.postError = ''; }

  confirmPost(): void {
    if (this.deptId === null || this.postBusy || !this.postReview) { return; }
    this.postBusy = true;
    this.api.publishWeek(this.deptId, toIso(this.monday)).subscribe({
      next: p => { this.pub.set(p); this.postBusy = false; this.cancelPost(); },
      error: err => { this.postBusy = false; this.postConfirm = false; this.postError = errorText(err); }
    });
  }

  reload(done?: () => void): void {
    if (this.deptId === null) { this.loading.set(false); return; }
    this.pub.set(null);
    this.api.publication(this.deptId, toIso(this.monday)).subscribe({ next: p => this.pub.set(p), error: () => this.pub.set(null) });
    const dept = this.deptId;
    // an employee loads every department they may see at once, so extra departments add into the hours card
    this.api.shifts(this.isStaff ? dept : null, toIso(this.monday), toIso(addDays(this.monday, 6))).subscribe({
      next: list => {
        this.weekAll.set(list);
        this.shifts.set(this.isStaff ? list : list.filter(s => s.department.id === dept));
        this.loading.set(false); this.loadError.set(''); done?.();
      },
      error: err => { this.loading.set(false); this.loadError.set(errorText(err)); }
    });
  }

  private loadStaffData(): void {
    this.api.employees().subscribe(list => this.deptPeople.set(list));
    this.api.templates().subscribe(list => { this.templates.set(list); this.applyTemplateId = this.applyTemplateId ?? list[0]?.id ?? null; });
  }

  /** People of this department not yet on the open shift. */
  get addable(): Employee[] {
    const shift = this.activeShift;
    if (!shift) { return []; }
    const on = (shift.assignments || []).map(a => a.employee_id);
    const shiftDeptId = typeof shift.department === 'object' ? shift.department?.id : shift.department;
    return this.deptPeople().filter(p => {
      const pDeptId = typeof p.department === 'object' ? p.department?.id : p.department;
      const worksInDept = pDeptId === shiftDeptId || (Array.isArray(p.extra_departments) && p.extra_departments.some(d => d.id === shiftDeptId));
      return worksInDept && !on.includes(p.id);
    });
  }

  // --- panel ---
  get activeShift(): Shift | null { return this.shifts().find(s => s.id === this.activeShiftId) ?? null; }

  openShift(shift: Shift): void {
    this.activeShiftId = shift.id;
    this.panel = 'shift';
    this.panelError = '';
    this.requestMode = null;
    this.requestDone = '';
    this.editing = false;
    this.toAdd = null;
    this.newNote = '';
    this.noteEditId = null;
    if (!this.deptPeople().length) {
      this.loadStaffData();
    }
  }

  closePanel(): void { this.outsidePrompt = null; this.panel = null; this.activeShiftId = null; this.panelError = ''; this.requestMode = null; this.confirmPrompt = null; this.confirmed = { timeOff: false, warnings: false }; }

  private fail(err: unknown): void { this.panelError = errorText(err); this.busy = false; }

  private applyUpdated(updated: Shift): void {
    this.shifts.update(list => list.map(s => s.id === updated.id ? updated : s));
    this.busy = false;
  }

  // --- staff: assign / remove / edit / delete ---
  addPerson(): void {
    const shift = this.activeShift;
    if (!shift || !this.toAdd || this.busy) { return; }
    this.busy = true;
    this.panelError = '';
    const employeeId = Number(this.toAdd);
    this.api.assign(shift.id, employeeId, { timeOff: this.confirmed.timeOff, warnings: this.confirmed.warnings }, this.newNote).subscribe({
      next: updated => {
        this.applyUpdated(updated);
        this.toAdd = null;
        this.newNote = '';
        this.confirmPrompt = null;
        this.confirmed = { timeOff: false, warnings: false };
        this.closePanel();
        this.reload();
      },
      error: (err: HttpErrorResponse) => {
        this.busy = false;
        if (err.status === 409 && err.error?.code === 'time_off_approved') {
          this.confirmPrompt = { kind: 'time_off', text: err.error.detail };
        } else if (err.status === 409 && err.error?.code === 'schedule_warning') {
          this.confirmPrompt = { kind: 'warning', text: err.error.detail };
        } else { this.confirmed = { timeOff: false, warnings: false }; this.fail(err); }
      }
    });
  }

  onEmployeeAdded(event: any): void {
    if (event?.shift) {
      this.applyUpdated(event.shift);
    }
    this.closePanel();
    this.reload();
  }

  /** Yes/No on a warning (approved time off, hour limits, minors). Yes asks again with that warning confirmed. */
  confirmWarning(yes: boolean): void {
    const prompt = this.confirmPrompt;
    if (!prompt) { return; }
    if (!yes) { this.confirmPrompt = null; this.toAdd = null; this.confirmed = { timeOff: false, warnings: false }; return; }
    if (prompt.kind === 'time_off') { this.confirmed.timeOff = true; } else { this.confirmed.warnings = true; }
    this.confirmPrompt = null;
    this.addPerson();
  }

  // --- automatic scheduler ---
  runAuto(confirmPending = false): void {
    if (this.deptId === null || this.autoBusy) { return; }
    this.autoBusy = true;
    this.autoError = '';
    this.autoPrompt = null;
    this.api.autoSchedule(this.deptId, toIso(this.monday), toIso(addDays(this.monday, 6)), confirmPending).subscribe({
      next: r => { this.autoBusy = false; this.autoResult = r; this.reload(); },
      error: (err: HttpErrorResponse) => {
        this.autoBusy = false;
        if (err.status === 409 && err.error?.code === 'pending_time_off') {
          this.autoPrompt = { count: err.error.count, people: err.error.people ?? [] };
        } else { this.autoError = errorText(err); }
      }
    });
  }

  nameClass(p: ShiftPerson): string {
    const base = 'inline-flex items-center max-w-full truncate rounded-md border px-1.5 py-0.5 text-xs leading-tight ';
    const look = this.isMine(p) ? 'bg-emerald-600 border-emerald-700 text-white'
      : p.is_minor ? 'bg-yellow-100 border-yellow-400 text-yellow-800' : 'bg-emerald-50 border-emerald-300 text-emerald-800';
    return base + look + (this.isMine(p) ? ' font-bold' : ' font-semibold');
  }

  startNote(p: ShiftPerson): void { this.noteEditId = p.id; this.noteDraft = p.note; this.panelError = ''; }

  saveNote(p: ShiftPerson): void {
    const shift = this.activeShift;
    if (!shift || this.busy) { return; }
    this.busy = true;
    this.api.setNote(shift.id, p.id, this.noteDraft.trim()).subscribe({
      next: u => { this.applyUpdated(u); this.noteEditId = null; this.panelError = ''; },
      error: err => this.fail(err)
    });
  }

  removePerson(p: ShiftPerson): void {
    const shift = this.activeShift;
    if (!shift || this.busy) { return; }
    this.busy = true;
    this.api.unassign(shift.id, p.id).subscribe({ next: u => this.applyUpdated(u), error: err => this.fail(err) });
  }

  startEdit(): void {
    const s = this.activeShift;
    if (!s) { return; }
    this.edit = { name: s.name, start_time: s.start_time, end_time: s.end_time, headcount: s.headcount };
    this.editing = true;
    this.panelError = '';
  }

  saveEdit(allowOutside = false): void {
    const s = this.activeShift;
    if (!s || this.busy) { return; }
    this.busy = true;
    this.api.updateShift(s.id, { ...this.edit, headcount: Number(this.edit.headcount), ...(allowOutside ? { allow_outside_hours: true } : {}) }).subscribe({
      next: u => { this.applyUpdated(u); this.editing = false; this.panelError = ''; },
      error: (err: HttpErrorResponse) => {
        if (err.status === 409 && err.error?.code === 'outside_hours') { this.busy = false; this.outsidePrompt = { text: err.error.detail, action: 'edit' }; }
        else { this.fail(err); }
      }
    });
  }

  deleteShift(): void {
    const s = this.activeShift;
    if (!s || this.busy) { return; }
    this.busy = true;
    const shiftId = s.id;
    this.api.deleteShift(shiftId).subscribe({
      next: () => {
        this.shifts.update(list => list.filter(item => item.id !== shiftId));
        this.weekAll.update(list => list.filter(item => item.id !== shiftId));
        this.busy = false;
        this.closePanel();
        this.reload();
      },
      error: err => this.fail(err)
    });
  }

  // --- staff: add shift, templates, hours ---
  openAdd(iso?: string): void {
    this.panel = 'add';
    this.panelError = '';
    this.newShift = { ...this.newShift, shift_date: iso ?? toIso(this.monday), name: '' };
  }

  createShift(allowOutside = false): void {
    if (this.deptId === null || this.busy) { return; }
    this.busy = true;
    this.api.createShift({ ...this.newShift, headcount: Number(this.newShift.headcount), department: this.deptId, ...(allowOutside ? { allow_outside_hours: true } : {}) }).subscribe({
      next: () => { this.busy = false; this.closePanel(); this.reload(); },
      error: (err: HttpErrorResponse) => {
        if (err.status === 409 && err.error?.code === 'outside_hours') { this.busy = false; this.outsidePrompt = { text: err.error.detail, action: 'create' }; }
        else { this.fail(err); }
      }
    });
  }

  /** Yes/No on "this shift is outside the hours of operation". Yes saves it anyway. */
  confirmOutside(yes: boolean): void {
    const prompt = this.outsidePrompt;
    if (!prompt) { return; }
    this.outsidePrompt = null;
    if (!yes) { return; }
    if (prompt.action === 'create') { this.createShift(true); } else { this.saveEdit(true); }
  }

  openTemplates(): void { this.panel = 'templates'; this.panelError = ''; this.templateMessage = ''; this.loadStaffData(); }

  saveTemplate(): void {
    if (this.busy) { return; }
    this.busy = true;
    this.panelError = '';
    this.api.createTemplate({ ...this.newTemplate, headcount: Number(this.newTemplate.headcount) }).subscribe({
      next: t => { this.busy = false; this.newTemplate = { ...this.newTemplate, name: '' }; this.applyTemplateId = this.applyTemplateId ?? t.id; this.loadStaffData(); },
      error: err => this.fail(err)
    });
  }

  removeTemplate(t: ShiftTemplate): void {
    this.api.deleteTemplate(t.id).subscribe({
      next: () => { if (this.applyTemplateId === t.id) { this.applyTemplateId = null; } this.loadStaffData(); },
      error: err => this.fail(err)
    });
  }

  applyTemplate(): void {
    if (this.busy || this.deptId === null || !this.applyTemplateId) { this.panelError = 'Choose a template first.'; return; }
    const dates = this.days().filter((_, i) => this.applyDays[i]).map(d => d.iso);
    if (!dates.length) { this.panelError = 'Choose at least one day.'; return; }
    this.busy = true;
    this.panelError = '';
    this.api.applyTemplate(Number(this.applyTemplateId), this.deptId, dates).subscribe({
      next: r => {
        this.busy = false;
        this.templateMessage = `Added ${r.created} shift${r.created === 1 ? '' : 's'}` + (r.skipped ? ` (${r.skipped} already existed).` : '.');
        this.reload();
      },
      error: err => this.fail(err)
    });
  }

  openHours(): void { this.panel = 'hours'; this.panelError = ''; this.hoursForm = { open_time: this.openTime, close_time: this.closeTime }; }

  saveHours(): void {
    if (this.busy) { return; }
    this.busy = true;
    this.api.setHours(this.hoursForm.open_time, this.hoursForm.close_time).subscribe({
      next: () => { this.auth.loadMe().subscribe(() => { this.busy = false; this.closePanel(); this.reload(); }); },
      error: err => this.fail(err)
    });
  }

  // --- employees: give away / take / swap ---
  startRequest(kind: 'give' | 'take' | 'swap', person?: ShiftPerson): void {
    this.requestMode = { kind, person };
    this.panelError = '';
    this.requestDone = '';
    this.giveTo = 'all';
    const shift = this.activeShift;
    if (kind === 'give' && shift) {   // coworkers of the shift's own department
      this.coworkers.set([]);
      this.api.coworkers(shift.department.id).subscribe(list => this.coworkers.set(list));
    }
    this.swapMine = this.mySwappable[0]?.id ?? null;
  }

  /** My own upcoming assignments (other than on the shift being looked at) that I could offer in a swap. */
  get mySwappable(): { id: number; label: string }[] {
    const today = toIso(new Date());
    const out: { id: number; label: string }[] = [];
    for (const s of this.shifts()) {
      if (s.shift_date < today) { continue; }
      for (const a of s.assignments) {
        if (this.isMine(a)) { out.push({ id: a.id, label: `${DAY_LONG[(new Date(s.shift_date + 'T00:00:00').getDay() + 6) % 7]} ${s.shift_date.slice(5)} · ${this.timeRange(s)}` }); }
      }
    }
    return out;
  }

  isPast(s: Shift): boolean { return s.shift_date < toIso(new Date()); }

  sendRequest(): void {
    const shift = this.activeShift;
    const mode = this.requestMode;
    if (!shift || !mode || this.busy) { return; }
    const mine = shift.assignments.find(a => this.isMine(a));
    let body: Record<string, unknown>;
    if (mode.kind === 'give') {
      if (!mine || !this.giveTo) { this.panelError = 'Choose who to ask.'; return; }
      body = this.giveTo === 'all'
        ? { kind: 'offer', schedule: mine.id }
        : { kind: 'give', schedule: mine.id, to_employee: Number(this.giveTo) };
    } else if (mode.kind === 'take') {
      if (!mode.person) { return; }
      body = { kind: 'take', schedule: mode.person.id };
    } else {
      if (!mode.person || !this.swapMine) { this.panelError = 'Choose which of your shifts to swap.'; return; }
      body = { kind: 'swap', schedule: Number(this.swapMine), other_schedule: mode.person.id };
    }
    this.busy = true;
    this.panelError = '';
    this.api.requestShift(body).subscribe({
      next: r => {
        this.busy = false;
        this.requestMode = null;
        this.requestDone = r.kind === 'offer'
          ? 'Your shift was offered to everyone in your department. The first person to accept gets it, and you will be notified.'
          : `Request sent to ${r.target?.name}. You'll get a notification when they answer.`;
      },
      error: err => this.fail(err)
    });
  }
}
