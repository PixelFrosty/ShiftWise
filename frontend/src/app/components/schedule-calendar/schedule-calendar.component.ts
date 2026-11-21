import { Component } from '@angular/core';
import { Router } from '@angular/router';
import { MONTHS, addDays, mondayOf, toIso } from '../shared/week-utils';

export interface CalendarDay {
  date: Date;
  label: number;
  inMonth: boolean;
  weekStartIso: string;
}

@Component({
  selector: 'app-schedule-calendar',
  standalone: true,
  imports: [],
  templateUrl: './schedule-calendar.component.html'
})
export class ScheduleCalendarComponent {
  readonly months = MONTHS;
  readonly weekdays = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

  viewYear: number;
  viewMonth: number;
  hoveredWeek: string | null = null;

  constructor(private router: Router) {
    const today = new Date();
    this.viewYear = today.getFullYear();
    this.viewMonth = today.getMonth();
  }

  get years(): number[] {
    const current = new Date().getFullYear();
    return Array.from({ length: 11 }, (_, i) => current - 5 + i);
  }

  get monthLabel(): string {
    return `${MONTHS[this.viewMonth]} ${this.viewYear}`;
  }

  /** Always 6 rows x 7 days (Monday first) so the card never changes height. */
  get days(): CalendarDay[] {
    const first = new Date(this.viewYear, this.viewMonth, 1);
    const gridStart = mondayOf(first);
    return Array.from({ length: 42 }, (_, i) => {
      const date = addDays(gridStart, i);
      return {
        date,
        label: date.getDate(),
        inMonth: date.getMonth() === this.viewMonth,
        weekStartIso: toIso(mondayOf(date))
      };
    });
  }

  shiftMonth(delta: number): void {
    const d = new Date(this.viewYear, this.viewMonth + delta, 1);
    this.viewYear = d.getFullYear();
    this.viewMonth = d.getMonth();
  }

  onMonthChange(event: Event): void {
    this.viewMonth = +(event.target as HTMLSelectElement).value;
  }

  onYearChange(event: Event): void {
    this.viewYear = +(event.target as HTMLSelectElement).value;
  }

  openWeek(day: CalendarDay): void {
    this.router.navigate(['/schedules/week', day.weekStartIso]);
  }
}
