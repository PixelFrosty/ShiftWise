import { Routes } from '@angular/router';
import { LandingPageComponent } from './components/landing-page/landing-page.component';
import { ForgotPasswordComponent } from './components/forgot-password/forgot-password.component';
import { RegisterComponent } from './components/register/register.component';
import { RegisterStepTwoComponent } from './components/register-step-two/register-step-two.component';
import { EmployeeDirectoryComponent } from './components/employee-directory/employee-directory.component';

export const routes: Routes = [
    { path: '', component: LandingPageComponent },
    { path: 'forgot-password', component: ForgotPasswordComponent },
    { path: 'register', component: RegisterComponent },
    { path: 'register-step-two', component: RegisterStepTwoComponent },
    { path: 'employees', component: EmployeeDirectoryComponent }
];