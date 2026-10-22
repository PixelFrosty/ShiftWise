import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

export interface Department {
  id: number;
  name: string;
}

export interface Employee {
  id: number;
  name: string;
  position: string;
  department: Department;
  role: 'ceo' | 'manager' | 'employee';
  productivityScore: number | null;
  payRate: number | null;
}

@Component({
  selector: 'app-employee-directory',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './employee-directory.component.html',
  styleUrl: './employee-directory.component.scss'
})
export class EmployeeDirectoryComponent {
  searchQuery = '';
  selectedDeptId = '';

  // Placeholder departments — replace with HttpClient call when API is ready
  departments: Department[] = [
    { id: 1, name: 'Engineering' },
    { id: 2, name: 'Marketing' },
    { id: 3, name: 'Operations' },
    { id: 4, name: 'Human Resources' }
  ];

  // Placeholder employees — replace with HttpClient call when API is ready
  employees: Employee[] = [
    { id: 1, name: 'Alice Johnson',   position: 'Senior Developer',    department: { id: 1, name: 'Engineering' },      role: 'employee', productivityScore: 8.5,  payRate: 55.00 },
    { id: 2, name: 'Bob Martinez',    position: 'Marketing Lead',      department: { id: 2, name: 'Marketing' },        role: 'manager',  productivityScore: 7.2,  payRate: 48.00 },
    { id: 3, name: 'Carol Williams',  position: 'Operations Manager',  department: { id: 3, name: 'Operations' },       role: 'manager',  productivityScore: 9.0,  payRate: 62.00 },
    { id: 4, name: 'David Chen',      position: 'Junior Developer',    department: { id: 1, name: 'Engineering' },      role: 'employee', productivityScore: 6.0,  payRate: 35.00 },
    { id: 5, name: 'Eva Thompson',    position: 'HR Coordinator',      department: { id: 4, name: 'Human Resources' },  role: 'employee', productivityScore: 7.8,  payRate: 42.00 },
    { id: 6, name: 'Frank Lee',       position: 'CEO',                 department: { id: 1, name: 'Engineering' },      role: 'ceo',      productivityScore: null, payRate: null },
    { id: 7, name: 'Grace Kim',       position: 'Content Strategist',  department: { id: 2, name: 'Marketing' },        role: 'employee', productivityScore: 8.0,  payRate: 40.00 },
    { id: 8, name: 'Henry Patel',     position: 'DevOps Engineer',     department: { id: 1, name: 'Engineering' },      role: 'employee', productivityScore: 9.3,  payRate: 58.00 }
  ];

  get filteredEmployees(): Employee[] {
    let result = this.employees;
    const query = this.searchQuery.trim().toLowerCase();

    if (query) {
      result = result.filter(emp =>
        emp.name.toLowerCase().includes(query) ||
        emp.position.toLowerCase().includes(query)
      );
    }

    if (this.selectedDeptId) {
      const deptId = Number(this.selectedDeptId);
      result = result.filter(emp => emp.department.id === deptId);
    }

    return result;
  }

  get hasActiveFilters(): boolean {
    return this.searchQuery.trim() !== '' || this.selectedDeptId !== '';
  }

  clearFilters(): void {
    this.searchQuery = '';
    this.selectedDeptId = '';
  }

  getProductivityBarWidth(score: number | null): string {
    if (score === null) return '0%';
    return Math.min(score * 10, 100) + '%';
  }

  getProductivityBarColor(score: number | null): string {
    if (score === null) return 'bg-slate-300';
    if (score >= 8) return 'bg-emerald-600';
    if (score >= 5) return 'bg-amber-500';
    return 'bg-rose-500';
  }

  getRoleBadgeClasses(role: string): string {
    switch (role) {
      case 'ceo':      return 'bg-purple-100 text-purple-800';
      case 'manager':  return 'bg-blue-100 text-blue-800';
      default:         return 'bg-emerald-100 text-emerald-800';
    }
  }

  getRoleLabel(role: string): string {
    switch (role) {
      case 'ceo':      return 'CEO';
      case 'manager':  return 'Manager';
      default:         return 'Employee';
    }
  }

  formatPayRate(rate: number | null): string {
    if (rate === null) return '—';
    return '$' + rate.toFixed(2) + '/hr';
  }
}
