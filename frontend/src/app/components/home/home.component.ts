import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { Role } from '../../core/models';
import { mondayOf, toIso } from '../shared/week-utils';

interface HomeCard { title: string; text: string; link: string; cta: string; icon: string; primary?: boolean; }

interface HomeConfig {
  subtitle: string;
  cards: HomeCard[];
  banner: { title: string; text: string; secondary?: { label: string; link: string }; primary: { label: string; link: string } };
}


// Simple outline icons (24x24 paths)
const ICON = {
  calendar: '/icon_calendar.png',
  timeOff: '/icon_timeoff.png',
  clock: '/icon_clock.png',
  people: '/icon_employee.png',
  key: '/icon_code.png',
  org: '/icon_org.png'
};

@Component({
  selector: 'app-home',
  standalone: true,
  imports: [RouterLink],
  template: `
    @if (config(); as c) {
      <section class="max-w-6xl mx-auto py-6">
        <h1 class="mt-5 text-4xl sm:text-5xl font-extrabold tracking-tight text-slate-900" data-testid="welcome">Welcome back, {{ firstName() }}</h1>
        <p class="mt-2 text-lg text-slate-600">{{ c.subtitle }}</p>

        <div class="mt-9 grid gap-5" [style.grid-template-columns]="'repeat(auto-fit, minmax(210px, 1fr))'">
          @for (card of c.cards; track card.title) {
            <a [routerLink]="card.link" class="group block bg-white rounded-2xl border border-slate-200 shadow-sm hover:shadow-md hover:border-emerald-300 transition p-6 no-underline" [attr.data-testid]="'card-' + card.title.toLowerCase()">
              <span class="inline-flex items-center justify-center w-13 h-13 rounded-xl mb-4 p-3 bg-emerald-100 group-hover:bg-emerald-600 transition">
                <img [src]="card.icon" alt="" class="w-7 h-7 object-contain" />
              </span>
              <h2 class="text-xl font-bold text-slate-900">{{ card.title }}</h2>
              <p class="mt-1.5 text-sm text-slate-500 leading-relaxed">{{ card.text }}</p>
              <span class="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-emerald-700">{{ card.cta }} <span aria-hidden="true" class="transition group-hover:translate-x-0.5">&rarr;</span></span>
            </a>
          }
        </div>

        <div class="mt-6 bg-white rounded-2xl border border-slate-200 shadow-sm px-6 py-5 flex flex-wrap items-center gap-4" data-testid="banner">
          <span class="inline-flex items-center justify-center w-11 h-11 rounded-lg border-2 border-dashed border-slate-500 text-slate-700 text-xl">+</span>
          <div class="flex-1 min-w-[220px]">
            <div class="font-bold text-slate-900">{{ c.banner.title }}</div>
            <div class="text-sm text-slate-600">{{ c.banner.text }}</div>
          </div>
          <div class="flex gap-3">
            @if (c.banner.secondary; as s) {
              <a [routerLink]="s.link" class="px-5 py-2.5 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-sm font-semibold text-slate-800 no-underline">{{ s.label }}</a>
            }
            <a [routerLink]="c.banner.primary.link" class="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-sm font-semibold text-white no-underline shadow-sm">{{ c.banner.primary.label }}</a>
          </div>
        </div>
      </section>
    }`
})
export class HomeComponent {
  private auth = inject(AuthService);

  private thisWeek = '/schedules/week/' + toIso(mondayOf(new Date()));

  firstName = computed(() => this.auth.me()?.first_name || this.auth.me()?.username || '');

  config = computed<HomeConfig | null>(() => {
    const role: Role | undefined = this.auth.role;
    if (role === 'employee') {
      return {
        subtitle: 'Check your shifts, request time off and keep your availability up to date.',
        cards: [
          { title: 'Schedules', text: "See your upcoming shifts and the week's open shifts.", link: '/schedules', cta: 'View my schedule', icon: ICON.calendar, primary: true },
          { title: 'Time Off', text: 'Request days off and track the status of your requests.', link: '/time-off', cta: 'Request time off', icon: ICON.timeOff },
          { title: 'Availability', text: "Set the days and hours you're able to work.", link: '/availability', cta: 'Update availability', icon: ICON.clock }
        ],
        banner: { title: 'Want more hours?', text: "Look for open shifts on this week's schedule.", primary: { label: 'See open shifts', link: this.thisWeek } }
      };
    }
    if (role === 'manager') {
      return {
        subtitle: 'Keep your team scheduled and covered. Choose an area to get started.',
        cards: [
          { title: 'Schedules', text: 'Build, review and publish weekly schedules for your team.', link: '/schedules', cta: 'Open schedules', icon: ICON.calendar, primary: true },
          { title: 'Time Off', text: 'Approve or decline requests and see who on your team is out.', link: '/time-off', cta: 'Review requests', icon: ICON.timeOff },
          { title: 'Employees', text: "See your team's roles, availability and contact details.", link: '/employees', cta: 'View employees', icon: ICON.people },
          { title: 'Join Codes', text: 'Create codes so new hires can join your team.', link: '/codes', cta: 'Manage codes', icon: ICON.key }
        ],
        banner: { title: 'Open shifts to fill?', text: "Check this week's schedule or bring on someone new with a join code.",
                  secondary: { label: 'View this week', link: this.thisWeek }, primary: { label: 'Create join code', link: '/codes' } }
      };
    }
    if (role === 'ceo') {
      return {
        subtitle: 'Everything you need to run your workforce, one click away. Choose an area to get started.',
        cards: [
          { title: 'Schedules', text: 'Build, review and publish weekly schedules across every department.', link: '/schedules', cta: 'Open schedules', icon: ICON.calendar, primary: true },
          { title: 'Time Off', text: 'Approve or decline requests and see who is out this week.', link: '/time-off', cta: 'Review requests', icon: ICON.timeOff },
          { title: 'Employees', text: 'Manage your team, roles, availability and contact details.', link: '/employees', cta: 'View employees', icon: ICON.people },
          { title: 'Join Codes', text: 'Create codes so new hires can join the right department.', link: '/codes', cta: 'Manage codes', icon: ICON.key },
          { title: 'Departments', text: 'Organize teams, set coverage needs and assign managers.', link: '/departments', cta: 'View departments', icon: ICON.org }
        ],
        banner: { title: 'Growing the team?', text: 'Generate a join code and share it with new employees.',
                  secondary: { label: 'Add department', link: '/departments' }, primary: { label: 'Create join code', link: '/codes' } }
      };
    }
    return null;
  });
}
