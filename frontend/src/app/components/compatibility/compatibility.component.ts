import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService, CompatibilityPair, Employee } from '../../core/api.service';
import { errorText } from '../../core/models';

@Component({
  selector: 'app-compatibility',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <div class="max-w-4xl mx-auto py-6">
      <div class="flex flex-wrap items-center justify-between gap-4 mb-4">
        <div>
          <h1 class="text-2xl font-bold text-slate-900">Pairwise Compatibility</h1>
          <p class="text-sm text-slate-500 mt-1">
            Rate how well employee pairs collaborate (scores 0.0 to 10.0). Higher scores improve auto-scheduling synergy.
          </p>
        </div>
        <div class="flex items-center gap-2">
          <a routerLink="/employees" class="px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 rounded-lg text-sm font-medium transition no-underline">
            &larr; Back to Employees
          </a>
          @if (!showForm()) {
            <button type="button" (click)="openAddForm()" class="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-semibold transition cursor-pointer">
              + Rate Pair
            </button>
          }
        </div>
      </div>

      @if (errorMessage()) {
        <div class="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg text-sm font-medium">
          {{ errorMessage() }}
        </div>
      }

      @if (showForm()) {
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5 mb-6">
          <h2 class="text-lg font-bold text-slate-800 mb-4">{{ isEditing ? 'Update Compatibility Rating' : 'Add New Compatibility Rating' }}</h2>
          <form (ngSubmit)="submitRating()" class="space-y-4">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label for="empA" class="block text-xs font-bold text-slate-600 uppercase mb-1">Employee A</label>
                <select id="empA" name="empA" [(ngModel)]="selectedEmpA" class="w-full h-10 border border-slate-300 rounded-lg px-3 text-sm bg-white" [disabled]="isEditing">
                  <option [ngValue]="null">Select employee...</option>
                  @for (emp of employees(); track emp.id) {
                    <option [ngValue]="emp.id" [disabled]="emp.id === selectedEmpB">{{ emp.name }}</option>
                  }
                </select>
              </div>

              <div>
                <label for="empB" class="block text-xs font-bold text-slate-600 uppercase mb-1">Employee B</label>
                <select id="empB" name="empB" [(ngModel)]="selectedEmpB" class="w-full h-10 border border-slate-300 rounded-lg px-3 text-sm bg-white" [disabled]="isEditing">
                  <option [ngValue]="null">Select employee...</option>
                  @for (emp of employees(); track emp.id) {
                    <option [ngValue]="emp.id" [disabled]="emp.id === selectedEmpA">{{ emp.name }}</option>
                  }
                </select>
              </div>

              <div>
                <label for="scoreInput" class="block text-xs font-bold text-slate-600 uppercase mb-1">Compatibility Score (0 - 10)</label>
                <div class="flex items-center gap-2">
                  <input id="scoreInput" name="scoreInput" type="number" min="0" max="10" step="0.1" [(ngModel)]="scoreValue"
                         class="w-full h-10 border border-slate-300 rounded-lg px-3 text-sm font-medium" />
                  <span class="text-xs font-bold px-2 py-1 rounded bg-slate-100 text-slate-700">/ 10</span>
                </div>
              </div>
            </div>

            <div class="flex justify-end gap-2 pt-2">
              <button type="button" (click)="cancelForm()" class="px-4 py-2 border border-slate-300 rounded-lg text-sm font-semibold text-slate-700 hover:bg-slate-50 cursor-pointer">
                Cancel
              </button>
              <button type="submit" [disabled]="isSaving" class="px-5 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-semibold transition cursor-pointer disabled:opacity-50">
                {{ isSaving ? 'Saving…' : 'Save Rating' }}
              </button>
            </div>
          </form>
        </div>
      }

      <!-- Ratings List -->
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table class="w-full text-sm text-left">
          <thead class="bg-slate-50 text-xs uppercase tracking-wider text-slate-500 border-b border-slate-200">
            <tr>
              <th class="px-6 py-3 font-semibold">Employee 1</th>
              <th class="px-6 py-3 font-semibold">Employee 2</th>
              <th class="px-6 py-3 font-semibold">Compatibility</th>
              <th class="px-6 py-3 font-semibold text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            @for (pair of pairs(); track pair.id) {
              <tr class="hover:bg-slate-50/50 transition">
                <td class="px-6 py-4 font-semibold text-slate-800">
                  {{ pair.employee_a_name }}
                </td>
                <td class="px-6 py-4 font-semibold text-slate-800">
                  {{ pair.employee_b_name }}
                </td>
                <td class="px-6 py-4">
                  <div class="flex items-center gap-3">
                    <span class="font-bold text-slate-900 w-9 text-right">{{ formatScore(pair.score) }}</span>
                    <div class="w-24 h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div class="h-full rounded-full" [class]="getScoreBarColor(pair.score)" [style.width.%]="Math.min(Number(pair.score) * 10, 100)"></div>
                    </div>
                  </div>
                </td>
                <td class="px-6 py-4 text-right whitespace-nowrap">
                  <button type="button" (click)="editPair(pair)" class="text-xs font-semibold text-brand-600 hover:text-brand-800 hover:underline mr-4 cursor-pointer">
                    Edit
                  </button>
                  <button type="button" (click)="deletePair(pair.id)" class="text-xs font-semibold text-rose-600 hover:text-rose-800 hover:underline cursor-pointer">
                    Delete
                  </button>
                </td>
              </tr>
            } @empty {
              <tr>
                <td colspan="4" class="px-6 py-12 text-center text-slate-500">
                  No pairwise compatibility ratings found. Click <strong>+ Rate Pair</strong> to add one.
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </div>`
})
export class CompatibilityComponent implements OnInit {
  private api = inject(ApiService);

  pairs = signal<CompatibilityPair[]>([]);
  employees = signal<Employee[]>([]);
  errorMessage = signal<string>('');
  showForm = signal<boolean>(false);
  isEditing = false;
  editingPairId: number | null = null;
  isSaving = false;

  selectedEmpA: number | null = null;
  selectedEmpB: number | null = null;
  scoreValue = 8.0;

  Math = Math;
  Number = Number;

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.api.pairwiseCompatibility().subscribe({
      next: data => this.pairs.set(data),
      error: err => this.errorMessage.set(errorText(err))
    });

    this.api.employees().subscribe({
      next: emps => this.employees.set(emps),
      error: () => {}
    });
  }

  openAddForm(): void {
    this.isEditing = false;
    this.editingPairId = null;
    this.selectedEmpA = null;
    this.selectedEmpB = null;
    this.scoreValue = 8.0;
    this.errorMessage.set('');
    this.showForm.set(true);
  }

  editPair(pair: CompatibilityPair): void {
    this.isEditing = true;
    this.editingPairId = pair.id;
    this.selectedEmpA = pair.employee_a;
    this.selectedEmpB = pair.employee_b;
    this.scoreValue = Number(pair.score);
    this.errorMessage.set('');
    this.showForm.set(true);
  }

  cancelForm(): void {
    this.showForm.set(false);
    this.isEditing = false;
    this.editingPairId = null;
    this.errorMessage.set('');
  }

  submitRating(): void {
    if (!this.selectedEmpA || !this.selectedEmpB) {
      this.errorMessage.set('Please select two distinct employees.');
      return;
    }
    if (this.selectedEmpA === this.selectedEmpB) {
      this.errorMessage.set('Employees must be distinct.');
      return;
    }
    if (this.scoreValue < 0 || this.scoreValue > 10) {
      this.errorMessage.set('Score must be between 0 and 10.');
      return;
    }

    this.isSaving = true;
    this.errorMessage.set('');

    this.api.savePairwiseScore(this.selectedEmpA, this.selectedEmpB, this.scoreValue).subscribe({
      next: () => {
        this.isSaving = false;
        this.showForm.set(false);
        this.loadData();
      },
      error: err => {
        this.isSaving = false;
        this.errorMessage.set(errorText(err));
      }
    });
  }

  deletePair(id: number): void {
    if (!confirm('Are you sure you want to delete this compatibility rating?')) {
      return;
    }
    this.api.deletePairwiseScore(id).subscribe({
      next: () => this.loadData(),
      error: err => this.errorMessage.set(errorText(err))
    });
  }

  formatScore(score: number | string): string {
    const num = Number(score);
    return isNaN(num) ? '—' : num.toFixed(1);
  }

  getScoreBarColor(score: number | string): string {
    const num = Number(score);
    if (num >= 8.0) return 'bg-emerald-500';
    if (num >= 5.0) return 'bg-amber-500';
    return 'bg-rose-500';
  }
}
