import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, TimeOff } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-time-off',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="max-w-4xl mx-auto">
      <h1 class="text-2xl font-bold text-slate-900">Time Off</h1>
      <p class="text-sm text-slate-500 mb-4">
        {{ isStaff() ? 'Review requests from your employees, and request time off for yourself.' : 'Request time off and see how your requests are doing.' }}
      </p>

      <form class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-5" (ngSubmit)="submit()">
        <h2 class="font-bold text-slate-800 mb-3">New request</h2>
        <div class="grid sm:grid-cols-4 gap-3">
          <div><label for="from" class="block text-xs font-bold text-slate-600 mb-1">From</label>
            <input id="from" name="from" type="date" [(ngModel)]="start" (ngModelChange)="error.set('')" class="w-full h-10 border border-slate-300 rounded-md px-2 text-sm" /></div>
          <div><label for="to" class="block text-xs font-bold text-slate-600 mb-1">To</label>
            <input id="to" name="to" type="date" [(ngModel)]="end" (ngModelChange)="error.set('')" class="w-full h-10 border border-slate-300 rounded-md px-2 text-sm" /></div>
          <div class="sm:col-span-2"><label for="reason" class="block text-xs font-bold text-slate-600 mb-1">Reason (optional)</label>
            <input id="reason" name="reason" type="text" maxlength="255" [(ngModel)]="reason" class="w-full h-10 border border-slate-300 rounded-md px-3 text-sm" /></div>
        </div>
        @if (error()) { <div class="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm" data-testid="to-error">{{ error() }}</div> }
        <button type="submit" class="mt-3 h-10 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-md cursor-pointer" data-testid="submit-to">Submit request</button>
      </form>

      @if (isStaff()) {
        <h2 class="font-bold text-slate-800 mb-2">Team requests</h2>
        <div class="space-y-2 mb-6">
          @for (r of team(); track r.id) {
            <div class="bg-white rounded-lg border border-slate-200 p-3 flex flex-wrap items-center gap-3" data-testid="team-request">
              <div class="flex-1 min-w-[200px]">
                <div class="font-semibold text-sm">{{ r.employee_name }}</div>
                <div class="text-xs text-slate-500">{{ range(r) }}{{ r.reason ? ' · ' + r.reason : '' }}</div>
              </div>
              <span [class]="badge(r.status)">{{ r.status === 'denied' ? 'rejected' : r.status }}</span>
              @if (r.status === 'pending') {
                <button type="button" (click)="decide(r, 'approved')" class="px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold cursor-pointer" data-testid="approve">Approve</button>
                <button type="button" (click)="decide(r, 'denied')" class="px-3 py-1.5 rounded-md border border-slate-300 hover:bg-slate-50 text-xs font-semibold cursor-pointer" data-testid="reject">Reject</button>
              }
            </div>
          } @empty {
            <div class="bg-white rounded-lg border border-slate-200 p-6 text-center text-slate-500 text-sm">No requests from your team.</div>
          }
        </div>
        <h2 class="font-bold text-slate-800 mb-2">My requests</h2>
      }
      <div class="space-y-2">
        @for (r of mine(); track r.id) {
          <div class="bg-white rounded-lg border border-slate-200 p-3 flex items-center gap-3" data-testid="my-request">
            <div class="flex-1">
              <div class="text-sm font-medium">{{ range(r) }}</div>
              <div class="text-xs text-slate-500">{{ r.reason || 'No reason given' }}</div>
            </div>
            <span [class]="badge(r.status)" data-testid="my-status">{{ r.status === 'denied' ? 'rejected' : r.status }}</span>
            @if (r.status === 'pending') {
              <button type="button" (click)="withdraw(r)" class="text-xs text-rose-600 hover:underline cursor-pointer">Withdraw</button>
            }
          </div>
        } @empty {
          <div class="bg-white rounded-lg border border-slate-200 p-6 text-center text-slate-500 text-sm">You haven't requested any time off.</div>
        }
      </div>
    </div>`
})
export class TimeOffComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  isStaff = computed(() => this.auth.role === 'ceo' || this.auth.role === 'manager');
  all = signal<TimeOff[]>([]);
  mine = computed(() => this.all().filter(r => r.employee === this.auth.me()?.profile?.id));
  team = computed(() => this.all().filter(r => r.employee !== this.auth.me()?.profile?.id));
  error = signal('');
  start = '';
  end = '';
  reason = '';

  constructor() { this.reload(); }

  reload(): void { this.api.timeOff().subscribe(list => this.all.set(list)); }

  range(r: TimeOff): string { return r.start_date === r.end_date ? r.start_date : `${r.start_date} to ${r.end_date}`; }

  badge(status: string): string {
    const base = 'px-2 py-0.5 rounded-full text-xs font-semibold capitalize ';
    return base + (status === 'approved' ? 'bg-emerald-100 text-emerald-800' : status === 'denied' ? 'bg-rose-100 text-rose-800' : 'bg-amber-100 text-amber-800');
  }

  submit(): void {
    if (!this.start || !this.end) { this.error.set('Choose a start and end date.'); return; }
    this.api.requestTimeOff({ start_date: this.start, end_date: this.end, reason: this.reason.trim() }).subscribe({
      next: () => { this.start = this.end = this.reason = ''; this.reload(); },
      error: err => this.error.set(errorText(err))
    });
  }

  decide(r: TimeOff, status: 'approved' | 'denied'): void {
    this.api.decideTimeOff(r.id, status).subscribe({ next: () => this.reload(), error: err => this.error.set(errorText(err)) });
  }

  withdraw(r: TimeOff): void {
    this.api.withdrawTimeOff(r.id).subscribe({ next: () => this.reload(), error: err => this.error.set(errorText(err)) });
  }
}
