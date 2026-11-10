import { Component, OnDestroy, inject } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';

import { AuthService, UserProfile } from './core/auth.service';
import { Me, Role, roleLabel } from './core/models';

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
export class AppComponent implements OnDestroy {
  title = 'ShiftWise';

  private auth = inject(AuthService);
  private poll = setInterval(() => {
    // Keep the bell's unread count fresh while someone is signed in.
    if (this.auth.isAuthenticated && this.auth.me()) { this.auth.loadMe().subscribe({ error: () => undefined }); }
  }, 60000);

  ngOnDestroy(): void {
    clearInterval(this.poll);
  }

  get currentUser(): UserProfile | null {
    return this.auth.user();
  }

  get isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }

  get me(): Me | null {
    return this.auth.me();
  }

  get role(): Role | undefined {
    return this.auth.role;
  }

  get roleText(): string {
    return roleLabel(this.role);
  }

  get displayName(): string {
    const me = this.me;
    return me ? `${me.first_name} ${me.last_name}`.trim() || me.username : this.currentUser?.username ?? '';
  }

  get hasCompany(): boolean {
    return !!this.me?.profile;
  }

  get isManagerOrCeo(): boolean {
    return this.role === 'ceo' || this.role === 'manager';
  }

  get isCeo(): boolean {
    return this.role === 'ceo';
  }

  get unread(): number {
    return this.me?.unread_notifications ?? 0;
  }

  notifications: NotificationMessage[] = [];

  isMenuOpen = false;

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
