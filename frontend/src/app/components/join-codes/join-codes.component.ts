import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Department, JoinCode } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-join-codes',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="max-w-4xl mx-auto">
      <h1 class="text-2xl font-bold text-slate-900">Join Codes</h1>
      <p class="text-sm text-slate-500 mb-4">
        Make a single-use code and send it to someone. They enter it when they sign up (or from "Join a company") to get into your company.
        {{ isCeo() ? 'As General Manager you can make manager and employee codes.' : 'You can make employee codes for the departments you manage.' }}
      </p>

      <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-5">
        <div class="flex flex-wrap items-end gap-3">
          @if (isCeo()) {
            <div>
              <label for="role" class="block text-xs font-bold text-slate-600 mb-1">Code for a</label>
              <select id="role" [(ngModel)]="role" name="role" class="h-10 border border-slate-300 rounded-md px-2 text-sm bg-white">
                <option value="employee">Employee</option>
                <option value="manager">Manager</option>
              </select>
            </div>
          }
          @if (role === 'employee') {
            <div>
              <label for="dept" class="block text-xs font-bold text-slate-600 mb-1">Department</label>
              <select id="dept" [(ngModel)]="deptId" name="dept" class="h-10 border border-slate-300 rounded-md px-2 text-sm bg-white">
                @for (d of choices(); track d.id) { <option [ngValue]="d.id">{{ d.name }}</option> }
              </select>
            </div>
          } @else {
            <fieldset>
              <legend class="block text-xs font-bold text-slate-600 mb-1">Departments this manager will run</legend>
              <div class="flex flex-wrap gap-3">
                @for (d of choices(); track d.id) {
                  <label class="flex items-center gap-1.5 text-sm"><input type="checkbox" [checked]="picked().includes(d.id)" (change)="toggle(d.id)" /> {{ d.name }}</label>
                }
              </div>
            </fieldset>
          }
          <button type="button" (click)="create()" class="h-10 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-md cursor-pointer" data-testid="make-code">Create code</button>
        </div>
        @if (error()) { <div class="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm">{{ error() }}</div> }
        @if (fresh(); as f) {
          <div class="mt-3 p-3 bg-emerald-50 border border-emerald-200 rounded-md flex items-center gap-3">
            <span class="text-sm text-emerald-900">New {{ f.role }} code:</span>
            <code class="text-lg font-bold tracking-widest text-emerald-900" data-testid="new-code">{{ f.code }}</code>
            <button type="button" (click)="copy(f.code)" class="text-xs px-2 py-1 rounded border border-emerald-300 hover:bg-emerald-100 cursor-pointer">{{ copied() ? 'Copied' : 'Copy' }}</button>
          </div>
        }
      </div>

      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-x-auto">
        <table class="w-full text-sm">
          <thead class="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr><th class="px-4 py-2">Code</th><th class="px-4 py-2">For</th><th class="px-4 py-2">Departments</th><th class="px-4 py-2">Status</th><th class="px-4 py-2"></th></tr>
          </thead>
          <tbody>
            @for (c of codes(); track c.id) {
              <tr class="border-t border-slate-100" data-testid="code-row">
                <td class="px-4 py-2 font-mono tracking-wider">{{ c.code }}</td>
                <td class="px-4 py-2 capitalize">{{ c.role }}</td>
                <td class="px-4 py-2">{{ names(c) }}</td>
                <td class="px-4 py-2">
                  @if (c.status === 'used') { <span class="text-slate-500">Used by {{ c.used_by }}</span> }
                  @else { <span class="text-emerald-700 font-medium">Unused</span> }
                </td>
                <td class="px-4 py-2 text-right whitespace-nowrap">
                  @if (c.status === 'unused') {
                    <button type="button" (click)="copy(c.code)" class="text-xs text-slate-600 hover:underline mr-3 cursor-pointer">Copy</button>
                    <button type="button" (click)="revoke(c)" class="text-xs text-rose-600 hover:underline cursor-pointer">Revoke</button>
                  }
                </td>
              </tr>
            } @empty {
              <tr><td colspan="5" class="px-4 py-6 text-center text-slate-500">No codes yet.</td></tr>
            }
          </tbody>
        </table>
      </div>
    </div>`
})
export class JoinCodesComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  isCeo = computed(() => this.auth.role === 'ceo');
  departments = signal<Department[]>([]);
  codes = signal<JoinCode[]>([]);
  fresh = signal<JoinCode | null>(null);
  error = signal('');
  copied = signal(false);

  role: 'employee' | 'manager' = 'employee';
  deptId: number | null = null;
  picked = signal<number[]>([]);

  /** Departments this person may make codes for. */
  choices = computed(() => {
    const allowed = this.auth.me()?.profile?.managed_departments.map(d => d.id) ?? [];
    return this.departments().filter(d => allowed.includes(d.id));
  });

  constructor() {
    this.api.departments().subscribe(list => {
      this.departments.set(list);
      this.deptId = this.choices()[0]?.id ?? null;
    });
    this.reload();
  }

  reload(): void { this.api.codes().subscribe(list => this.codes.set(list)); }

  toggle(id: number): void {
    this.picked.update(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]);
  }

  names(c: JoinCode): string { return c.departments.map(d => d.name).join(', '); }

  create(): void {
    this.error.set('');
    const ids = this.role === 'employee' ? (this.deptId ? [this.deptId] : []) : this.picked();
    if (!ids.length) { this.error.set('Choose a department first.'); return; }
    this.api.createCode(this.role, ids).subscribe({
      next: code => { this.fresh.set(code); this.copied.set(false); this.reload(); },
      error: err => this.error.set(errorText(err))
    });
  }

  revoke(c: JoinCode): void {
    this.api.revokeCode(c.id).subscribe({
      next: () => { if (this.fresh()?.id === c.id) { this.fresh.set(null); } this.reload(); },
      error: err => this.error.set(errorText(err))
    });
  }

  copy(code: string): void {
    try { navigator.clipboard.writeText(code).then(() => this.copied.set(true), () => undefined); } catch { /* clipboard unavailable */ }
  }
}
