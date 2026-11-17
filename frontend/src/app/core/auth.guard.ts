import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';
import { AuthService } from './auth.service';
import { Role } from './models';

/** Makes sure the signed-in user's profile is loaded, then runs `check` on it. */
function withMe(allowed: Role[] | null, needsProfile: boolean): CanActivateFn {
  return () => {
    const auth = inject(AuthService);
    const router = inject(Router);
    if (!auth.isAuthenticated) { return router.createUrlTree(['/']); }

    const decide = (role: Role | undefined) => {
      if (!role) { return needsProfile ? router.createUrlTree(['/join-company']) : true; }
      if (allowed && !allowed.includes(role)) { return router.createUrlTree(['/home']); }
      return true;
    };
    const me = auth.me();
    if (me) { return decide(me.profile?.role); }
    return auth.loadMe().pipe(
      map(loaded => decide(loaded.profile?.role)),
      catchError(() => of(router.createUrlTree(['/'])))
    );
  };
}

/** Signed in AND belongs to a company (people without one are sent to "Join a company"). */
export const authGuard: CanActivateFn = withMe(null, true);

/** Signed in, no company needed (used by the join-company and account pages). */
export const signedInGuard: CanActivateFn = withMe(null, false);

/** Only the given roles may open the route; everyone else lands on the home page. */
export const roleGuard = (...roles: Role[]): CanActivateFn => withMe(roles, true);
