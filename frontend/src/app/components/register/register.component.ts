import { Component } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss'
})
export class RegisterComponent {
  isMenuOpen: boolean = false;

  // Actually set errors up //
  hasEmailError: boolean = false;
  hasUsernameError: boolean = false;
  hasPasswordError: boolean = false;

  constructor(private router: Router, private auth: AuthService) { }

  get isAuthenticated(): boolean { return this.auth.isAuthenticated; }

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    this.router.navigate(['/register-step-two']);
  }

  /** Logout then navigate to the login page */
  goToLogin(event: Event): void {
    event.preventDefault();
    this.auth.logout();
  }

  /** Log out directly from the sign‑up page when user is already logged in */
  logoutNow(event: Event): void {
    event.preventDefault();
    this.auth.logout();
  }

  isMenuOpen: boolean = false;

  // Actually set errors up //
  hasEmailError: boolean = false;
  hasUsernameError: boolean = false;
  hasPasswordError: boolean = false;

  constructor(private router: Router, private auth: AuthService) { }

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    this.router.navigate(['/register-step-two']);
  }

  /** Logout then navigate to the login page */
  goToLogin(event: Event): void {
    event.preventDefault();
    this.auth.logout();
  }
}