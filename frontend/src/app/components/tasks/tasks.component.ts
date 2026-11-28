import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Department, Employee, TaskItem, TaskStatus } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: 'To Do',
  in_progress: 'In Progress',
  done: 'Done'
};

const STATUS_BADGE_CLASSES: Record<TaskStatus, string> = {
  todo: 'bg-slate-100 text-slate-700',
  in_progress: 'bg-amber-100 text-amber-800',
  done: 'bg-emerald-100 text-emerald-800'
};

const PRIORITY_BADGE_CLASSES: Record<TaskItem['priority'], string> = {
  low: 'bg-slate-100 text-slate-700',
  medium: 'bg-blue-100 text-blue-800',
  high: 'bg-rose-100 text-rose-800'
};

@Component({
  selector: 'app-tasks',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="max-w-5xl mx-auto space-y-6">
      <!-- Page Header -->
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 class="text-2xl font-bold text-slate-900">Tasks</h1>
          <p class="text-sm text-slate-500 mt-1">Track team tasks, assignees, priorities, and completion progress</p>
        </div>
        @if (!formOpen()) {
          <button
            type="button"
            (click)="openCreateForm()"
            class="inline-flex items-center px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-semibold shadow-sm transition border-0 cursor-pointer"
            data-testid="new-task-btn">
            + New Task
          </button>
        }
      </div>

      @if (error()) {
        <div class="p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-sm font-medium" data-testid="task-error">
          {{ error() }}
        </div>
      }

      <!-- Create Task Card -->
      @if (formOpen()) {
        <form (ngSubmit)="createTask()" class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4" data-testid="task-form">
          <div class="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h2 class="text-lg font-bold text-slate-900">Create New Task</h2>
              <p class="text-xs text-slate-500">Assign work, set a priority, and optionally add a due date</p>
            </div>
            <button
              type="button"
              (click)="closeCreateForm()"
              class="text-slate-400 hover:text-slate-600 text-xl font-bold bg-transparent border-0 cursor-pointer p-1 leading-none">
              &times;
            </button>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div class="sm:col-span-2 lg:col-span-2">
              <label for="taskName" class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Task Name *</label>
              <input
                id="taskName"
                name="taskName"
                type="text"
                maxlength="255"
                [(ngModel)]="newName"
                placeholder="e.g. Restock front display"
                required
                class="form-input"
                data-testid="task-name-input" />
            </div>

            <div>
              <label for="taskAssignee" class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Assignee</label>
              <select id="taskAssignee" name="taskAssignee" [(ngModel)]="newEmployeeId" class="form-select" data-testid="task-assignee-select">
                <option [ngValue]="null">Unassigned</option>
                @for (emp of employees(); track emp.id) {
                  <option [ngValue]="emp.id">{{ emp.name }}</option>
                }
              </select>
            </div>

            <div>
              <label for="taskPriority" class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Priority</label>
              <select id="taskPriority" name="taskPriority" [(ngModel)]="newPriority" class="form-select" data-testid="task-priority-select">
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>

            <div>
              <label for="taskStatus" class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Status</label>
              <select id="taskStatus" name="taskStatus" [(ngModel)]="newStatus" class="form-select" data-testid="task-status-select">
                @for (s of statuses; track s) {
                  <option [value]="s">{{ statusLabel(s) }}</option>
                }
              </select>
            </div>

            <div>
              <label for="taskDue" class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Due Date</label>
              <input id="taskDue" name="taskDue" type="date" [(ngModel)]="newDueDate" class="form-input" data-testid="task-due-input" />
            </div>

            <div>
              <label for="taskDept" class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Department</label>
              <select id="taskDept" name="taskDept" [(ngModel)]="newDepartmentId" class="form-select">
                <option [ngValue]="null">General</option>
                @for (dept of departments(); track dept.id) {
                  <option [ngValue]="dept.id">{{ dept.name }}</option>
                }
              </select>
            </div>

            <div class="sm:col-span-2">
              <label for="taskDesc" class="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">Description (optional)</label>
              <input
                id="taskDesc"
                name="taskDesc"
                type="text"
                [(ngModel)]="newDescription"
                placeholder="Brief details or instructions..."
                class="form-input"
                data-testid="task-desc-input" />
            </div>
          </div>

          <div class="flex justify-end gap-3 pt-3 border-t border-slate-100">
            <button
              type="button"
              (click)="closeCreateForm()"
              [disabled]="isSaving()"
              class="px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-lg text-sm font-medium transition cursor-pointer">
              Cancel
            </button>
            <button
              type="submit"
              [disabled]="isSaving() || !newName.trim()"
              class="px-5 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-lg text-sm font-semibold shadow-sm transition cursor-pointer"
              data-testid="save-task-btn">
              {{ isSaving() ? 'Creating…' : 'Create Task' }}
            </button>
          </div>
        </form>
      }

      <!-- Summary & Filter Bar -->
      <div class="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            (click)="statusFilter.set('all')"
            class="px-3 py-1.5 rounded-full text-xs font-semibold transition cursor-pointer"
            [class]="statusFilter() === 'all' ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'">
            All ({{ tasks().length }})
          </button>
          @for (s of statuses; track s) {
            <button
              type="button"
              (click)="statusFilter.set(s)"
              class="px-3 py-1.5 rounded-full text-xs font-semibold transition cursor-pointer"
              [class]="statusFilter() === s ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700 hover:bg-slate-200'">
              {{ statusLabel(s) }} ({{ statusCounts()[s] }})
            </button>
          }
        </div>

        <div class="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            [ngModel]="searchQuery()"
            (ngModelChange)="searchQuery.set($event)"
            name="searchQuery"
            placeholder="Search tasks by name, description, or assignee..."
            class="form-input flex-1" />

          <select
            [ngModel]="priorityFilter()"
            (ngModelChange)="priorityFilter.set($event)"
            name="priorityFilter"
            class="form-select sm:w-48">
            <option value="all">All Priorities</option>
            <option value="high">High Priority</option>
            <option value="medium">Medium Priority</option>
            <option value="low">Low Priority</option>
          </select>

          @if (hasActiveFilters()) {
            <button
              type="button"
              (click)="clearFilters()"
              class="px-4 py-2 border border-slate-200 hover:bg-slate-100 text-slate-600 rounded-lg text-sm font-medium transition cursor-pointer">
              Clear
            </button>
          }
        </div>
      </div>

      <!-- Task Cards -->
      <div class="space-y-3">
        @for (task of filteredTasks(); track task.id) {
          <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 hover:border-brand-300 transition" data-testid="task-card">
            <div class="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
              <div class="space-y-2 flex-1 min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <h2 class="text-base font-bold text-slate-900" data-testid="task-title">{{ task.name }}</h2>
                  <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold" [class]="statusBadge(task.status)" data-testid="task-status-badge">
                    {{ statusLabel(task.status || 'todo') }}
                  </span>
                  <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize" [class]="priorityBadge(task.priority)" data-testid="task-priority-badge">
                    {{ task.priority }} priority
                  </span>
                  @if (task.department_name) {
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700">
                      {{ task.department_name }}
                    </span>
                  }
                </div>

                @if (task.description) {
                  <p class="text-sm text-slate-600">{{ task.description }}</p>
                }

                <div class="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-500 pt-1">
                  <span data-testid="task-assignee">
                    <span class="font-semibold text-slate-600">Assignee:</span> {{ assigneeName(task) }}
                  </span>
                  <span data-testid="task-due-date">
                    <span class="font-semibold text-slate-600">Due:</span> {{ task.due_date || 'No due date' }}
                  </span>
                </div>
              </div>

              <!-- Status Updater & Delete Actions -->
              <div class="flex flex-wrap items-center gap-3 sm:justify-end shrink-0">
                <select
                  [ngModel]="task.status || 'todo'"
                  (ngModelChange)="updateStatus(task, $event)"
                  aria-label="Task status"
                  class="h-9 border border-slate-300 rounded-lg px-2.5 text-xs font-medium bg-white text-slate-700 focus:outline-none focus:border-brand-500"
                  data-testid="task-status-select-inline">
                  @for (s of statuses; track s) {
                    <option [value]="s">{{ statusLabel(s) }}</option>
                  }
                </select>

                @if (confirmingDeleteId() === task.id) {
                  <div class="flex items-center gap-2">
                    <button
                      type="button"
                      (click)="deleteTask(task.id)"
                      class="px-3 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-semibold transition cursor-pointer"
                      data-testid="confirm-delete-task">
                      Confirm
                    </button>
                    <button
                      type="button"
                      (click)="confirmingDeleteId.set(null)"
                      class="px-3 py-1.5 border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-medium transition cursor-pointer">
                      Cancel
                    </button>
                  </div>
                } @else {
                  <button
                    type="button"
                    (click)="confirmingDeleteId.set(task.id)"
                    class="px-3 py-1.5 border border-rose-200 text-rose-600 hover:bg-rose-50 rounded-lg text-xs font-semibold transition cursor-pointer"
                    data-testid="delete-task-btn">
                    Delete
                  </button>
                }
              </div>
            </div>
          </div>
        } @empty {
          @if (loaded()) {
            <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-10 text-center text-slate-500 text-sm" data-testid="no-tasks">
              {{ hasActiveFilters() ? 'No tasks match your current filters.' : 'No tasks yet. Click "+ New Task" to create one.' }}
            </div>
          }
        }
      </div>
    </div>
  `
})
export class TasksComponent implements OnInit {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  readonly statuses: TaskStatus[] = ['todo', 'in_progress', 'done'];

  tasks = signal<TaskItem[]>([]);
  employees = signal<Employee[]>([]);
  departments = signal<Department[]>([]);
  loaded = signal(false);
  error = signal('');
  formOpen = signal(false);
  isSaving = signal(false);
  confirmingDeleteId = signal<number | null>(null);

  searchQuery = signal('');
  statusFilter = signal<'all' | TaskStatus>('all');
  priorityFilter = signal<'all' | TaskItem['priority']>('all');

  newName = '';
  newDescription = '';
  newPriority: TaskItem['priority'] = 'medium';
  newStatus: TaskStatus = 'todo';
  newDueDate = '';
  newEmployeeId: number | null = null;
  newDepartmentId: number | null = null;

  private employeeNameMap = computed(() => new Map(this.employees().map(e => [e.id, e.name])));

  statusCounts = computed(() => {
    const counts: Record<TaskStatus, number> = { todo: 0, in_progress: 0, done: 0 };
    for (const task of this.tasks()) {
      const s = task.status ?? 'todo';
      counts[s] = (counts[s] || 0) + 1;
    }
    return counts;
  });

  hasActiveFilters = computed(() =>
    this.searchQuery().trim().length > 0 || this.statusFilter() !== 'all' || this.priorityFilter() !== 'all'
  );

  filteredTasks = computed(() => {
    const query = this.searchQuery().trim().toLowerCase();
    const status = this.statusFilter();
    const priority = this.priorityFilter();

    return this.tasks().filter(task => {
      const taskStatus = task.status ?? 'todo';
      if (status !== 'all' && taskStatus !== status) { return false; }
      if (priority !== 'all' && task.priority !== priority) { return false; }
      if (!query) { return true; }

      const assignee = this.assigneeName(task).toLowerCase();
      return (
        task.name.toLowerCase().includes(query) ||
        (task.description || '').toLowerCase().includes(query) ||
        assignee.includes(query)
      );
    });
  });

  ngOnInit(): void {
    this.loadTasks();
    this.api.employees().subscribe({
      next: list => this.employees.set(list),
      error: () => {}
    });
    this.api.departments().subscribe({
      next: list => this.departments.set(list),
      error: () => {}
    });
  }

  loadTasks(): void {
    this.api.tasks().subscribe({
      next: list => {
        this.tasks.set(list);
        this.loaded.set(true);
      },
      error: err => {
        this.error.set(errorText(err));
        this.loaded.set(true);
      }
    });
  }

  statusLabel(status: TaskStatus): string {
    return STATUS_LABELS[status] || 'To Do';
  }

  statusBadge(status?: TaskStatus): string {
    return STATUS_BADGE_CLASSES[status ?? 'todo'] || STATUS_BADGE_CLASSES.todo;
  }

  priorityBadge(priority: TaskItem['priority']): string {
    return PRIORITY_BADGE_CLASSES[priority] || PRIORITY_BADGE_CLASSES.medium;
  }

  assigneeName(task: TaskItem): string {
    if (task.employee_name) { return task.employee_name; }
    if (task.employee !== null && task.employee !== undefined) {
      return this.employeeNameMap().get(task.employee) || `Employee #${task.employee}`;
    }
    return 'Unassigned';
  }

  openCreateForm(): void {
    this.error.set('');
    this.newName = '';
    this.newDescription = '';
    this.newPriority = 'medium';
    this.newStatus = 'todo';
    this.newDueDate = '';
    this.newEmployeeId = null;
    this.newDepartmentId = this.auth.me()?.profile?.department?.id ?? null;
    this.formOpen.set(true);
  }

  closeCreateForm(): void {
    this.formOpen.set(false);
    this.error.set('');
  }

  createTask(): void {
    if (!this.newName.trim()) {
      this.error.set('Please enter a task name.');
      return;
    }

    this.isSaving.set(true);
    this.error.set('');

    const companyId = this.auth.me()?.profile?.company?.id ?? 1;
    const empName = this.newEmployeeId ? (this.employeeNameMap().get(this.newEmployeeId) ?? null) : null;
    const deptName = this.newDepartmentId
      ? (this.departments().find(d => d.id === this.newDepartmentId)?.name ?? null)
      : null;

    this.api.createTask({
      company: companyId,
      name: this.newName.trim(),
      description: this.newDescription.trim(),
      priority: this.newPriority,
      status: this.newStatus,
      due_date: this.newDueDate || null,
      employee: this.newEmployeeId,
      employee_name: empName,
      department: this.newDepartmentId,
      department_name: deptName
    }).subscribe({
      next: created => {
        this.isSaving.set(false);
        this.formOpen.set(false);
        this.tasks.update(list => [created, ...list]);
      },
      error: err => {
        this.isSaving.set(false);
        this.error.set(errorText(err));
      }
    });
  }

  updateStatus(task: TaskItem, status: TaskStatus): void {
    this.error.set('');
    this.api.updateTask(task.id, { status }).subscribe({
      next: updated => {
        this.tasks.update(list => list.map(t => t.id === task.id ? { ...t, ...updated, status } : t));
      },
      error: err => this.error.set(errorText(err))
    });
  }

  deleteTask(id: number): void {
    this.error.set('');
    this.api.deleteTask(id).subscribe({
      next: () => {
        this.confirmingDeleteId.set(null);
        this.tasks.update(list => list.filter(t => t.id !== id));
      },
      error: err => this.error.set(errorText(err))
    });
  }

  clearFilters(): void {
    this.searchQuery.set('');
    this.statusFilter.set('all');
    this.priorityFilter.set('all');
  }
}
