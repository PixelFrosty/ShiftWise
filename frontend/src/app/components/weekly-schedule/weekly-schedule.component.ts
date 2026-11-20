import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { ApiService, AssignShiftDetail, AssignShiftsPayload, AssignShiftsResult, AutoScheduleResult, Employee, GenerateShiftsPayload, GenerateShiftsResult, PostReview, Publication, Shift, ShiftPerson, ShiftTemplate, TaskItem, TimeOff } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { DepartmentRef, errorText } from '../../core/models';
import { addDays, formatWeekRange, fromIso, mondayOf, toIso } from '../shared/week-utils';
import { EmployeeDirectoryComponent } from '../employee-directory/employee-directory.component';

const HOUR_PX = 60;
const DAY_SHORT = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
const DAY_LONG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function loadView(): 'grid' | 'list' | 'stats' {
  try {
    const val = localStorage.getItem('shiftwise.scheduleView');
    return val === 'list' || val === 'stats' ? val : 'grid';
  } catch { return 'grid'; }
}

export function toMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
}

export function shiftDurationMinutes(start: string, end: string): number {
  const s = toMinutes(start);
  const e = toMinutes(end);
  return e >= s ? e - s : (e + 24 * 60) - s;
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

export interface EmployeeHoursStat {
  id: number;
  name: string;
  isMinor: boolean;
  totalMinutes: number;
  totalHours: number;
  shiftCount: number;
  shifts: { date: string; start_time: string; end_time: string; name: string }[];
  hasTimeOffConflict: boolean;
  isCurrentEmployee: boolean;
}

export interface DayDensityStat {
  iso: string;
  short: string;
  long: string;
  num: number;
  today: boolean;
  totalHours: number;
  assignedHours: number;
  openHours: number;
  shiftCount: number;
  slotCount: number;
  assignedSlotCount: number;
  openSlotCount: number;
}

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

  /** Grid (hour-by-hour columns), List (one card per shift), or Stats (hours histograms & density charts). */
  view = signal<'grid' | 'list' | 'stats'>(loadView());
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
  tasks = signal<TaskItem[]>([]);
  templates = signal<ShiftTemplate[]>([]);
  toAdd: number | null = null;
  toAddList: number[] = [];
  newNote = '';                       // optional note typed while adding a person
  noteEditId: number | null = null;   // the assignment whose note is being edited
  noteDraft = '';
  editing = false;
  edit = { name: '', start_time: '', end_time: '', headcount: 1 };
  newShiftTaskId: number | null = null;
  newShiftEmployees: number[] = [];
  newShift = { name: '', shift_date: '', start_time: '09:00', end_time: '13:00', headcount: 1 };
  newTemplate = { name: '', start_time: '09:00', end_time: '13:00', headcount: 1 };
  applyTemplateId: number | null = null;
  applyDays: boolean[] = [true, true, true, true, true, false, false];
  hoursForm = { open_time: '08:00', close_time: '18:00' };
  templateMessage = '';
  shiftGenPrompt = false;
  shiftGenBusy = false;
  shiftGenError = '';
  shiftGenResult: GenerateShiftsResult | null = null;
  shiftGenClearExisting = false;

  // smart shift assignment
  shiftAssignPrompt = false;
  shiftAssignBusy = false;
  shiftAssignError = '';
  shiftAssignResult: AssignShiftsResult | null = null;

  // clear assignments
  clearPrompt = false;
  clearBusy = false;
  clearError = '';
  clearSuccess = '';

  // clear shifts (delete all entries for the week)
  clearShiftsPrompt = false;
  clearShiftsBusy = false;
  clearShiftsError = '';

  // time-off requests for the viewed week
  weekTimeOff = signal<TimeOff[]>([]);
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
    } else {
      this.auth.loadMe().subscribe({
        next: me => {
          const p = me?.profile;
          if (p) {
            this.managedIds = new Set(p.managed_departments.map(d => d.id));
            const mine = p.can_edit_schedule ? p.managed_departments : [p.department, ...(p.extra_departments ?? [])];
            this.departments = mine.length ? mine : [p.department];
            this.deptId = this.departments.find(d => d.id === p.department.id)?.id ?? this.departments[0]?.id ?? null;
            if (p.can_edit_schedule) {
              this.api.departments().subscribe(all => {
                const own = new Set(this.departments.map(d => d.id));
                this.departments = [...this.departments, ...all.filter(d => !own.has(d.id)).map(d => ({ id: d.id, name: d.name }))];
              });
            }
            if (this.canEdit) { this.loadStaffData(); }
            this.reload();
          }
        },
        error: () => {
          this.api.departments().subscribe(all => {
            if (all.length > 0) {
              this.departments = all.map(d => ({ id: d.id, name: d.name }));
              if (this.deptId === null) { this.deptId = all[0].id; }
              this.managedIds.add(all[0].id);
              this.loadStaffData();
              this.reload();
            }
          });
        }
      });
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
  /** Staff may change only the departments they run; other departments are view only. When all departments is chosen, staff can edit. */
  get canEdit(): boolean { return this.isStaff && (this.deptId === null || this.managedIds.has(this.deptId)); }
  get isCeo(): boolean { return this.me?.profile?.role === 'ceo'; }
  get deptName(): string { return this.deptId === null ? 'All' : (this.departments.find(d => d.id === this.deptId)?.name ?? ''); }
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

  scheduledSlots = computed(() => this.visibleShifts().reduce((n, s) => n + (s.assignments?.length || 0), 0));
  openSlots = computed(() => this.visibleShifts().reduce((n, s) => n + Math.max(0, (s.headcount ?? 1) - (s.assignments?.length ?? 0)), 0));

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

  openOnDay(iso: string): number {
    return this.visibleShifts().filter(s => s.shift_date === iso).reduce((n, s) => n + Math.max(0, (s.headcount ?? 1) - (s.assignments?.length ?? 0)), 0);
  }
  hasShifts(iso: string): boolean { return this.visibleShifts().some(s => s.shift_date === iso); }

  dayName(iso: string): string { return DAY_LONG[(new Date(iso + 'T00:00:00').getDay() + 6) % 7]; }

  blockClass(s: Shift): string {
    const base = 'w-full h-full text-left rounded-lg px-2.5 py-2 overflow-hidden cursor-pointer transition flex flex-col gap-0.5 ';
    return base + this.shiftLook(s);
  }

  /** Colours shared by grid blocks and list cards. The viewer's own shifts are bright blue so they stand out. */
  shiftLook(s: Shift): string {
    const look = this.iAmOn(s)
      ? 'bg-brand-200 hover:bg-brand-300 border-l-4 border-brand-600 ring-2 ring-brand-600 '
      : s.assignments.length
        ? 'bg-slate-300 hover:bg-slate-400 border-l-4 border-slate-500 '
        : 'bg-white hover:bg-slate-50 border-2 border-dashed border-slate-700 ';
    return look + (this.activeShiftId === s.id ? 'outline outline-2 outline-offset-1 outline-slate-900' : '');
  }

  isMine(p: ShiftPerson): boolean { return p.employee_id === this.myProfileId; }
  iAmOn(s: Shift): boolean { return s.assignments.some(a => this.isMine(a)); }
  timeRange(s: { start_time: string; end_time: string }): string { return `${prettyTime(s.start_time)} – ${prettyTime(s.end_time)}`; }

  // --- Stats View Signals & Helpers ---
  readonly Math = Math;
  statsFilter = signal<'all' | 'scheduled' | 'unassigned'>('all');
  statsSearch = signal<string>('');
  expandedEmpId = signal<number | null>(null);

  toggleExpandEmp(empId: number): void {
    this.expandedEmpId.set(this.expandedEmpId() === empId ? null : empId);
  }

  getEmpInitials(name: string): string {
    if (!name) return '?';
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }

  dayDensityStats = computed<DayDensityStat[]>(() => {
    const allShifts = this.shifts();
    return this.days().map(day => {
      const dayShifts = allShifts.filter(s => s.shift_date === day.iso);
      let totalMinutes = 0;
      let assignedMinutes = 0;
      let openMinutes = 0;
      let slotCount = 0;
      let assignedSlotCount = 0;
      let openSlotCount = 0;

      for (const s of dayShifts) {
        const duration = Math.max(0, shiftDurationMinutes(s.start_time, s.end_time));
        const headcount = Math.max(1, s.headcount ?? 1);
        const assigned = (s.assignments || []).length;
        const open = Math.max(0, headcount - assigned);

        totalMinutes += duration * headcount;
        assignedMinutes += duration * assigned;
        openMinutes += duration * open;

        slotCount += headcount;
        assignedSlotCount += assigned;
        openSlotCount += open;
      }

      return {
        iso: day.iso,
        short: day.short,
        long: day.long,
        num: day.num,
        today: day.today,
        totalHours: Math.round((totalMinutes / 60) * 10) / 10,
        assignedHours: Math.round((assignedMinutes / 60) * 10) / 10,
        openHours: Math.round((openMinutes / 60) * 10) / 10,
        shiftCount: dayShifts.length,
        slotCount,
        assignedSlotCount,
        openSlotCount,
      };
    });
  });

  maxDailyDensityHours = computed(() => {
    const list = this.dayDensityStats();
    const max = Math.max(0, ...list.map(d => d.totalHours));
    return max > 0 ? max : 8;
  });

  dailyDensityTicks = computed(() => {
    const max = this.maxDailyDensityHours();
    return [
      { label: `${Math.round(max)}h`, percent: 100 },
      { label: `${Math.round(max * 0.75)}h`, percent: 75 },
      { label: `${Math.round(max * 0.5)}h`, percent: 50 },
      { label: `${Math.round(max * 0.25)}h`, percent: 25 },
      { label: '0h', percent: 0 },
    ];
  });

  totalWeekDensityHours = computed(() => {
    const list = this.dayDensityStats();
    const sum = list.reduce((acc, d) => acc + d.totalHours, 0);
    return Math.round(sum * 10) / 10;
  });

  totalWeekAssignedHours = computed(() => {
    const list = this.dayDensityStats();
    const sum = list.reduce((acc, d) => acc + d.assignedHours, 0);
    return Math.round(sum * 10) / 10;
  });

  totalWeekOpenHours = computed(() => {
    const list = this.dayDensityStats();
    const sum = list.reduce((acc, d) => acc + d.openHours, 0);
    return Math.round(sum * 10) / 10;
  });

  busiestDay = computed(() => {
    const list = this.dayDensityStats();
    if (!list.length) return null;
    let best = list[0];
    for (const d of list) {
      if (d.totalHours > best.totalHours) {
        best = d;
      }
    }
    return best.totalHours > 0 ? best : null;
  });

  employeeHoursStats = computed<EmployeeHoursStat[]>(() => {
    const allShifts = this.shifts();
    const peopleMap = new Map<number, EmployeeHoursStat>();

    // Seed from deptPeople
    for (const p of this.deptPeople()) {
      peopleMap.set(p.id, {
        id: p.id,
        name: p.name || `${p.first_name || ''} ${p.last_name || ''}`.trim() || `Employee #${p.id}`,
        isMinor: !!p.is_minor,
        totalMinutes: 0,
        totalHours: 0,
        shiftCount: 0,
        shifts: [],
        hasTimeOffConflict: false,
        isCurrentEmployee: p.id === this.myProfileId,
      });
    }

    // Accumulate from shifts
    for (const s of allShifts) {
      const duration = Math.max(0, shiftDurationMinutes(s.start_time, s.end_time));
      for (const a of s.assignments || []) {
        let stat = peopleMap.get(a.employee_id);
        if (!stat) {
          stat = {
            id: a.employee_id,
            name: a.name || `Employee #${a.employee_id}`,
            isMinor: !!a.is_minor,
            totalMinutes: 0,
            totalHours: 0,
            shiftCount: 0,
            shifts: [],
            hasTimeOffConflict: false,
            isCurrentEmployee: a.employee_id === this.myProfileId,
          };
          peopleMap.set(a.employee_id, stat);
        }
        stat.totalMinutes += duration;
        stat.shiftCount += 1;
        stat.shifts.push({
          date: s.shift_date,
          start_time: s.start_time,
          end_time: s.end_time,
          name: s.name || 'Shift',
        });
        if (this.hasTimeOff(a.employee_id, s.shift_date)) {
          stat.hasTimeOffConflict = true;
        }
      }
    }

    const list = Array.from(peopleMap.values()).map(stat => ({
      ...stat,
      totalHours: Math.round((stat.totalMinutes / 60) * 10) / 10,
    }));

    return list.sort((a, b) => b.totalHours - a.totalHours || a.name.localeCompare(b.name));
  });

  filteredEmployeeStats = computed(() => {
    const filter = this.statsFilter();
    const query = this.statsSearch().trim().toLowerCase();
    let list = this.employeeHoursStats();

    if (filter === 'scheduled') {
      list = list.filter(e => e.totalHours > 0);
    } else if (filter === 'unassigned') {
      list = list.filter(e => e.totalHours === 0);
    }

    if (query) {
      list = list.filter(e => e.name.toLowerCase().includes(query));
    }

    return list;
  });

  maxEmployeeHours = computed(() => {
    const list = this.employeeHoursStats();
    const max = Math.max(0, ...list.map(e => e.totalHours));
    return Math.max(40, Math.ceil(max / 10) * 10);
  });

  employeeHistogramTicks = computed(() => {
    const max = this.maxEmployeeHours();
    const step = max <= 50 ? 10 : 20;
    const ticks: { hour: number; percent: number }[] = [];
    for (let h = 0; h <= max; h += step) {
      ticks.push({ hour: h, percent: (h / max) * 100 });
    }
    return ticks;
  });

  scheduledEmployeeCount = computed(() => {
    return this.employeeHoursStats().filter(e => e.totalHours > 0).length;
  });

  totalEmployeeCount = computed(() => {
    return this.employeeHoursStats().length;
  });

  averageEmployeeHours = computed(() => {
    const active = this.employeeHoursStats().filter(e => e.totalHours > 0);
    if (!active.length) return 0;
    const sum = active.reduce((acc, e) => acc + e.totalHours, 0);
    return Math.round((sum / active.length) * 10) / 10;
  });

  overtimeEmployeeCount = computed(() => {
    return this.employeeHoursStats().filter(e => e.totalHours > 40).length;
  });

  // --- loading ---
  goToWeek(delta: number): void { this.router.navigate(['/schedules/week', toIso(addDays(this.monday, delta * 7))]); }
  changeDepartment(): void { this.closePanel(); this.reload(); if (this.canEdit) { this.loadStaffData(); } }

  runs(id: number): boolean { return this.managedIds.has(id); }

  setView(v: 'grid' | 'list' | 'stats'): void {
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
    this.pub.set(null);
    if (this.deptId !== null) {
      this.api.publication(this.deptId, toIso(this.monday)).subscribe({ next: p => this.pub.set(p), error: () => this.pub.set(null) });
    }
    const dept = this.deptId;
    this.api.timeOff(undefined, toIso(this.monday), toIso(addDays(this.monday, 6)), dept).subscribe({
      next: list => this.weekTimeOff.set(list),
      error: () => this.weekTimeOff.set([])
    });
    if (!this.deptPeople().length) {
      this.api.employees().subscribe({
        next: list => this.deptPeople.set(list),
        error: () => {}
      });
    }
    // an employee loads every department they may see at once, so extra departments add into the hours card
    this.api.shifts(this.isStaff ? dept : null, toIso(this.monday), toIso(addDays(this.monday, 6))).subscribe({
      next: list => {
        this.weekAll.set(list);
        this.shifts.set(dept === null ? list : (this.isStaff ? list : list.filter(s => s.department.id === dept)));
        this.loading.set(false); this.loadError.set(''); done?.();
      },
      error: err => { this.loading.set(false); this.loadError.set(errorText(err)); }
    });
  }

  openShiftGeneration(): void {
    this.shiftGenPrompt = true;
    this.shiftGenBusy = false;
    this.shiftGenError = '';
    this.shiftGenResult = null;
    this.shiftGenClearExisting = false;
  }

  closeShiftGeneration(): void {
    if (this.shiftGenBusy) { return; }
    this.shiftGenPrompt = false;
    this.shiftGenBusy = false;
    this.shiftGenError = '';
    this.shiftGenResult = null;
  }

  generateWeeklyShifts(): void {
    if (this.shiftGenBusy) { return; }
    this.shiftGenBusy = true;
    this.shiftGenError = '';
    this.shiftGenResult = null;

    const companyId = this.auth.me()?.profile?.company?.id ?? 1;
    const payload: GenerateShiftsPayload = {
      company_id: companyId,
      week_start: toIso(this.monday),
      department_id: this.deptId,
      clear_existing: this.shiftGenClearExisting,
    };

    const startTime = Date.now();
    this.api.generateShifts(payload).subscribe({
      next: res => {
        const elapsed = Date.now() - startTime;
        const delay = Math.max(0, 800 - elapsed);
        setTimeout(() => {
          this.shiftGenBusy = false;
          this.shiftGenResult = res;
          this.reload();
        }, delay);
      },
      error: err => {
        this.shiftGenBusy = false;
        this.shiftGenError = errorText(err) || 'Failed to generate shifts. Please check your tasks and hours.';
      }
    });
  }

  private loadStaffData(): void {
    this.api.employees().subscribe(list => this.deptPeople.set(list));
    this.api.tasks(this.deptId).subscribe(list => this.tasks.set(list));
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
    this.toAddList = [];
    this.newNote = '';
    this.noteEditId = null;
    if (!this.deptPeople().length) {
      this.loadStaffData();
    }
  }

  closePanel(): void { this.outsidePrompt = null; this.panel = null; this.activeShiftId = null; this.panelError = ''; this.requestMode = null; this.confirmPrompt = null; this.confirmed = { timeOff: false, warnings: false }; this.toAddList = []; }

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
    this.api.assign(shift.id, employeeId, { timeOff: this.confirmed.timeOff, warnings: this.confirmed.warnings }, this.newNote, shift).subscribe({
      next: updated => {
        this.applyUpdated(updated);
        this.toAdd = null;
        this.toAddList = [];
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

  addMultiplePeople(): void {
    const shift = this.activeShift;
    if (!shift || !this.toAddList.length || this.busy) { return; }
    this.busy = true;
    this.panelError = '';
    const employeeIds = [...this.toAddList];
    this.api.assign(shift.id, employeeIds, { timeOff: this.confirmed.timeOff, warnings: this.confirmed.warnings }, this.newNote, shift).subscribe({
      next: updated => {
        this.applyUpdated(updated);
        this.toAddList = [];
        this.toAdd = null;
        this.newNote = '';
        this.closePanel();
        this.reload();
      },
      error: err => {
        this.fail(err);
      }
    });
  }

  toggleToAddList(empId: number): void {
    const shift = this.activeShift;
    const maxAddable = shift ? shift.open_count : 0;
    if (this.toAddList.includes(empId)) {
      this.toAddList = this.toAddList.filter(id => id !== empId);
    } else {
      if (this.toAddList.length < maxAddable) {
        this.toAddList = [...this.toAddList, empId];
      }
    }
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

  // --- smart shift assignment ---
  openShiftAssignment(): void {
    this.shiftAssignPrompt = true;
    this.shiftAssignBusy = false;
    this.shiftAssignError = '';
    this.shiftAssignResult = null;
  }

  closeShiftAssignment(): void {
    if (this.shiftAssignBusy) { return; }
    this.shiftAssignPrompt = false;
    this.shiftAssignBusy = false;
    this.shiftAssignError = '';
    this.shiftAssignResult = null;
  }

  executeShiftAssignment(): void {
    if (this.shiftAssignBusy) { return; }
    this.shiftAssignBusy = true;
    this.shiftAssignError = '';
    this.shiftAssignResult = null;

    const companyId = this.auth.me()?.profile?.company?.id ?? 1;
    const payload: AssignShiftsPayload = {
      company_id: companyId,
      week_start: toIso(this.monday),
      department_id: this.deptId,
    };

    const startTime = Date.now();
    this.api.assignShifts(payload).subscribe({
      next: res => {
        const elapsed = Date.now() - startTime;
        const delay = Math.max(0, 700 - elapsed);
        setTimeout(() => {
          this.shiftAssignBusy = false;
          this.shiftAssignResult = res;
          this.reload();
        }, delay);
      },
      error: (err: HttpErrorResponse) => {
        this.shiftAssignBusy = false;
        if (err.status === 409 && err.error?.code === 'pending_time_off') {
          this.autoPrompt = { count: err.error.count, people: err.error.people ?? [] };
        } else {
          this.shiftAssignError = errorText(err) || 'Failed to assign shifts using smart scheduler.';
        }
      }
    });
  }

  // --- clear assignments ---
  openClearAssignments(): void {
    this.clearPrompt = true;
    this.clearBusy = false;
    this.clearError = '';
  }

  closeClearAssignments(): void {
    if (this.clearBusy) { return; }
    this.clearPrompt = false;
    this.clearBusy = false;
    this.clearError = '';
  }

  confirmClearAssignments(): void {
    if (this.clearBusy) { return; }
    this.clearBusy = true;
    this.clearError = '';

    const companyId = this.auth.me()?.profile?.company?.id ?? 1;
    const payload = {
      company_id: companyId,
      week_start: toIso(this.monday),
      department_id: this.deptId,
    };

    this.api.clearAssignments(payload).subscribe({
      next: res => {
        this.clearBusy = false;
        this.clearPrompt = false;
        this.clearSuccess = `Cleared assignments from ${res.cleared_count} shift slot${res.cleared_count === 1 ? '' : 's'}. All shifts are now open slots.`;
        this.reload();
        setTimeout(() => { this.clearSuccess = ''; }, 6000);
      },
      error: err => {
        this.clearBusy = false;
        this.clearError = errorText(err) || 'Failed to clear assignments.';
      }
    });
  }

  // --- clear shifts (delete all entries for the week) ---
  openClearShifts(): void {
    this.clearShiftsPrompt = true;
    this.clearShiftsBusy = false;
    this.clearShiftsError = '';
  }

  closeClearShifts(): void {
    if (this.clearShiftsBusy) { return; }
    this.clearShiftsPrompt = false;
    this.clearShiftsBusy = false;
    this.clearShiftsError = '';
  }

  confirmClearShifts(): void {
    if (this.clearShiftsBusy) { return; }
    this.clearShiftsBusy = true;
    this.clearShiftsError = '';

    const companyId = this.auth.me()?.profile?.company?.id ?? 1;
    const payload = {
      company_id: companyId,
      week_start: toIso(this.monday),
      department_id: this.deptId,
    };

    this.api.clearShifts(payload).subscribe({
      next: res => {
        this.clearShiftsBusy = false;
        this.clearShiftsPrompt = false;
        this.clearSuccess = `Deleted ${res.deleted_count} shift entr${res.deleted_count === 1 ? 'y' : 'ies'} for this week.`;
        this.reload();
        setTimeout(() => { this.clearSuccess = ''; }, 6000);
      },
      error: err => {
        this.clearShiftsBusy = false;
        this.clearShiftsError = errorText(err) || 'Failed to clear shift entries.';
      }
    });
  }

  // --- time off signifier helpers ---
  getTimeOff(empId: number, dateIso: string): TimeOff | null {
    if (!empId || !dateIso) { return null; }
    return this.weekTimeOff().find(to =>
      to.employee === empId &&
      to.status !== 'denied' &&
      to.start_date <= dateIso &&
      to.end_date >= dateIso
    ) ?? null;
  }

  hasTimeOff(empId: number, dateIso: string): boolean {
    return this.getTimeOff(empId, dateIso) !== null;
  }

  isApprovedTimeOff(empId: number, dateIso: string): boolean {
    const to = this.getTimeOff(empId, dateIso);
    return to !== null && to.status === 'approved';
  }

  timeOffLabel(empId: number, dateIso: string): string {
    const to = this.getTimeOff(empId, dateIso);
    if (!to) { return ''; }
    return to.status === 'approved' ? 'Time Off' : 'Pending Off';
  }

  runAuto(confirmPending = false): void {
    this.openShiftAssignment();
  }

  nameClass(p: ShiftPerson, dateIso?: string): string {
    const isOff = dateIso ? this.hasTimeOff(p.employee_id, dateIso) : false;
    const base = 'inline-flex items-center max-w-full truncate rounded-md border px-1.5 py-0.5 text-xs leading-tight ';
    if (isOff) {
      return base + 'bg-rose-100 border-rose-400 text-rose-800 font-bold';
    }
    const look = this.isMine(p) ? 'bg-brand-600 border-brand-700 text-white'
      : p.is_minor ? 'bg-yellow-100 border-yellow-400 text-yellow-800' : 'bg-brand-50 border-brand-300 text-brand-800';
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
    this.api.deleteShift(shiftId, s.schedule_ids).subscribe({
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
  newShiftDeptId: number | null = null;

  openAdd(iso?: string): void {
    this.panel = 'add';
    this.panelError = '';
    this.newShiftTaskId = null;
    this.newShiftDeptId = this.deptId ?? this.departments[0]?.id ?? null;
    this.newShiftEmployees = [];
    this.newShift = { ...this.newShift, shift_date: iso ?? toIso(this.monday), name: '', headcount: 1 };
    if (!this.tasks().length) {
      this.api.tasks(this.deptId).subscribe(list => this.tasks.set(list));
    }
    if (!this.deptPeople().length) {
      this.loadStaffData();
    }
  }

  onNewShiftTaskChange(taskId: number | null): void {
    this.newShiftTaskId = taskId;
    if (taskId) {
      const task = this.tasks().find(t => t.id === taskId);
      if (task) {
        this.newShift.name = task.name;
        this.newShift.headcount = task.required_people;
        if (task.department) {
          this.newShiftDeptId = typeof task.department === 'object' ? (task.department as any).id : task.department;
        }
        if (this.newShiftEmployees.length > task.required_people) {
          this.newShiftEmployees = this.newShiftEmployees.slice(0, task.required_people);
        }
      }
    }
  }

  get addableEmployeesForNewShift(): Employee[] {
    const list = this.deptPeople();
    const effectiveDeptId = this.newShiftTaskId
      ? (this.tasks().find(t => t.id === this.newShiftTaskId)?.department ?? this.newShiftDeptId)
      : this.newShiftDeptId;
    const targetDeptId = typeof effectiveDeptId === 'object' && effectiveDeptId !== null ? (effectiveDeptId as any).id : effectiveDeptId;
    if (!targetDeptId) { return list; }
    return list.filter(p => {
      const pDeptId = typeof p.department === 'object' ? p.department?.id : p.department;
      return pDeptId === targetDeptId || (Array.isArray(p.extra_departments) && p.extra_departments.some(d => d.id === targetDeptId));
    });
  }

  isEmployeeSelectedForNewShift(empId: number): boolean {
    return this.newShiftEmployees.includes(empId);
  }

  toggleEmployeeForNewShift(empId: number): void {
    if (this.newShiftEmployees.includes(empId)) {
      this.newShiftEmployees = this.newShiftEmployees.filter(id => id !== empId);
    } else {
      if (this.newShiftEmployees.length < this.newShift.headcount) {
        this.newShiftEmployees = [...this.newShiftEmployees, empId];
      }
    }
  }

  createShift(allowOutside = false): void {
    if (this.busy) { return; }
    this.panelError = '';

    const effectiveDept = this.newShiftTaskId
      ? (this.tasks().find(t => t.id === this.newShiftTaskId)?.department ?? this.newShiftDeptId ?? this.deptId)
      : (this.newShiftDeptId ?? this.deptId);
    const targetDeptId = typeof effectiveDept === 'object' && effectiveDept !== null ? (effectiveDept as any).id : effectiveDept;

    if (!targetDeptId && !this.newShiftTaskId) {
      this.panelError = 'Please select a department for this shift.';
      return;
    }

    if (!this.newShift.name?.trim()) {
      this.panelError = 'Please enter a schedule name.';
      return;
    }

    this.busy = true;
    const payload = {
      ...this.newShift,
      task: this.newShiftTaskId,
      employees: [...this.newShiftEmployees],
      headcount: Number(this.newShift.headcount),
      department: targetDeptId,
      ...(allowOutside ? { allow_outside_hours: true } : {})
    };
    this.api.createShift(payload).subscribe({
      next: () => {
        this.busy = false;
        this.newShiftEmployees = [];
        this.newShiftTaskId = null;
        this.newShiftDeptId = null;
        this.closePanel();
        this.reload();
      },
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
