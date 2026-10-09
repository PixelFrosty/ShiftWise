import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-register-step-two',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './register-step-two.component.html',
  styleUrl: './register-step-two.component.scss'
})
export class RegisterStepTwoComponent {
  isMenuOpen: boolean = false;

  errorMessage: string | null = 'The birthday entered is invalid, please try again.';

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  onSubmit(event: Event): void {
    event.preventDefault();
  }
}