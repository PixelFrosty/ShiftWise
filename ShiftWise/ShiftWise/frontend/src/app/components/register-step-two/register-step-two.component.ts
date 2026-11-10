import { Component, inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { RegistrationService } from '../../core/registration.service';

@Component({
  selector: 'app-register-step-two',
  standalone: true,
  imports: [RouterLink, FormsModule],
  templateUrl: './register-step-two.component.html',
  styleUrl: './register-step-two.component.scss'
})
export class RegisterStepTwoComponent {
  private router = inject(Router);
  private registration = inject(RegistrationService);

  isMenuOpen: boolean = false;

  firstName = '';
  lastName = '';
  dateOfBirth = ''; // YYYY-MM-DD from <input type="date">
  isSubmitting = false;

  errorMessage: string | null = null;
  readonly maxDate = new Date().toISOString().slice(0, 10);

  constructor() {
    // Step one hasn't been completed (or the page was refreshed): start from the beginning.
    if (!this.registration.getDraft()) {
      this.router.navigate(['/register']);
    }
  }

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  clearError(): void {
    this.errorMessage = null;
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    if (this.isSubmitting) { return; }
    const draft = this.registration.getDraft();
    if (!draft) {
      this.router.navigate(['/register']);
      return;
    }

    const first = this.firstName.trim();
    const last = this.lastName.trim();
    if (!first || !last) {
      this.errorMessage = 'Please enter your first and last name.';
      return;
    }
    if (!this.isValidBirthday(this.dateOfBirth)) {
      this.errorMessage = 'The birthday entered is invalid, please try again.';
      return;
    }

    this.isSubmitting = true;
    this.errorMessage = null;
    this.registration.register({
      ...draft,
      first_name: first,
      last_name: last,
      date_of_birth: this.dateOfBirth
    }).subscribe({
      next: () => {
        this.isSubmitting = false;
        this.registration.clearDraft();
        this.router.navigate(['/'], { state: { registered: true, email: draft.email } });
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;
        this.handleError(err);
      }
    });
  }

  private handleError(err: HttpErrorResponse): void {
    const body = err.error && typeof err.error === 'object' ? err.error : {};
    if (err.status === 400 && (body.email || body.username)) {
      // Taken between step one and now: send them back to pick another.
      this.router.navigate(['/register'], { state: { taken: true } });
    } else if (err.status === 400 && (body.join_code || body.company_name)) {
      // The code was used by someone else in the meantime, or the company name was rejected.
      const message = (body.join_code ?? body.company_name)[0];
      this.router.navigate(['/register'], { state: { joinCodeError: message } });
    } else if (err.status === 400 && body.date_of_birth) {
      this.errorMessage = 'The birthday entered is invalid, please try again.';
    } else if (err.status === 400) {
      this.errorMessage = 'Some of the details entered are invalid, please check them and try again.';
    } else {
      this.errorMessage = 'Unable to create your account right now. Please try again.';
    }
  }

  private isValidBirthday(value: string): boolean {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) { return false; }
    const d = new Date(value + 'T00:00:00');
    if (isNaN(d.getTime())) { return false; }
    const year = d.getFullYear();
    return year >= 1900 && d.getTime() <= Date.now();
  }
}
