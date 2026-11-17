import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { API_URL } from './api';
import { AuthService } from './auth.service';

const PUBLIC_PATHS = ['/login/', '/token/refresh/', '/logout/', '/signup/', '/signup-check/', '/join-code-check/'];

function withToken(req: HttpRequest<unknown>, token: string): HttpRequest<unknown> {
  return req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
}

/** Adds the Bearer token to API calls and retries once with a refreshed token after a 401. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const isApi = req.url.startsWith(API_URL);
  const isPublic = PUBLIC_PATHS.some(p => req.url.startsWith(API_URL + p));
  if (!isApi || isPublic) { return next(req); }

  const token = auth.accessToken;
  const authed = token ? withToken(req, token) : req;

  return next(authed).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 401 && auth.isAuthenticated) {
        return auth.refreshAccessToken().pipe(switchMap(fresh => next(withToken(req, fresh))));
      }
      return throwError(() => err);
    })
  );
};
