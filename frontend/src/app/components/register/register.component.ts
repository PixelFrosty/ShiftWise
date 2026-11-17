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
  // UI state
  isMenuOpen: boolean = false;

  // Validation flags
  hasEmailError: boolean = false;
  hasUsernameError: boolean = false;
  hasPasswordError: boolean = false;

  constructor(private router: Router, private auth: AuthService) {}

  /** Shortcut for the template */
  get isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }

  /** Toggle the mobile menu */
  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  /** Handle registration form submit */
  onSubmit(event: Event): void {
    event.preventDefault();
    this.router.navigate(['/register-step-two']);
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
