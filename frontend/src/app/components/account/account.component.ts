import { Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText, roleLabel } from '../../core/models';

@Component({
  selector: 'app-account',
  standalone: true,
  template: `
    <div class="max-w-xl mx-auto">
      <h1 class="text-2xl font-bold text-slate-900 mb-4">My Account</h1>
      @if (me(); as m) {
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-3">
          <div><div class="text-xs uppercase tracking-wide text-slate-500">Name</div><div class="font-semibold">{{ m.first_name }} {{ m.last_name }}</div></div>
          <div><div class="text-xs uppercase tracking-wide text-slate-500">Email</div><div>{{ m.email }}</div></div>
          @if (m.profile; as p) {
            <div><div class="text-xs uppercase tracking-wide text-slate-500">Company</div><div data-testid="company">{{ p.company.name }}</div></div>
            <div><div class="text-xs uppercase tracking-wide text-slate-500">Role</div><div data-testid="role">{{ roleText() }}</div></div>
            <div><div class="text-xs uppercase tracking-wide text-slate-500">Department</div><div>{{ p.department.name }}</div></div>
            @if (p.role === 'manager') {
              <div><div class="text-xs uppercase tracking-wide text-slate-500">You manage</div>
                <div>{{ managed() }}</div></div>
            }
          } @else {
            <p class="text-sm text-slate-600">You are not in a company. <a href="/join-company" class="text-emerald-700 underline" (click)="goJoin($event)">Join one with a code</a>.</p>
          }
        </div>

        @if (m.profile; as p) {
          <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mt-4">
            <h2 class="font-bold text-slate-900 mb-1">Leave company</h2>
            @if (p.role === 'ceo') {
              <p class="text-sm text-slate-500">The General Manager can't leave the company in this version.</p>
              <button type="button" disabled class="mt-3 px-4 py-2 rounded-md bg-slate-200 text-slate-500 text-sm font-medium cursor-not-allowed">Leave company</button>
            } @else {
              <p class="text-sm text-slate-500">You'll lose access to this company's schedule. Your account stays, and you can join another company with a code.</p>
              @if (error()) { <div class="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm">{{ error() }}</div> }
              @if (!confirming()) {
                <button type="button" (click)="confirming.set(true)" class="mt-3 px-4 py-2 rounded-md border border-rose-300 text-rose-700 hover:bg-rose-50 text-sm font-medium cursor-pointer" data-testid="leave">Leave company</button>
              } @else {
                <div class="mt-3 flex gap-2 items-center">
                  <span class="text-sm text-slate-700">Are you sure?</span>
                  <button type="button" (click)="leave()" class="px-4 py-2 rounded-md bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium cursor-pointer" data-testid="leave-confirm">Yes, leave</button>
                  <button type="button" (click)="confirming.set(false)" class="px-4 py-2 rounded-md border border-slate-300 text-sm cursor-pointer">Cancel</button>
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
