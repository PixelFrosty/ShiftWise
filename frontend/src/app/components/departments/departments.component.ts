import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Department } from '../../core/api.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-departments',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="max-w-3xl mx-auto">
      <h1 class="text-2xl font-bold text-slate-900">Departments</h1>
      <p class="text-sm text-slate-500 mb-4">Only the General Manager can add, rename or remove departments. Assign departments to managers from the Employees page.</p>

      <form class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-5 flex gap-3" (ngSubmit)="add()">
        <input name="newName" type="text" placeholder="New department name" maxlength="255" [(ngModel)]="newName" (ngModelChange)="error.set('')"
               class="flex-1 h-10 border border-slate-300 rounded-md px-3 text-sm outline-none focus:border-brand-600" data-testid="new-dept" />
        <button type="submit" class="h-10 px-4 bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold rounded-md cursor-pointer" data-testid="add-dept">Add department</button>
      </form>
      @if (error()) { <div class="mb-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm" data-testid="dept-error">{{ error() }}</div> }

      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr><th class="px-4 py-2">Name</th><th class="px-4 py-2">People</th><th class="px-4 py-2">Managers</th><th class="px-4 py-2"></th></tr>
          </thead>
          <tbody>
            @for (d of departments(); track d.id) {
              <tr class="border-t border-slate-100" data-testid="dept-row">
                <td class="px-4 py-2">
                  @if (editing === d.id) {
                    <input name="rename" type="text" [(ngModel)]="editName" (keydown.enter)="saveRename(d)" class="h-8 border border-slate-300 rounded px-2 text-sm" />
                  } @else { <span class="font-medium">{{ d.name }}</span> }
                </td>
                <td class="px-4 py-2">{{ d.employee_count }}</td>
                <td class="px-4 py-2">{{ d.managers.length ? d.managers.join(', ') : 'No manager (General Manager covers)' }}</td>
                <td class="px-4 py-2 text-right whitespace-nowrap">
                  @if (editing === d.id) {
                    <button type="button" (click)="saveRename(d)" class="text-xs text-brand-700 hover:underline mr-3 cursor-pointer">Save</button>
                    <button type="button" (click)="editing = null" class="text-xs text-slate-500 hover:underline cursor-pointer">Cancel</button>
                  } @else {
                    <button type="button" (click)="startRename(d)" class="text-xs text-slate-600 hover:underline mr-3 cursor-pointer">Rename</button>
                    <button type="button" (click)="remove(d)" class="text-xs text-rose-600 hover:underline cursor-pointer">Delete</button>
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </div>`
})
export class DepartmentsComponent {
  private api = inject(ApiService);

  departments = signal<Department[]>([]);
  error = signal('');
  newName = '';
  editing: number | null = null;
  editName = '';

  constructor() { this.reload(); }

  reload(): void { this.api.departments().subscribe(list => this.departments.set(list)); }

  add(): void {
    if (!this.newName.trim()) { this.error.set('Enter a department name.'); return; }
    this.api.addDepartment(this.newName.trim()).subscribe({
      next: () => { this.newName = ''; this.reload(); },
      error: err => this.error.set(errorText(err.error?.name ? err : err))
    });
  }

  startRename(d: Department): void { this.editing = d.id; this.editName = d.name; this.error.set(''); }

  saveRename(d: Department): void {
    this.api.renameDepartment(d.id, this.editName.trim()).subscribe({
      next: () => { this.editing = null; this.reload(); },
      error: err => this.error.set(errorText(err))
    });
  }

  remove(d: Department): void {
    this.error.set('');
    this.api.deleteDepartment(d.id).subscribe({
      next: () => this.reload(),
      error: err => this.error.set(errorText(err))
    });
  }
}
