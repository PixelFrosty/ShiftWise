import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { ApiService, AppNotification } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-notifications',
  standalone: true,
  imports: [DatePipe],
  template: `
    <div class="max-w-2xl mx-auto">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold text-slate-900">Notifications</h1>
        @if (items().length) {
          <button type="button" (click)="readAll()" class="text-sm text-emerald-700 hover:underline cursor-pointer" data-testid="read-all">Mark all as read</button>
        }
      </div>
      @if (error()) { <div class="mb-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm">{{ error() }}</div> }
      @if (loaded() && !items().length) {
        <div class="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500">You're all caught up.</div>
      }
      <div class="space-y-2">
        @for (n of items(); track n.id) {
          <div class="bg-white rounded-lg border p-4 flex items-start gap-3" [class.border-emerald-300]="!n.is_read" [class.border-slate-200]="n.is_read" data-testid="notification">
            <div class="flex-1">
              <div class="text-sm text-slate-800" [class.font-semibold]="!n.is_read">{{ n.message }}</div>
              <div class="text-xs text-slate-400 mt-0.5">{{ n.created_at | date:'medium' }}</div>
              @if (n.transfer_request; as t) {
                @if (n.kind === 'transfer_request' && t.status === 'pending') {
                  <div class="mt-2 flex gap-2">
                    <button type="button" (click)="decide(n, t.id, true)" class="px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold cursor-pointer" data-testid="accept">Accept</button>
                    <button type="button" (click)="decide(n, t.id, false)" class="px-3 py-1.5 rounded-md border border-slate-300 hover:bg-slate-50 text-xs font-semibold cursor-pointer" data-testid="decline">Decline</button>
                  </div>
                } @else if (n.kind === 'transfer_request') {
                  <div class="mt-1 text-xs text-slate-500">This request was {{ t.status }}.</div>
                }
              }
              @if (n.shift_request; as sr) {
                @if (sr.status === 'pending' && n.kind === 'shift_request' && (sr.kind !== 'offer' || !n.is_read)) {
                  <div class="mt-2 flex gap-2">
                    <button type="button" (click)="decideShift(n, sr.id, true)" class="px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold cursor-pointer" data-testid="accept-shift">Accept</button>
                    <button type="button" (click)="decideShift(n, sr.id, false)" class="px-3 py-1.5 rounded-md border border-slate-300 hover:bg-slate-50 text-xs font-semibold cursor-pointer" data-testid="decline-shift">Decline</button>
                  </div>
                } @else if (n.kind === 'shift_request' && sr.kind === 'offer') {
                  <div class="mt-1 text-xs text-slate-500" data-testid="offer-state">{{ sr.status === 'accepted' ? 'Someone already took this shift.' : sr.status === 'pending' ? 'You passed on this offer.' : 'This offer was withdrawn.' }}</div>
                } @else if (n.kind === 'shift_request') {
                  <div class="mt-1 text-xs text-slate-500">This request was {{ sr.status }}.</div>
                }
              }
            </div>
            @if (!n.is_read) {
              <button type="button" (click)="read(n)" class="text-xs text-slate-500 hover:text-slate-800 cursor-pointer">Mark read</button>
            }
          </div>
        }
      </div>
    </div>`
})
export class NotificationsComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  items = signal<AppNotification[]>([]);
  loaded = signal(false);
  error = signal('');

  constructor() { this.load(); }

  private load(): void {
    this.api.notifications().subscribe({
      next: list => { this.items.set(list); this.loaded.set(true); },
      error: err => { this.loaded.set(true); this.error.set(errorText(err)); }
    });
  }

  read(n: AppNotification): void {
    this.api.markRead(n.id).subscribe(r => {
      this.items.update(list => list.map(x => x.id === n.id ? { ...x, is_read: true } : x));
      this.auth.setUnread(r.unread_notifications);
    });
  }

  readAll(): void {
    this.api.markAllRead().subscribe(r => {
      this.items.update(list => list.map(x => ({ ...x, is_read: true })));
      this.auth.setUnread(r.unread_notifications);
    });
  }

  decideShift(n: AppNotification, requestId: number, accept: boolean): void {
    this.error.set('');
    const call = accept ? this.api.acceptShiftRequest(requestId) : this.api.declineShiftRequest(requestId);
    call.subscribe({
      next: () => { this.read(n); this.load(); },
      error: err => { this.error.set(errorText(err)); this.load(); }
    });
  }

  decide(n: AppNotification, requestId: number, accept: boolean): void {
    this.error.set('');
    const call = accept ? this.api.acceptTransfer(requestId) : this.api.rejectTransfer(requestId);
    call.subscribe({
      next: () => { this.read(n); this.load(); },
      error: err => { this.error.set(errorText(err)); this.load(); }
    });
  }
}
