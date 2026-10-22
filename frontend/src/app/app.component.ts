import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService, UserProfile } from './services/auth.service';

export interface NotificationMessage {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  text: string;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss'
})
export class AppComponent {
  title = 'ShiftWise';

  notifications: NotificationMessage[] = [];

  isMenuOpen = false;

  constructor(public auth: AuthService) {}

  get currentUser(): UserProfile | null {
    return this.auth.currentUser;
  }

  get isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }

  get isManagerOrCeo(): boolean {
    return this.auth.isManagerOrCeo;
  }

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  closeMenu(): void {
    this.isMenuOpen = false;
  }

  dismissNotification(id: string): void {
    this.notifications = this.notifications.filter(n => n.id !== id);
  }

  onLogout(): void {
    this.auth.logout();
  }
}
