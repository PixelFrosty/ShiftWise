import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Observable, catchError, map, of, throwError } from 'rxjs';
import { API_URL } from './api';

export interface RegistrationStepOne {
  username: string;
  email: string;
  password: string;
  role: 'ceo' | 'manager' | 'employee';
  company_name?: string;     // General Manager
  department_name?: string;  // General Manager (optional, defaults to "General" on the server)
  join_code?: string;        // manager / employee
}

export interface JoinCodeInfo {
  valid: boolean;
  role: 'manager' | 'employee';
  company: string;
  departments: string[];
}

export interface RegistrationDetails extends RegistrationStepOne {
  first_name: string;
  last_name: string;
  date_of_birth: string; // YYYY-MM-DD
}

@Injectable({ providedIn: 'root' })
export class RegistrationService {
  private http = inject(HttpClient);

  // Page-one answers are held in memory only (never written to storage, since they include the
  // password). A page refresh on step two clears them and sends the user back to step one.
  private draft: RegistrationStepOne | null = null;

  saveDraft(draft: RegistrationStepOne): void {
    this.draft = draft;
  }

  getDraft(): RegistrationStepOne | null {
    return this.draft;
  }

  clearDraft(): void {
    this.draft = null;
  }

  /** true = both free, false = one of them is already registered (the API doesn't say which). */
  isAvailable(email: string, username: string): Observable<boolean> {
    const params = new HttpParams().set('email', email).set('username', username);
    return this.http.get(`${API_URL}/signup-check/`, { params }).pipe(
      map(() => true),
      catchError((err: HttpErrorResponse) => (err.status === 409 ? of(false) : throwError(() => err)))
    );
  }

  /** Resolves with the code's details, or rejects with the server's error message text. */
  checkJoinCode(code: string, role: string): Observable<JoinCodeInfo> {
    const params = new HttpParams().set('code', code).set('role', role);
    return this.http.get<JoinCodeInfo>(`${API_URL}/join-code-check/`, { params });
  }

  register(details: RegistrationDetails): Observable<unknown> {
    return this.http.post(`${API_URL}/signup/`, details);
  }
}
