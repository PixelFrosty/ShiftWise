import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, catchError, finalize, map, of, shareReplay, switchMap, tap, throwError } from 'rxjs';
import { API_URL } from './api';
import { Me, Role } from './models';

export interface UserProfile {
  username: string;
}

interface TokenPair { access: string; refresh: string; }

const ACCESS_KEY = 'sw_access';
const REFRESH_KEY = 'sw_refresh';
const EMAIL_KEY = 'sw_email';

function read(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key: string, value: string | null): void {
  try {
    if (value === null) { localStorage.removeItem(key); } else { localStorage.setItem(key, value); }
  } catch { /* storage unavailable: session just won't survive a reload */ }
}

/** True when the JWT is missing, malformed or past its `exp`. */
function isExpired(token: string | null): boolean {
  if (!token) { return true; }
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.exp !== 'number' || payload.exp * 1000 <= Date.now();
  } catch {
    return true;
  }
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  readonly user = signal<UserProfile | null>(null);
  /** Who the backend says we are (role, company, departments, unread count). Null until loaded. */
  readonly me = signal<Me | null>(null);
  private refreshInFlight$: Observable<string> | null = null;
  private meInFlight$: Observable<Me> | null = null;

  constructor() {
    // Restore a session after a page reload if the 30-day refresh token is still valid.
    const email = read(EMAIL_KEY);
    if (email && !isExpired(read(REFRESH_KEY))) {
      this.user.set({ username: email });
      this.loadMe().pipe(catchError(() => of(null))).subscribe();
    } else {
      this.clearSession();
    }
  }

  get isAuthenticated(): boolean {
    return this.user() !== null;
  }

  get accessToken(): string | null {
    return read(ACCESS_KEY);
  }

  get role(): Role | undefined {
    return this.me()?.profile?.role;
  }

  /** Fetches /api/me/ (current role, departments, unread notifications). Shared while in flight. */
  loadMe(): Observable<Me> {
    if (!this.meInFlight$) {
      this.meInFlight$ = this.http.get<Me>(`${API_URL}/me/`).pipe(
        tap(me => this.me.set(me)),
        finalize(() => { this.meInFlight$ = null; }),
        shareReplay(1)
      );
    }
    return this.meInFlight$;
  }

  setUnread(count: number): void {
    const me = this.me();
    if (me) { this.me.set({ ...me, unread_notifications: count }); }
  }

  login(email: string, password: string): Observable<void> {
    return this.http.post<TokenPair>(`${API_URL}/login/`, { email, password }).pipe(
      tap(tokens => {
        write(ACCESS_KEY, tokens.access);
        write(REFRESH_KEY, tokens.refresh);
        write(EMAIL_KEY, email);
        this.user.set({ username: email });
        this.me.set(null);
      }),
      switchMap(() => this.loadMe()),
      map(() => void 0)
    );
  }

  /** Gets a fresh access token. Concurrent callers share one request (refresh tokens rotate). */
  refreshAccessToken(): Observable<string> {
    const refresh = read(REFRESH_KEY);
    if (!refresh || isExpired(refresh)) {
      this.expireSession();
      return throwError(() => new Error('Session expired'));
    }
    if (!this.refreshInFlight$) {
      this.refreshInFlight$ = this.http.post<Partial<TokenPair>>(`${API_URL}/token/refresh/`, { refresh }).pipe(
        map(tokens => {
          if (!tokens.access) { throw new Error('No access token returned'); }
          write(ACCESS_KEY, tokens.access);
          if (tokens.refresh) { write(REFRESH_KEY, tokens.refresh); } // rotated
          return tokens.access;
        }),
        catchError(err => {
          this.expireSession();
          return throwError(() => err);
        }),
        finalize(() => { this.refreshInFlight$ = null; }),
        shareReplay(1)
      );
    }
    return this.refreshInFlight$;
  }

  logout(): void {
    const refresh = read(REFRESH_KEY);
    this.clearSession();
    if (refresh) {
      // Blacklist the refresh token server-side; the user is already logged out locally either way.
      this.http.post(`${API_URL}/logout/`, { refresh }).pipe(catchError(() => of(null))).subscribe();
    }
    this.router.navigate(['/']);
  }

  /** Session is no longer usable (refresh failed/expired): clear it and go to the sign-in page. */
  private expireSession(): void {
    this.clearSession();
    this.router.navigate(['/']);
  }

  private clearSession(): void {
    write(ACCESS_KEY, null);
    write(REFRESH_KEY, null);
    write(EMAIL_KEY, null);
    this.user.set(null);
    this.me.set(null);
  }
}
