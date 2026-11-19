import { Component, inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { RegistrationService } from '../../core/registration.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [RouterLink, FormsModule],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss'
})
export class RegisterComponent {
  private router = inject(Router);
  private auth = inject(AuthService);
  private registration = inject(RegistrationService);

  // Form fields
  username = '';
  email = '';
  password = '';
  confirmPassword = '';

  // UI state
  isMenuOpen: boolean = false;
  isSubmitting: boolean = false;

  // Validation flags
  hasEmailError: boolean = false;
  hasUsernameError: boolean = false;
  hasTakenError: boolean = false;
  hasPasswordError: boolean = false;
  errorMessage: string = '';

  /** Shortcut for the template */
  get isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }

  /** Toggle the mobile menu */
  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  clearErrors(): void {
    this.hasEmailError = false;
    this.hasUsernameError = false;
    this.hasTakenError = false;
    this.hasPasswordError = false;
    this.errorMessage = '';
  }

  /** Handle registration form submit */
  onSubmit(event: Event): void {
    event.preventDefault();
    if (this.isSubmitting) { return; }
    this.clearErrors();

    const username = this.username.trim();
    const email = this.email.trim();
    const password = this.password;
    const confirmPassword = this.confirmPassword;

    if (!username || !email || !password || !confirmPassword) {
      this.errorMessage = 'Please fill in all fields.';
      return;
    }

    if (password !== confirmPassword) {
      this.hasPasswordError = true;
      return;
    }

    this.isSubmitting = true;
    this.registration.isAvailable(email, username).subscribe({
      next: (available) => {
        this.isSubmitting = false;
        if (!available) {
          this.hasTakenError = true;
          this.errorMessage = 'The email or username entered already exists, please try again.';
        } else {
          this.registration.saveDraft({ username, email, password });
          this.router.navigate(['/register-step-two']);
        }
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;
        if (err.status === 409) {
          this.hasTakenError = true;
          this.errorMessage = 'The email or username entered already exists, please try again.';
        } else if (err.status === 400) {
          this.errorMessage = 'Please provide both a valid email and username.';
        } else {
          this.errorMessage = 'Unable to verify email and username. Please try again.';
        }
      }
    });
  }

  /** Log out and optionally navigate to login */
  goToLogin(event: Event): void {
    event.preventDefault();
    this.auth.logout();
  }

  /** Log out directly from the sign‑up page when already logged in */
  logoutNow(event: Event): void {
    event.preventDefault();
    this.auth.logout();
  }
}
