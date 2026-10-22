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

export interface EditEmployeeForm {
  id: number;
  name: string;
  position: string;
  departmentId: number;
  role: 'ceo' | 'manager' | 'employee';
  productivityScore: number | null;
  payRate: number | null;
}

export interface AddEmployeeForm {
  name: string;
  position: string;
  departmentId: number;
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

  // Delete modal state
  employeeToDelete: Employee | null = null;
  isDeleting = false;

  // Edit modal state
  editingEmployee: EditEmployeeForm | null = null;
  isSavingEdit = false;

  // Add modal state
  isAddModalOpen = false;
  isAdding = false;
  newEmployee: AddEmployeeForm = this.getInitialAddForm();

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

  private getInitialAddForm(): AddEmployeeForm {
    return {
      name: '',
      position: '',
      departmentId: 1,
      role: 'employee',
      productivityScore: 7.0,
      payRate: 25.00
    };
  }

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

  // Delete modal methods
  openDeleteModal(emp: Employee): void {
    this.employeeToDelete = emp;
  }

  closeDeleteModal(): void {
    if (this.isDeleting) return;
    this.employeeToDelete = null;
  }

  confirmDelete(): void {
    if (!this.employeeToDelete) return;
    this.isDeleting = true;

    // Simulate delete: remove employee from the list
    setTimeout(() => {
      const idToDelete = this.employeeToDelete?.id;
      this.employees = this.employees.filter(e => e.id !== idToDelete);
      this.isDeleting = false;
      this.employeeToDelete = null;
    }, 300);
  }

  // Edit modal methods
  openEditModal(emp: Employee): void {
    this.editingEmployee = {
      id: emp.id,
      name: emp.name,
      position: emp.position,
      departmentId: emp.department.id,
      role: emp.role,
      productivityScore: emp.productivityScore,
      payRate: emp.payRate
    };
  }

  closeEditModal(): void {
    if (this.isSavingEdit) return;
    this.editingEmployee = null;
  }

  saveEdit(): void {
    if (!this.editingEmployee) return;
    this.isSavingEdit = true;

    setTimeout(() => {
      if (!this.editingEmployee) return;
      const dept = this.departments.find(d => d.id === Number(this.editingEmployee?.departmentId)) || {
        id: Number(this.editingEmployee.departmentId),
        name: 'General'
      };

      const index = this.employees.findIndex(e => e.id === this.editingEmployee?.id);
      if (index !== -1) {
        this.employees[index] = {
          ...this.employees[index],
          name: this.editingEmployee.name,
          position: this.editingEmployee.position,
          department: dept,
          role: this.editingEmployee.role,
          productivityScore: this.editingEmployee.productivityScore !== null && this.editingEmployee.productivityScore !== undefined ? Number(this.editingEmployee.productivityScore) : null,
          payRate: this.editingEmployee.payRate !== null && this.editingEmployee.payRate !== undefined ? Number(this.editingEmployee.payRate) : null
        };
      }

      this.isSavingEdit = false;
      this.editingEmployee = null;
    }, 300);
  }

  // Add modal methods
  openAddModal(): void {
    this.newEmployee = this.getInitialAddForm();
    this.isAddModalOpen = true;
  }

  closeAddModal(): void {
    if (this.isAdding) return;
    this.isAddModalOpen = false;
  }

  saveNewEmployee(): void {
    if (!this.newEmployee.name.trim() || !this.newEmployee.position.trim()) return;
    this.isAdding = true;

    setTimeout(() => {
      const dept = this.departments.find(d => d.id === Number(this.newEmployee.departmentId)) || {
        id: Number(this.newEmployee.departmentId),
        name: 'General'
      };

      const nextId = this.employees.length > 0 ? Math.max(...this.employees.map(e => e.id)) + 1 : 1;

      const created: Employee = {
        id: nextId,
        name: this.newEmployee.name.trim(),
        position: this.newEmployee.position.trim(),
        department: dept,
        role: this.newEmployee.role,
        productivityScore: this.newEmployee.productivityScore !== null && this.newEmployee.productivityScore !== undefined ? Number(this.newEmployee.productivityScore) : null,
        payRate: this.newEmployee.payRate !== null && this.newEmployee.payRate !== undefined ? Number(this.newEmployee.payRate) : null
      };

      this.employees.unshift(created);
      this.isAdding = false;
      this.isAddModalOpen = false;
    }, 300);
  }
}
