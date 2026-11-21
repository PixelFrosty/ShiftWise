import { Component, inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-landing-page',
  standalone: true,
  imports: [RouterLink, FormsModule],
  templateUrl: './landing-page.component.html',
  styleUrl: './landing-page.component.scss'
})
export class LandingPageComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  email = '';
  password = '';
  showPassword = false;
  isSubmitting = false;

  hasError: boolean = false;
  errorMessage: string = '';

  isMenuOpen: boolean = false;
  justRegistered = false;

  constructor() {
    const state = this.router.getCurrentNavigation()?.extras.state || (typeof history !== 'undefined' ? history.state : undefined);
    if (state?.['registered']) {
      this.justRegistered = true;
      this.email = typeof state['email'] === 'string' ? state['email'] : '';
    }

    // Already signed in: skip the sign-in screen.
    if (this.auth.isAuthenticated) {
      this.router.navigate(['/home']);
    }
  }

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  clearError(): void {
    this.hasError = false;
    this.justRegistered = false;
  }

  onLogin(event: Event): void {
    event.preventDefault();
    if (this.isSubmitting) { return; }

    if (!this.email.trim() || !this.password) {
      this.showError('Please enter your email and password.');
      return;
    }

    this.isSubmitting = true;
    this.hasError = false;

    this.auth.login(this.email.trim(), this.password).subscribe({
      next: () => {
        this.isSubmitting = false;
        this.router.navigate(['/home']);
      },
      error: (err: HttpErrorResponse) => {
        this.isSubmitting = false;
        if (err.status === 401 || err.status === 400) {
          this.showError('Email or password is incorrect. Try again.');
        } else if (err.status === 429) {
          this.showError('Too many attempts. Please wait a moment and try again.');
        } else {
          this.showError('Unable to reach the server. Please try again.');
        }
      }
    });
  }

  private showError(message: string): void {
    this.errorMessage = message;
    this.hasError = true;
  }
}
