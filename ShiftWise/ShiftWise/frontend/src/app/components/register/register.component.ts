import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { map, of, switchMap } from 'rxjs';
import { RegistrationService } from '../../core/registration.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [RouterLink, FormsModule],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss'
})
export class RegisterComponent {
  private router = inject(Router);
  private registration = inject(RegistrationService);

  isMenuOpen: boolean = false;

  username = '';
  email = '';
  password = '';
  confirmPassword = '';
  role: 'ceo' | 'manager' | 'employee' = 'employee';
  companyName = '';
  departmentName = '';
  joinCode = '';
  isSubmitting = false;

  readonly roles = [
    { value: 'ceo' as const, label: 'General Manager', hint: 'Start a new company' },
    { value: 'manager' as const, label: 'Manager', hint: 'Join with a manager code' },
    { value: 'employee' as const, label: 'Employee', hint: 'Join with an employee code' }
  ];

  // The signup-check API deliberately doesn't say whether the email or the username was taken.
  hasTakenError: boolean = false;
  hasPasswordError: boolean = false;
  formError: string | null = null;

  constructor() {
    // Coming back from step two (e.g. the account was taken in the meantime): keep what was typed.
    const draft = this.registration.getDraft();
    if (draft) {
      this.username = draft.username;
      this.email = draft.email;
      this.role = draft.role;
      this.companyName = draft.company_name ?? '';
      this.departmentName = draft.department_name ?? '';
      this.joinCode = draft.join_code ?? '';
    }
    const state = this.router.getCurrentNavigation()?.extras.state;
    if (state?.['taken']) { this.hasTakenError = true; }
    if (typeof state?.['joinCodeError'] === 'string') { this.formError = state['joinCodeError']; }
  }

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  clearErrors(): void {
    this.hasTakenError = false;
    this.hasPasswordError = false;
    this.formError = null;
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    if (this.isSubmitting) { return; }
    this.clearErrors();

    const username = this.username.trim();
    const email = this.email.trim();

    if (!username || !email || !this.password || !this.confirmPassword) {
      this.formError = 'Please fill in every field.';
      return;
    }
    if (this.password !== this.confirmPassword) {
      this.hasPasswordError = true;
      return;
    }
    if (this.password.length < 8) {
      this.formError = 'Password must be at least 8 characters.';
      return;
    }

    const company = this.companyName.trim();
    const code = this.joinCode.trim();
    if (this.role === 'ceo' && !company) {
      this.formError = 'Enter your company name.';
      return;
    }
    if (this.role !== 'ceo' && !code) {
      this.formError = 'Enter the join code you were given.';
      return;
    }

    this.isSubmitting = true;
    this.registration.isAvailable(email, username).pipe(
      switchMap(available => {
        if (!available) { return of('taken' as const); }
        if (this.role === 'ceo') { return of('ok' as const); }
        // Managers and employees need a real, unused code before they can continue.
        return this.registration.checkJoinCode(code, this.role).pipe(map(() => 'ok' as const));
      })
    ).subscribe({
      next: result => {
        this.isSubmitting = false;
        if (result === 'taken') {
          this.hasTakenError = true;
          return;
        }
        this.registration.saveDraft({
          username, email, password: this.password, role: this.role,
          ...(this.role === 'ceo'
            ? { company_name: company, department_name: this.departmentName.trim() || undefined }
            : { join_code: code })
        });
        this.router.navigate(['/register-step-two']);
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;
        if (err.status === 404 || err.status === 400) {
          this.formError = errorText({ error: { detail: err.error?.detail } }, 'That code does not exist.');
        } else {
          this.formError = 'Unable to reach the server. Please try again.';
        }
      }
    });
  }
}
