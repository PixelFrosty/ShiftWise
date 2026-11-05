import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';

export interface UserProfile {
  username: string;
  role: 'CEO' | 'MANAGER' | 'EMPLOYEE';
}

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

  // Current user state (can be wired to an AuthService)
  currentUser: UserProfile | null = null;
  isAuthenticated = false;

  notifications: NotificationMessage[] = [];

  isMenuOpen = false;

  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  closeMenu(): void {
    this.isMenuOpen = false;
  }

  get isManagerOrCeo(): boolean {
    return this.currentUser?.role === 'CEO' || this.currentUser?.role === 'MANAGER';
  }

  dismissNotification(id: string): void {
    this.notifications = this.notifications.filter(n => n.id !== id);
  }

  onLogout(): void {
    this.currentUser = null;
    this.isAuthenticated = false;
  }
}
