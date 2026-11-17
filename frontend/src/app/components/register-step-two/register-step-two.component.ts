import { Component, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { RegistrationService } from '../../core/registration.service';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-register-step-two',
  standalone: true,
  imports: [RouterLink, FormsModule],
  templateUrl: './register-step-two.component.html',
  styleUrl: './register-step-two.component.scss'
})
export class RegisterStepTwoComponent {
  isMenuOpen: boolean = false;
  firstName: string = '';
  lastName: string = '';
  dob: string = '';
  errorMessage: string | null = null;

  private registration = inject(RegistrationService);
  private auth = inject(AuthService);
  private router = inject(Router);

  toggleMenu(): void { this.isMenuOpen = !this.isMenuOpen; }

  onSubmit(event: Event): void {
    event.preventDefault();
    const draft = this.registration.getDraft();
    if (!draft) {
      this.errorMessage = 'Registration data missing.';
      return;
    }
    const details = {
      ...draft,
      first_name: this.firstName,
      last_name: this.lastName,
      date_of_birth: this.dob
    };
    this.registration.register(details as any).subscribe({
      next: () => {
        // Ensure any existing authentication is cleared
        this.auth.logout();
        // Navigate to login page, passing state to indicate successful registration
        this.router.navigate(['/'], { state: { registered: true, email: draft.email } });
      },
      error: () => {
        this.errorMessage = 'Registration failed.';
      }
    });
  }
}
