import { Component, inject } from '@angular/core';
import { Router, RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from './core/auth.service';
import { Role } from './core/models';

export interface UserProfile {
  username: string;
  role?: Role;
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
  private auth = inject(AuthService);
  private router = inject(Router);
  title = 'ShiftWise';

  get isAuthenticated(): boolean {
    return this.auth.isAuthenticated;
  }

  get currentUser(): UserProfile | null {
    const me = this.auth.me();
    if (me) {
      return {
        username: me.first_name ? `${me.first_name} ${me.last_name || ''}`.trim() : (me.username || this.auth.user()?.username || ''),
        role: me.profile?.role
      };
    }
    const user = this.auth.user();
    if (user) {
      return { username: user.username };
    }
    return null;
  }

  get isManagerOrCeo(): boolean {
    const role = this.auth.role;
    return role === 'ceo' || role === 'manager';
  }

  notifications: NotificationMessage[] = [];
  isMenuOpen = false;
  isProfileMenuOpen = false;
  


  toggleMenu(): void {
    this.isMenuOpen = !this.isMenuOpen;
  }

  closeMenu(): void {
    this.isMenuOpen = false;
  }

  toggleProfileMenu(): void {
    this.isProfileMenuOpen = !this.isProfileMenuOpen;
  }

  closeProfileMenu(): void {
    this.isProfileMenuOpen = false;
  }

  goToAccount(): void {
    this.closeProfileMenu();
    this.router.navigate(['/account']);
  }

  goToCompanies(): void {
    this.closeProfileMenu();
    this.router.navigate(['/companies']);
  }

  
  dismissNotification(id: string): void {
    this.notifications = this.notifications.filter(n => n.id !== id);
  }

  logout(): void {
    this.auth.logout();
  }

}
