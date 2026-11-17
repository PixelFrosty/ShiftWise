import { Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-join-company',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="max-w-[420px] mx-auto my-12 px-4">
      <div class="bg-white p-8 rounded-xl border border-slate-200 shadow-sm">
        <h2 class="text-2xl font-bold text-slate-900 mb-1 text-center">Join a company</h2>
        <p class="text-sm text-slate-500 text-center mb-5">
          Your account isn't part of a company right now. Enter a join code from your General Manager or manager to join one.
        </p>
        @if (error) {
          <div class="p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-sm font-medium text-center mb-4" data-testid="join-error">{{ error }}</div>
        }
        <form class="space-y-4" (ngSubmit)="submit()">
          <div>
            <label for="code" class="block text-sm font-bold text-slate-700 mb-1.5">Join Code</label>
            <input id="code" name="code" type="text" autocomplete="off" placeholder="XXXX-XXXX" maxlength="20" [(ngModel)]="code" (ngModelChange)="error = ''"
                   class="w-full h-10 bg-slate-50 border border-slate-300 rounded-md px-3 text-sm uppercase tracking-widest outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-500/20" />
          </div>
          <button type="submit" [disabled]="busy" class="w-full h-11 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white font-semibold rounded-md shadow-sm transition cursor-pointer">
            {{ busy ? 'Joining…' : 'Join company' }}
          </button>
        </form>
      </div>
    </div>`
})
export class JoinCompanyComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private router = inject(Router);

  code = '';
  error = '';
  busy = false;

  submit(): void {
    if (this.busy) { return; }
    if (!this.code.trim()) { this.error = 'Enter a join code.'; return; }
    this.busy = true;
    this.api.joinCompany(this.code.trim()).subscribe({
      next: me => { this.busy = false; this.auth.me.set(me); this.router.navigate(['/home']); },
      error: err => { this.busy = false; this.error = errorText(err); }
    });
  }
}
