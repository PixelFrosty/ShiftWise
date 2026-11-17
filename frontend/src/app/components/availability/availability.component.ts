import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Slot } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-availability',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="max-w-3xl mx-auto">
      <h1 class="text-2xl font-bold text-slate-900">My Availability</h1>
      <p class="text-sm text-slate-500 mb-4">Days you haven't changed count as available all day. Add hours to limit a day, or tick "Not available" to mark the whole day off. These repeat every week.</p>

      <form class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 mb-5" (ngSubmit)="add()">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label for="day" class="block text-xs font-bold text-slate-600 mb-1">Day</label>
            <select id="day" name="day" [(ngModel)]="day" class="h-10 border border-slate-300 rounded-md px-2 text-sm bg-white">
              @for (d of days; track $index) { <option [ngValue]="$index">{{ d }}</option> }
            </select>
          </div>
          <div>
            <label for="from" class="block text-xs font-bold text-slate-600 mb-1">From</label>
            <input id="from" name="from" type="time" [(ngModel)]="from" class="h-10 border border-slate-300 rounded-md px-2 text-sm" />
          </div>
          <div>
            <label for="to" class="block text-xs font-bold text-slate-600 mb-1">To</label>
            <input id="to" name="to" type="time" [(ngModel)]="to" class="h-10 border border-slate-300 rounded-md px-2 text-sm" />
          </div>
          <button type="submit" class="h-10 px-4 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold rounded-md cursor-pointer" data-testid="add-slot">Add</button>
        </div>
        @if (error()) { <div class="mt-3 p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm" data-testid="slot-error">{{ error() }}</div> }
      </form>

      <div class="bg-white rounded-xl border border-slate-200 shadow-sm divide-y divide-slate-100">
        @for (d of days; track $index) {
          <div class="flex items-start gap-4 px-4 py-3">
            <div class="w-28 text-sm font-semibold text-slate-700 pt-1">{{ d }}</div>
            <label class="flex items-center gap-1.5 text-xs text-slate-600 pt-1.5 w-36 cursor-pointer">
              <input type="checkbox" [checked]="isOff($index)" (change)="toggleOff($index)" [attr.data-testid]="'off-' + $index" /> Not available
            </label>
            <div class="flex-1 flex flex-wrap gap-2">
              @if (isOff($index)) {
                <span class="text-sm text-slate-400 pt-1" data-testid="day-off">Not available all day</span>
              } @else {
              @for (s of byDay()[$index]; track s.id) {
                <span class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-sm text-emerald-900" data-testid="slot">
                  {{ s.start_time.slice(0, 5) }} – {{ s.end_time.slice(0, 5) }}
                  <button type="button" (click)="remove(s)" class="text-emerald-700 hover:text-rose-600 cursor-pointer" [attr.aria-label]="'Remove ' + d + ' slot'">&times;</button>
                </span>
              } @empty {
                <span class="text-sm text-emerald-700 pt-1" data-testid="day-open">Available all day</span>
              }
              }
            </div>
          </div>
        }
      </div>
    </div>`
})
export class AvailabilityComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  readonly days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  slots = signal<Slot[]>([]);
  error = signal('');
  day = 0;
  from = '09:00';
  to = '17:00';

  /** Only my own slots (managers' lists would otherwise include their team's). */
  byDay = computed(() => {
    const mine = this.auth.me()?.profile?.id;
    const out: Slot[][] = this.days.map(() => []);
    for (const s of this.slots()) { if (s.employee === mine) { out[s.day_of_week].push(s); } }
    return out;
  });

  off = signal<number[]>([]);

  constructor() {
    this.reload();
    this.api.unavailableDays().subscribe(r => this.off.set(r.unavailable_days));
  }

  reload(): void { this.api.availability().subscribe(list => this.slots.set(list)); }

  isOff(day: number): boolean { return this.off().includes(day); }

  toggleOff(day: number): void {
    const next = this.isOff(day) ? this.off().filter(d => d !== day) : [...this.off(), day].sort();
    this.error.set('');
    this.api.setUnavailableDays(next).subscribe({
      next: r => this.off.set(r.unavailable_days),
      error: err => this.error.set(errorText(err))
    });
  }

  add(): void {
    const me = this.auth.me()?.profile;
    if (!me) { return; }
    if (this.isOff(Number(this.day))) { this.error.set(`${this.days[Number(this.day)]} is marked "Not available". Untick it first to add hours.`); return; }
    if (!this.from || !this.to) { this.error.set('Choose a start and end time.'); return; }
    this.error.set('');
    this.api.addSlot({ employee: me.id, day_of_week: Number(this.day), start_time: this.from, end_time: this.to }).subscribe({
      next: () => this.reload(),
      error: err => this.error.set(errorText(err))
    });
  }

  remove(s: Slot): void {
    this.api.removeSlot(s.id).subscribe({ next: () => this.reload(), error: err => this.error.set(errorText(err)) });
  }
}
