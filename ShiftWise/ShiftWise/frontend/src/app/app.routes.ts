import { Routes } from '@angular/router';
import { LandingPageComponent } from './components/landing-page/landing-page.component';
import { ForgotPasswordComponent } from './components/forgot-password/forgot-password.component';
import { RegisterComponent } from './components/register/register.component';
import { RegisterStepTwoComponent } from './components/register-step-two/register-step-two.component';
import { EmployeeDirectoryComponent } from './components/employee-directory/employee-directory.component';
import { ScheduleCalendarComponent } from './components/schedule-calendar/schedule-calendar.component';
import { WeeklyScheduleComponent } from './components/weekly-schedule/weekly-schedule.component';
import { authGuard, roleGuard, signedInGuard } from './core/auth.guard';
import { JoinCompanyComponent } from './components/join-company/join-company.component';
import { AccountComponent } from './components/account/account.component';
import { NotificationsComponent } from './components/notifications/notifications.component';
import { JoinCodesComponent } from './components/join-codes/join-codes.component';
import { DepartmentsComponent } from './components/departments/departments.component';
import { HomeComponent } from './components/home/home.component';
import { AvailabilityComponent } from './components/availability/availability.component';
import { ProjectsComponent } from './components/projects/projects.component';
import { TimeOffComponent } from './components/time-off/time-off.component';

export const routes: Routes = [
    { path: '', component: LandingPageComponent },
    { path: 'forgot-password', component: ForgotPasswordComponent },
    { path: 'register', component: RegisterComponent },
    { path: 'register-step-two', component: RegisterStepTwoComponent },
    { path: 'home', canActivate: [authGuard], component: HomeComponent },
    { path: 'availability', canActivate: [authGuard], component: AvailabilityComponent },
    { path: 'employees', canActivate: [roleGuard('ceo', 'manager')], component: EmployeeDirectoryComponent },
    { path: 'codes', canActivate: [roleGuard('ceo', 'manager')], component: JoinCodesComponent },
    { path: 'departments', canActivate: [roleGuard('ceo')], component: DepartmentsComponent },
    { path: 'projects', canActivate: [authGuard], component: ProjectsComponent },
    { path: 'time-off', canActivate: [authGuard], component: TimeOffComponent },
    { path: 'notifications', canActivate: [authGuard], component: NotificationsComponent },
    { path: 'join-company', canActivate: [signedInGuard], component: JoinCompanyComponent },
    { path: 'account', canActivate: [signedInGuard], component: AccountComponent },
    { path: 'schedules', canActivate: [authGuard], component: ScheduleCalendarComponent },
    { path: 'schedules/week/:start', canActivate: [authGuard], component: WeeklyScheduleComponent },
    { path: '**', redirectTo: '' }
];
