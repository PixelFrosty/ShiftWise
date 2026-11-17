import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Department, Milestone, MilestoneStatus, Project } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

const STATUS_LABEL: Record<MilestoneStatus, string> = { todo: 'To do', in_progress: 'In progress', done: 'Done' };

@Component({
  selector: 'app-projects',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="max-w-4xl mx-auto">
      <div class="flex flex-wrap items-center gap-3 mb-1">
        <h1 class="text-2xl font-bold text-slate-900 flex-1">Projects</h1>
        @if (isStaff() && !formOpen()) {
          <button type="button" (click)="openProjectForm(null)" class="h-10 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-md cursor-pointer" data-testid="new-project">New project</button>
        }
      </div>
      <p class="text-sm text-slate-500 mb-4">
        {{ isStaff() ? 'Create projects, add milestones and assign people. Employees see every milestone but only their own assignments.' : 'Projects for your department and the company. Milestones assigned to you are highlighted.' }}
      </p>
      @if (error()) { <div class="mb-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm" data-testid="project-error">{{ error() }}</div> }

      @if (formOpen()) {
        <form class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-5" (ngSubmit)="saveProject()" data-testid="project-form">
          <h2 class="font-bold text-slate-800 mb-3">{{ editingId ? 'Edit project' : 'New project' }}</h2>
          <div class="grid sm:grid-cols-3 gap-3">
            <div class="sm:col-span-3"><label for="pname" class="block text-xs font-bold text-slate-600 mb-1">Name</label>
              <input id="pname" name="pname" maxlength="255" [(ngModel)]="pName" class="w-full h-10 border border-slate-300 rounded-md px-3 text-sm" data-testid="project-name" /></div>
            <div><label for="pdept" class="block text-xs font-bold text-slate-600 mb-1">Belongs to</label>
              <select id="pdept" name="pdept" [(ngModel)]="pDept" class="w-full h-10 border border-slate-300 rounded-md px-2 text-sm" data-testid="project-dept">
                @if (isCeo()) { <option [ngValue]="null">Whole company</option> }
                @for (d of myDepartments(); track d.id) { <option [ngValue]="d.id">{{ d.name }}</option> }
              </select></div>
            <div><label for="pprio" class="block text-xs font-bold text-slate-600 mb-1">Priority</label>
              <select id="pprio" name="pprio" [(ngModel)]="pPriority" class="w-full h-10 border border-slate-300 rounded-md px-2 text-sm">
                <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
              </select></div>
            <div class="flex items-end"><label class="flex items-center gap-2 text-sm h-10"><input type="checkbox" name="pactive" [(ngModel)]="pActive" /> Active</label></div>
            <div class="sm:col-span-3"><label for="pdesc" class="block text-xs font-bold text-slate-600 mb-1">Description (optional)</label>
              <textarea id="pdesc" name="pdesc" rows="2" [(ngModel)]="pDesc" class="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"></textarea></div>
          </div>
          <div class="mt-3 flex gap-2">
            <button type="submit" class="h-10 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-md cursor-pointer" data-testid="save-project">Save project</button>
            <button type="button" (click)="formOpen.set(false)" class="h-10 px-4 border border-slate-300 text-sm font-semibold rounded-md cursor-pointer">Cancel</button>
          </div>
        </form>
      }

      @if (loaded() && mine().length) {
        <div class="bg-emerald-50 border border-emerald-200 rounded-xl p-4 mb-5" data-testid="my-milestones">
          <h2 class="font-bold text-emerald-900 mb-2">Assigned to you</h2>
          <ul class="space-y-1.5">
            @for (row of mine(); track row.m.id) {
              <li class="text-sm flex flex-wrap items-center gap-2" data-testid="my-milestone">
                <span class="font-semibold text-slate-800">{{ row.m.title }}</span>
                <span class="text-slate-500">· {{ row.p.name }}{{ row.m.due_date ? ' · due ' + row.m.due_date : '' }}</span>
                <span [class]="chip(row.m.status)">{{ label(row.m.status) }}</span>
              </li>
            }
          </ul>
        </div>
      }

      <div class="space-y-3">
        @for (p of projects(); track p.id) {
          <div class="bg-white rounded-xl border border-slate-200 shadow-sm" data-testid="project">
            <div class="p-4 flex flex-wrap items-center gap-3">
              <button type="button" (click)="toggle(p.id)" class="flex-1 min-w-[220px] text-left cursor-pointer" [attr.aria-expanded]="open().has(p.id)" data-testid="project-toggle">
                <div class="font-bold text-slate-900" data-testid="project-title">{{ p.name }}</div>
                <div class="text-xs text-slate-500">{{ p.department_name || 'Whole company' }} · {{ p.priority }} priority{{ p.is_active ? '' : ' · inactive' }}</div>
              </button>
              <div class="w-40">
                <div class="text-xs text-slate-500 mb-1" data-testid="project-progress">{{ p.milestone_counts.done }} of {{ p.milestone_counts.total }} done</div>
                <div class="h-2 bg-slate-100 rounded-full overflow-hidden"><div class="h-full bg-emerald-500" [style.width.%]="pct(p)"></div></div>
              </div>
              @if (p.can_edit) {
                <button type="button" (click)="openProjectForm(p)" class="text-xs font-semibold text-slate-600 hover:underline cursor-pointer" data-testid="edit-project">Edit</button>
                <button type="button" (click)="removeProject(p)" class="text-xs font-semibold text-rose-600 hover:underline cursor-pointer" data-testid="delete-project">Delete</button>
              }
            </div>
            @if (open().has(p.id)) {
              <div class="border-t border-slate-100 p-4">
                @if (p.description) { <p class="text-sm text-slate-600 mb-3 whitespace-pre-line">{{ p.description }}</p> }
                <div class="space-y-2">
                  @for (m of p.milestones; track m.id) {
                    <div class="rounded-lg border p-3" [class]="m.assigned_to_me ? 'border-emerald-300 bg-emerald-50' : 'border-slate-200'" [attr.data-mine]="m.assigned_to_me" data-testid="milestone">
                      <div class="flex flex-wrap items-center gap-2">
                        <span class="font-semibold text-sm text-slate-800" data-testid="milestone-title">{{ m.title }}</span>
                        @if (m.assigned_to_me) { <span class="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-600 text-white" data-testid="assigned-badge">Assigned to you</span> }
                        <span class="text-xs text-slate-500">{{ m.due_date ? 'due ' + m.due_date : 'no due date' }}</span>
                        <span class="flex-1"></span>
                        @if (m.assigned_to_me && !p.can_edit) {
                          <select [ngModel]="m.status" (ngModelChange)="setStatus(m, $event)" class="h-8 border border-slate-300 rounded-md px-2 text-xs bg-white" aria-label="Status" data-testid="my-status-select">
                            @for (s of statuses; track s) { <option [value]="s">{{ label(s) }}</option> }
                          </select>
                        } @else {
                          <span [class]="chip(m.status)" data-testid="milestone-status">{{ label(m.status) }}</span>
                        }
                        @if (p.can_edit) {
                          <button type="button" (click)="openMilestoneForm(p, m)" class="text-xs font-semibold text-slate-600 hover:underline cursor-pointer" data-testid="edit-milestone">Edit</button>
                          <button type="button" (click)="removeMilestone(m)" class="text-xs font-semibold text-rose-600 hover:underline cursor-pointer" data-testid="delete-milestone">Delete</button>
                        }
                      </div>
                      @if (m.description) { <p class="text-xs text-slate-600 mt-1 whitespace-pre-line">{{ m.description }}</p> }
                      @if (p.can_edit) {
                        <div class="text-xs text-slate-500 mt-1" data-testid="assignees">Assigned: {{ m.assignees.length ? names(m) : 'nobody yet' }}</div>
                      }
                    </div>
                  } @empty {
                    <div class="text-sm text-slate-500">No milestones yet.</div>
                  }
                </div>
                @if (p.can_edit && msProject !== p.id) {
                  <button type="button" (click)="openMilestoneForm(p, null)" class="mt-3 h-9 px-3 border border-emerald-600 text-emerald-700 hover:bg-emerald-50 text-sm font-semibold rounded-md cursor-pointer" data-testid="add-milestone">Add milestone</button>
                }
                @if (msProject === p.id) {
                  <form class="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3" (ngSubmit)="saveMilestone(p)" data-testid="milestone-form">
                    <div class="grid sm:grid-cols-3 gap-3">
                      <div class="sm:col-span-2"><label for="mtitle" class="block text-xs font-bold text-slate-600 mb-1">Title</label>
                        <input id="mtitle" name="mtitle" maxlength="200" [(ngModel)]="mTitle" class="w-full h-10 border border-slate-300 rounded-md px-3 text-sm" data-testid="milestone-title-input" /></div>
                      <div><label for="mdue" class="block text-xs font-bold text-slate-600 mb-1">Due date</label>
                        <input id="mdue" name="mdue" type="date" [(ngModel)]="mDue" class="w-full h-10 border border-slate-300 rounded-md px-2 text-sm" data-testid="milestone-due" /></div>
                      <div class="sm:col-span-2"><label for="mdesc" class="block text-xs font-bold text-slate-600 mb-1">Description (optional)</label>
                        <textarea id="mdesc" name="mdesc" rows="2" [(ngModel)]="mDesc" class="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"></textarea></div>
                      <div><label for="mstatus" class="block text-xs font-bold text-slate-600 mb-1">Status</label>
                        <select id="mstatus" name="mstatus" [(ngModel)]="mStatus" class="w-full h-10 border border-slate-300 rounded-md px-2 text-sm">
                          @for (s of statuses; track s) { <option [value]="s">{{ label(s) }}</option> }
                        </select></div>
                    </div>
                    <fieldset class="mt-3">
                      <legend class="text-xs font-bold text-slate-600 mb-1">Assign to</legend>
                      <div class="flex flex-wrap gap-x-4 gap-y-1">
                        @for (person of people(); track person.id) {
                          <label class="flex items-center gap-1.5 text-sm"><input type="checkbox" [checked]="mAssignees().has(person.id)" (change)="toggleAssignee(person.id)" [attr.data-assignee]="person.name" /> {{ person.name }}</label>
                        } @empty { <span class="text-sm text-slate-500">No one to assign.</span> }
                      </div>
                    </fieldset>
                    <div class="mt-3 flex gap-2">
                      <button type="submit" class="h-9 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-md cursor-pointer" data-testid="save-milestone">Save milestone</button>
                      <button type="button" (click)="msProject = null" class="h-9 px-4 border border-slate-300 text-sm font-semibold rounded-md cursor-pointer">Cancel</button>
                    </div>
                  </form>
                }
              </div>
            }
          </div>
        } @empty {
          @if (loaded()) {
            <div class="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500 text-sm" data-testid="no-projects">
              {{ isStaff() ? 'No projects yet. Create one to get started.' : 'There are no projects for you to see right now.' }}
            </div>
          }
        }
      </div>
    </div>`
})
export class ProjectsComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  statuses: MilestoneStatus[] = ['todo', 'in_progress', 'done'];
  isStaff = computed(() => this.auth.role === 'ceo' || this.auth.role === 'manager');
  isCeo = computed(() => this.auth.role === 'ceo');
  projects = signal<Project[]>([]);
  loaded = signal(false);
  error = signal('');
  open = signal<Set<number>>(new Set());
  departments = signal<Department[]>([]);
  myDepartments = computed(() => {
    const managed = new Set((this.auth.me()?.profile?.managed_departments ?? []).map(d => d.id));
    return this.departments().filter(d => this.isCeo() || managed.has(d.id));
  });
  mine = computed(() => this.projects().flatMap(p => p.milestones.filter(m => m.assigned_to_me).map(m => ({ p, m }))));

  // project form
  formOpen = signal(false);
  editingId: number | null = null;
  pName = ''; pDesc = ''; pDept: number | null = null; pPriority = 'medium'; pActive = true;

  // milestone form
  msProject: number | null = null;
  msEditing: number | null = null;
  mTitle = ''; mDesc = ''; mDue = ''; mStatus: MilestoneStatus = 'todo';
  mAssignees = signal<Set<number>>(new Set());
  people = signal<{ id: number; name: string }[]>([]);

  constructor() {
    this.reload();
    if (this.isStaff()) { this.api.departments().subscribe(d => this.departments.set(d)); }
  }

  reload(): void {
    this.api.projects().subscribe({
      next: list => { this.projects.set(list); this.loaded.set(true); },
      error: err => { this.error.set(errorText(err)); this.loaded.set(true); }
    });
  }

  label(s: MilestoneStatus): string { return STATUS_LABEL[s]; }
  names(m: Milestone): string { return m.assignees.map(a => a.name).join(', '); }
  pct(p: Project): number { return p.milestone_counts.total ? Math.round(100 * p.milestone_counts.done / p.milestone_counts.total) : 0; }
  chip(s: MilestoneStatus): string {
    return 'px-2 py-0.5 rounded-full text-xs font-semibold ' + (s === 'done' ? 'bg-emerald-100 text-emerald-800' : s === 'in_progress' ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-700');
  }
  toggle(id: number): void {
    const next = new Set(this.open());
    if (!next.delete(id)) { next.add(id); }
    this.open.set(next);
  }

  openProjectForm(p: Project | null): void {
    this.error.set('');
    this.editingId = p?.id ?? null;
    this.pName = p?.name ?? ''; this.pDesc = p?.description ?? ''; this.pPriority = p?.priority ?? 'medium'; this.pActive = p?.is_active ?? true;
    this.pDept = p ? p.department : (this.isCeo() ? null : this.myDepartments()[0]?.id ?? null);
    this.formOpen.set(true);
  }

  saveProject(): void {
    if (!this.pName.trim()) { this.error.set('Give the project a name.'); return; }
    const company = this.auth.me()?.profile?.company.id;
    const body = { name: this.pName.trim(), description: this.pDesc, department: this.pDept, priority: this.pPriority as Project['priority'], is_active: this.pActive, ...(this.editingId ? {} : { company }) };
    this.api.saveProject(this.editingId, body).subscribe({
      next: () => { this.formOpen.set(false); this.error.set(''); this.reload(); },
      error: err => this.error.set(errorText(err))
    });
  }

  removeProject(p: Project): void {
    if (!confirm(`Delete "${p.name}" and its milestones?`)) { return; }
    this.api.deleteProject(p.id).subscribe({ next: () => this.reload(), error: err => this.error.set(errorText(err)) });
  }

  openMilestoneForm(p: Project, m: Milestone | null): void {
    this.error.set('');
    this.msProject = p.id; this.msEditing = m?.id ?? null;
    this.mTitle = m?.title ?? ''; this.mDesc = m?.description ?? ''; this.mDue = m?.due_date ?? ''; this.mStatus = m?.status ?? 'todo';
    this.mAssignees.set(new Set((m?.assignees ?? []).map(a => a.id)));
    this.people.set([]);
    this.api.projectPeople(p.department).subscribe(list => this.people.set(list));
  }

  toggleAssignee(id: number): void {
    const next = new Set(this.mAssignees());
    if (!next.delete(id)) { next.add(id); }
    this.mAssignees.set(next);
  }

  saveMilestone(p: Project): void {
    if (!this.mTitle.trim()) { this.error.set('Give the milestone a title.'); return; }
    const body = { title: this.mTitle.trim(), description: this.mDesc, due_date: this.mDue || null, status: this.mStatus, assignee_ids: [...this.mAssignees()], ...(this.msEditing ? {} : { project: p.id }) };
    this.api.saveMilestone(this.msEditing, body).subscribe({
      next: () => { this.msProject = null; this.error.set(''); this.reload(); },
      error: err => this.error.set(errorText(err))
    });
  }

  removeMilestone(m: Milestone): void {
    this.api.deleteMilestone(m.id).subscribe({ next: () => this.reload(), error: err => this.error.set(errorText(err)) });
  }

  setStatus(m: Milestone, status: MilestoneStatus): void {
    this.api.saveMilestone(m.id, { status }).subscribe({ next: () => this.reload(), error: err => { this.error.set(errorText(err)); this.reload(); } });
  }
}
