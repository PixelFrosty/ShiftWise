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
                   class="w-full h-10 bg-slate-50 border border-slate-300 rounded-md px-3 text-sm uppercase tracking-widest outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-500/20" />
          </div>
          <button type="submit" [disabled]="busy" class="w-full h-11 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 text-white font-semibold rounded-md shadow-sm transition cursor-pointer">
            {{ busy ? 'Joining…' : 'Join company' }}
          </button>
        </form>

        <div class="relative my-6">
          <div class="absolute inset-0 flex items-center">
            <div class="w-full border-t border-slate-200"></div>
          </div>
          <div class="relative flex justify-center text-xs uppercase">
            <span class="bg-white px-2 text-slate-500 font-semibold">Or create a company</span>
          </div>
        </div>

        <form class="space-y-4" (ngSubmit)="submitCreate()">
          <div>
            <label for="newCompanyName" class="block text-sm font-bold text-slate-700 mb-1.5">Company Name</label>
            <input id="newCompanyName" name="newCompanyName" type="text" placeholder="e.g. Acme Corporation" maxlength="255" [(ngModel)]="newCompanyName" (ngModelChange)="createError = ''"
                   class="w-full h-10 bg-slate-50 border border-slate-300 rounded-md px-3 text-sm outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-500/20" />
          </div>
          @if (createError) {
            <div class="p-2.5 bg-rose-50 border border-rose-200 text-rose-800 rounded-md text-xs font-medium">{{ createError }}</div>
          }
          <button type="submit" [disabled]="createBusy" class="w-full h-11 bg-slate-800 hover:bg-slate-900 disabled:opacity-60 text-white font-semibold rounded-md shadow-sm transition cursor-pointer">
            {{ createBusy ? 'Creating company…' : 'Create company' }}
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

  newCompanyName = '';
  createError = '';
  createBusy = false;

  submit(): void {
    if (this.busy) { return; }
    if (!this.code.trim()) { this.error = 'Enter a join code.'; return; }
    this.busy = true;
    this.api.joinCompany(this.code.trim()).subscribe({
      next: me => { this.busy = false; this.auth.me.set(me); this.router.navigate(['/home']); },
      error: err => { this.busy = false; this.error = errorText(err); }
    });
  }

  submitCreate(): void {
    if (this.createBusy) { return; }
    if (!this.newCompanyName.trim()) { this.createError = 'Enter a company name.'; return; }
    this.createBusy = true;
    this.api.createCompany(this.newCompanyName.trim()).subscribe({
      next: me => { this.createBusy = false; this.auth.me.set(me); this.router.navigate(['/home']); },
      error: err => { this.createBusy = false; this.createError = errorText(err); }
    });
  }
}
