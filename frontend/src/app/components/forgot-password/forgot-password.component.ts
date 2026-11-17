import { Component } from '@angular/core';


@Component({
  selector: 'app-forgot-password',
  standalone: true,

  templateUrl: './forgot-password.component.html',
  styleUrl: './forgot-password.component.scss'
})
export class ForgotPasswordComponent {
  isMenuOpen: boolean = false;

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  onSubmit(event: Event): void {
    event.preventDefault();
  }
}