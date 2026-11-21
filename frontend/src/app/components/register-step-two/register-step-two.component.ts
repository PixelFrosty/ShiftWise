import { Component, ElementRef, HostListener, inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { RegistrationService } from '../../core/registration.service';
import { AuthService } from '../../core/auth.service';

export interface CalendarCell {
  day: number;
  empty: boolean;
}

@Component({
  selector: 'app-register-step-two',
  standalone: true,
  imports: [RouterLink, FormsModule],
  templateUrl: './register-step-two.component.html',
  styleUrl: './register-step-two.component.scss'
})
export class RegisterStepTwoComponent {
  firstName: string = '';
  lastName: string = '';
  dob: string = '';
  errorMessage: string | null = null;
  isSubmitting: boolean = false;

  // Calendar picker state
  isCalendarOpen: boolean = false;
  calYear: number = 2000;
  calMonth: number = 0; // 0 = Jan ... 11 = Dec
  availableYears: number[] = [];
  readonly monthNames: string[] = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  calendarCells: CalendarCell[] = [];

  private registration = inject(RegistrationService);
  private auth = inject(AuthService);
  private router = inject(Router);
  private elementRef = inject(ElementRef);

  constructor() {
    const currentYear = new Date().getFullYear();
    for (let y = currentYear; y >= 1920; y--) {
      this.availableYears.push(y);
    }
    // Default calendar view to ~25 years ago
    this.calYear = Math.max(1920, currentYear - 25);
    this.calMonth = 0;
    this.updateCalendarDays();

    if (!this.registration.getDraft()) {
      this.router.navigate(['/register']);
    }
  }

  openCalendar(): void {
    if (this.dob) {
      const parts = this.dob.split('-');
      if (parts.length === 3) {
        const y = parseInt(parts[0], 10);
        const m = parseInt(parts[1], 10) - 1;
        if (!isNaN(y) && !isNaN(m)) {
          this.calYear = y;
          this.calMonth = m;
        }
      }
    }
    this.updateCalendarDays();
    this.isCalendarOpen = true;
  }

  toggleCalendar(event: Event): void {
    event.stopPropagation();
    if (this.isCalendarOpen) {
      this.isCalendarOpen = false;
    } else {
      this.openCalendar();
    }
  }

  closeCalendar(): void {
    this.isCalendarOpen = false;
  }

  setCalMonth(month: any): void {
    this.calMonth = Number(month);
    this.updateCalendarDays();
  }

  setCalYear(year: any): void {
    this.calYear = Number(year);
    this.updateCalendarDays();
  }

  prevMonth(event: Event): void {
    event.stopPropagation();
    if (this.calMonth === 0) {
      this.calMonth = 11;
      this.calYear--;
    } else {
      this.calMonth--;
    }
    this.updateCalendarDays();
  }

  nextMonth(event: Event): void {
    event.stopPropagation();
    if (this.calMonth === 11) {
      this.calMonth = 0;
      this.calYear++;
    } else {
      this.calMonth++;
    }
    this.updateCalendarDays();
  }

  updateCalendarDays(): void {
    const firstDayIndex = new Date(this.calYear, this.calMonth, 1).getDay(); // 0 = Sun
    const daysInMonth = new Date(this.calYear, this.calMonth + 1, 0).getDate();

    const cells: CalendarCell[] = [];
    for (let i = 0; i < firstDayIndex; i++) {
      cells.push({ day: 0, empty: true });
    }
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push({ day: d, empty: false });
    }
    this.calendarCells = cells;
  }

  selectDay(day: number, event: Event): void {
    event.stopPropagation();
    const mm = String(this.calMonth + 1).padStart(2, '0');
    const dd = String(day).padStart(2, '0');
    this.dob = `${this.calYear}-${mm}-${dd}`;
    this.isCalendarOpen = false;
    this.errorMessage = null;
  }

  isSelectedDay(day: number): boolean {
    if (!this.dob) { return false; }
    const mm = String(this.calMonth + 1).padStart(2, '0');
    const dd = String(day).padStart(2, '0');
    return this.dob === `${this.calYear}-${mm}-${dd}`;
  }

  onDobInput(value: string): void {
    this.errorMessage = null;
    const normalized = this.normalizeDate(value);
    if (normalized) {
      this.dob = normalized;
      const parts = normalized.split('-');
      this.calYear = parseInt(parts[0], 10);
      this.calMonth = parseInt(parts[1], 10) - 1;
      this.updateCalendarDays();
    }
  }

  normalizeDate(val: string): string | null {
    if (!val) { return null; }
    const trimmed = val.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
      return trimmed;
    }
    const m1 = /^(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})$/.exec(trimmed);
    if (m1) {
      const month = m1[1].padStart(2, '0');
      const day = m1[2].padStart(2, '0');
      return `${m1[3]}-${month}-${day}`;
    }
    const m2 = /^(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})$/.exec(trimmed);
    if (m2) {
      const month = m2[2].padStart(2, '0');
      const day = m2[3].padStart(2, '0');
      return `${m2[1]}-${month}-${day}`;
    }
    return null;
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    const target = event.target as HTMLElement;
    if (this.isCalendarOpen && !this.elementRef.nativeElement.querySelector('.dob-container')?.contains(target)) {
      this.isCalendarOpen = false;
    }
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    if (this.isSubmitting) { return; }

    const draft = this.registration.getDraft();
    if (!draft) {
      this.errorMessage = 'Registration data missing. Please restart from Step 1.';
      this.router.navigate(['/register']);
      return;
    }

    const firstName = this.firstName.trim();
    const lastName = this.lastName.trim();
    let dob = this.dob.trim();

    const normalizedDob = this.normalizeDate(dob);
    if (normalizedDob) {
      dob = normalizedDob;
      this.dob = normalizedDob;
    }

    if (!firstName || !lastName || !dob) {
      this.errorMessage = 'Please fill in all fields.';
      return;
    }

    if (!/^\d{4}-\d{2}-\d{2}$/.test(dob)) {
      this.errorMessage = 'Please enter or select a valid date of birth (YYYY-MM-DD).';
      return;
    }

    this.isSubmitting = true;
    this.errorMessage = null;

    const details = {
      ...draft,
      first_name: firstName,
      last_name: lastName,
      date_of_birth: dob
    };

    this.registration.register(details).subscribe({
      next: () => {
        this.isSubmitting = false;
        this.registration.clearDraft();
        // Ensure any existing authentication is cleared
        this.auth.logout();
        // Navigate to login page, passing state to indicate successful registration
        this.router.navigate(['/'], { state: { registered: true, email: draft.email } });
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;
        if (err.error && typeof err.error === 'object') {
          const messages = Object.entries(err.error)
            .map(([key, val]) => `${key}: ${Array.isArray(val) ? val.join(' ') : val}`)
            .join('; ');
          this.errorMessage = messages || 'Registration failed. Please check your information.';
        } else {
          this.errorMessage = 'Registration failed. Please try again.';
        }
      }
    });
  }
}
