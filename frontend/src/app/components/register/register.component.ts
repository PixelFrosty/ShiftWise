import { Component } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

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

  constructor(private router: Router) { }

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  onSubmit(event: Event): void {
    event.preventDefault();
    this.router.navigate(['/register-step-two']);
  }
}