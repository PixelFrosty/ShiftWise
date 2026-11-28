import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText, roleLabel } from '../../core/models';

@Component({
  selector: 'app-account',
  standalone: true,
  template: `
    <div class="max-w-4xl mx-auto space-y-6">
      <!-- Page Header -->
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
        <div class="flex items-center gap-4">
          <img src="/user.png" alt="" class="w-12 h-12 rounded-full object-cover border border-slate-200 bg-slate-50" />
          <div>
            <h1 class="text-2xl font-bold text-slate-900">My Account</h1>
            <p class="text-sm text-slate-500 mt-0.5">Manage your profile details and company membership</p>
          </div>
        </div>
        @if (me()?.profile; as p) {
          <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold"
                [class]="p.role === 'ceo' ? 'bg-purple-100 text-purple-800' : p.role === 'manager' ? 'bg-blue-100 text-blue-800' : 'bg-brand-100 text-brand-800'">
            {{ roleText() }}
          </span>
        }
      </div>

      @if (me(); as m) {
        <!-- Profile & Organization Card -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="px-6 py-4 bg-slate-50 border-b border-slate-200">
            <h2 class="text-base font-bold text-slate-900">Profile &amp; Organization</h2>
            <p class="text-xs text-slate-500 mt-0.5">Personal and role details tied to your ShiftWise account</p>
          </div>

          <div class="p-6">
            <dl class="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div class="p-4 rounded-lg border border-slate-100 bg-slate-50/50">
                <dt class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Name</dt>
                <dd class="text-sm font-semibold text-slate-900">{{ m.first_name }} {{ m.last_name }}</dd>
              </div>

              <div class="p-4 rounded-lg border border-slate-100 bg-slate-50/50">
                <dt class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Email</dt>
                <dd class="text-sm font-medium text-slate-800 break-all">{{ m.email }}</dd>
              </div>

              @if (m.profile; as p) {
                <div class="p-4 rounded-lg border border-slate-100 bg-slate-50/50">
                  <dt class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Company</dt>
                  <dd class="text-sm font-semibold text-slate-900" data-testid="company">{{ p.company.name }}</dd>
                </div>

                <div class="p-4 rounded-lg border border-slate-100 bg-slate-50/50">
                  <dt class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Role</dt>
                  <dd>
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold"
                          [class]="p.role === 'ceo' ? 'bg-purple-100 text-purple-800' : p.role === 'manager' ? 'bg-blue-100 text-blue-800' : 'bg-brand-100 text-brand-800'"
                          data-testid="role">
                      {{ roleText() }}
                    </span>
                  </dd>
                </div>

                <div class="p-4 rounded-lg border border-slate-100 bg-slate-50/50">
                  <dt class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Department</dt>
                  <dd>
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800">
                      {{ p.department.name }}
                    </span>
                  </dd>
                </div>

                @if (p.role === 'manager') {
                  <div class="p-4 rounded-lg border border-slate-100 bg-slate-50/50">
                    <dt class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">You manage</dt>
                    <dd class="text-sm font-medium text-slate-800">{{ managed() }}</dd>
                  </div>
                }
              }
            </dl>

            @if (!m.profile) {
              <div class="mt-5 p-4 rounded-lg bg-brand-50 border border-brand-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <p class="text-sm text-slate-700">
                  You are not in a company.
                  <a href="/join-company" class="text-brand-700 font-semibold underline hover:text-brand-800" (click)="goJoin($event)">Join one with a code</a>.
                </p>
              </div>
            }
          </div>
        </div>

        @if (m.profile; as p) {
          <!-- Leave Company Card -->
          <div class="bg-white rounded-xl border border-rose-200 shadow-sm p-6">
            <h2 class="text-lg font-bold text-slate-900 mb-1">Leave company</h2>
            @if (p.role === 'ceo') {
              <p class="text-sm text-slate-500">The General Manager can't leave the company in this version.</p>
              <button type="button" disabled class="mt-4 px-4 py-2 rounded-lg bg-slate-100 border border-slate-200 text-slate-400 text-sm font-medium cursor-not-allowed">Leave company</button>
            } @else {
              <p class="text-sm text-slate-500">You'll lose access to this company's schedule. Your account stays, and you can join another company with a code.</p>
              @if (error()) { <div class="mt-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-sm font-medium">{{ error() }}</div> }
              @if (!confirming()) {
                <button type="button" (click)="confirming.set(true)" class="mt-4 px-4 py-2 rounded-lg border border-rose-300 text-rose-700 hover:bg-rose-50 text-sm font-semibold transition cursor-pointer" data-testid="leave">Leave company</button>
              } @else {
                <div class="mt-4 p-3 rounded-lg bg-rose-50/60 border border-rose-200 flex flex-wrap gap-3 items-center">
                  <span class="text-sm font-medium text-slate-800">Are you sure?</span>
                  <button type="button" (click)="leave()" class="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-sm font-semibold shadow-sm transition cursor-pointer" data-testid="leave-confirm">Yes, leave</button>
                  <button type="button" (click)="confirming.set(false)" class="px-4 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium transition cursor-pointer">Cancel</button>
                </div>
              }
            }
          </div>
        }
      }
    </div>`
})
export class AccountComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private router = inject(Router);

  me = this.auth.me;
  roleText = computed(() => roleLabel(this.me()?.profile?.role));
  managed = computed(() => (this.me()?.profile?.managed_departments ?? []).map(d => d.name).join(', ') || 'No departments yet');
  confirming = signal(false);
  error = signal('');

  goJoin(event: Event): void {
    event.preventDefault();
    this.router.navigate(['/join-company']);
  }

  leave(): void {
    this.api.leaveCompany().subscribe({
      next: me => { this.auth.me.set(me); this.router.navigate(['/join-company']); },
      error: err => { this.confirming.set(false); this.error.set(errorText(err)); }
    });
  }
}
