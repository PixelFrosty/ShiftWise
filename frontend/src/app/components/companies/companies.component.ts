import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService, Department } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Me, errorText, roleLabel } from '../../core/models';

@Component({
  selector: 'app-companies',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <div class="max-w-4xl mx-auto py-6">
      <div class="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h1 class="text-2xl font-bold text-slate-900">Company Management</h1>
          <p class="text-sm text-slate-500 mt-1">Manage the company you are in, view departments, and adjust operating hours.</p>
        </div>
        <div class="flex items-center gap-2">
          <a routerLink="/join-company" class="px-4 py-2 border border-brand-600 text-brand-700 hover:bg-brand-50 rounded-lg text-sm font-semibold transition no-underline">
            + Join / Create Company
          </a>
        </div>
      </div>

      @if (statusMessage()) {
        <div class="mb-4 p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-sm font-medium">
          {{ statusMessage() }}
        </div>
      }
      @if (errorMessage()) {
        <div class="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-sm font-medium">
          {{ errorMessage() }}
        </div>
      }

      @if (currentCompany(); as company) {
        <!-- Main Company Card -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
          <div class="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-100">
            <div>
              <span class="text-xs uppercase tracking-wider font-bold text-brand-600 bg-brand-50 px-2.5 py-1 rounded-full">Active Organization</span>
              <h2 class="text-2xl font-bold text-slate-900 mt-2">{{ company.name }}</h2>
              <p class="text-xs text-slate-400 mt-0.5">Company ID: #{{ company.id }}</p>
            </div>
            <div class="text-right">
              <span class="text-xs text-slate-500 block uppercase font-semibold">Your Role</span>
              <span class="inline-block mt-1 px-3 py-1 rounded-full text-xs font-semibold"
                    [class]="role() === 'ceo' ? 'bg-purple-100 text-purple-800' : role() === 'manager' ? 'bg-blue-100 text-blue-800' : 'bg-brand-100 text-brand-800'">
                {{ roleText() }}
              </span>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-3 gap-6 pt-5">
            <div>
              <span class="text-xs font-bold text-slate-500 uppercase block mb-1">Assigned Department</span>
              <span class="text-sm font-semibold text-slate-800">{{ departmentName() }}</span>
            </div>
            <div>
              <span class="text-xs font-bold text-slate-500 uppercase block mb-1">Operating Hours</span>
              <span class="text-sm font-semibold text-slate-800">{{ company.open_time || '08:00:00' }} – {{ company.close_time || '18:00:00' }}</span>
            </div>
            <div>
              <span class="text-xs font-bold text-slate-500 uppercase block mb-1">Company Access</span>
              <span class="text-sm text-slate-700">Full Schedule Access</span>
            </div>
          </div>
        </div>

        <!-- Operating Hours Form (CEO only) -->
        @if (role() === 'ceo') {
          <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
            <h3 class="text-lg font-bold text-slate-900 mb-2">Update Operating Hours</h3>
            <p class="text-xs text-slate-500 mb-4">Shifts scheduled outside these hours will trigger schedule warnings.</p>
            <form (ngSubmit)="saveHours()" class="flex flex-wrap items-end gap-4">
              <div>
                <label for="openTime" class="block text-xs font-bold text-slate-600 uppercase mb-1">Open Time</label>
                <input id="openTime" name="openTime" type="time" [(ngModel)]="openTime" class="h-10 border border-slate-300 rounded-lg px-3 text-sm" />
              </div>
              <div>
                <label for="closeTime" class="block text-xs font-bold text-slate-600 uppercase mb-1">Close Time</label>
                <input id="closeTime" name="closeTime" type="time" [(ngModel)]="closeTime" class="h-10 border border-slate-300 rounded-lg px-3 text-sm" />
              </div>
              <button type="submit" [disabled]="savingHours" class="h-10 px-5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-semibold cursor-pointer disabled:opacity-50">
                {{ savingHours ? 'Saving…' : 'Update Hours' }}
              </button>
            </form>
          </div>
        }

        <!-- Departments List in this Company -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold text-slate-900">Departments ({{ departments().length }})</h3>
            @if (role() === 'ceo') {
              <a routerLink="/departments" class="text-xs font-semibold text-brand-600 hover:text-brand-800 hover:underline">
                Manage Departments &rarr;
              </a>
            }
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            @for (dept of departments(); track dept.id) {
              <div class="p-3 rounded-lg border border-slate-100 bg-slate-50/50 flex items-center justify-between">
                <span class="text-sm font-medium text-slate-800">{{ dept.name }}</span>
                <span class="text-xs text-slate-500">{{ dept.employee_count }} staff</span>
              </div>
            } @empty {
              <p class="text-sm text-slate-500 col-span-full">No departments loaded.</p>
            }
          </div>
        </div>

        <!-- Danger Zone (Leave company if not CEO) -->
        @if (role() !== 'ceo') {
          <div class="bg-white rounded-xl border border-rose-200 shadow-sm p-6">
            <h3 class="text-lg font-bold text-slate-900 mb-1">Leave Company</h3>
            <p class="text-sm text-slate-500 mb-4">You will forfeit access to {{ company.name }} schedules and assignments.</p>
            @if (!confirmingLeave) {
              <button type="button" (click)="confirmingLeave = true" class="px-4 py-2 border border-rose-300 text-rose-700 hover:bg-rose-50 text-sm font-semibold rounded-lg cursor-pointer">
                Leave {{ company.name }}
              </button>
            } @else {
              <div class="flex items-center gap-3">
                <span class="text-sm font-medium text-slate-800">Are you sure?</span>
                <button type="button" (click)="leaveCompany()" class="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold rounded-lg cursor-pointer">
                  Yes, Leave Company
                </button>
                <button type="button" (click)="confirmingLeave = false" class="px-4 py-2 border border-slate-300 text-sm font-semibold rounded-lg cursor-pointer">
                  Cancel
                </button>
              </div>
            }
          </div>
        }
      } @else {
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-8 text-center">
          <h2 class="text-xl font-bold text-slate-900 mb-2">No Active Company</h2>
          <p class="text-sm text-slate-500 mb-6">You are not currently associated with any company.</p>
          <a routerLink="/join-company" class="inline-block px-5 py-2.5 bg-brand-600 hover:bg-brand-700 text-white font-semibold rounded-lg text-sm no-underline shadow-sm">
            Join or Create a Company
          </a>
        </div>
      }
    </div>`
})
export class CompaniesComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private router = inject(Router);

  me = this.auth.me;
  role = computed(() => this.me()?.profile?.role);
  roleText = computed(() => roleLabel(this.role()));
  currentCompany = computed(() => this.me()?.profile?.company);
  departmentName = computed(() => this.me()?.profile?.department?.name || 'General');

  openTime = '08:00';
  closeTime = '18:00';
  savingHours = false;
  confirmingLeave = false;
  statusMessage = signal('');
  errorMessage = signal('');

  departments = signal<Department[]>([]);

  constructor() {
    this.api.departments().subscribe({
      next: depts => this.departments.set(depts),
      error: () => {}
    });

    const c = this.currentCompany();
    if (c) {
      if (c.open_time) this.openTime = c.open_time.slice(0, 5);
      if (c.close_time) this.closeTime = c.close_time.slice(0, 5);
    }
  }

  saveHours(): void {
    this.savingHours = true;
    this.statusMessage.set('');
    this.errorMessage.set('');
    const openWithSeconds = this.openTime.length === 5 ? `${this.openTime}:00` : this.openTime;
    const closeWithSeconds = this.closeTime.length === 5 ? `${this.closeTime}:00` : this.closeTime;

    this.api.setHours(openWithSeconds, closeWithSeconds).subscribe({
      next: () => {
        this.savingHours = false;
        this.statusMessage.set('Company operating hours updated successfully.');
        const currentMe = this.me();
        if (currentMe && currentMe.profile) {
          this.auth.me.set({
            ...currentMe,
            profile: {
              ...currentMe.profile,
              company: {
                ...currentMe.profile.company,
                open_time: openWithSeconds,
                close_time: closeWithSeconds
              }
            }
          });
        }
      },
      error: err => {
        this.savingHours = false;
        this.errorMessage.set(errorText(err));
      }
    });
  }

  leaveCompany(): void {
    this.api.leaveCompany().subscribe({
      next: me => {
        this.auth.me.set(me);
        this.router.navigate(['/join-company']);
      },
      error: err => {
        this.confirmingLeave = false;
        this.errorMessage.set(errorText(err));
      }
    });
  }
}
