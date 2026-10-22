import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

export interface EmployeeSummary {
  id: number;
  name: string;
  position: string;
  department: string;
}

@Component({
  selector: 'app-employee-delete-confirm',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './employee-delete-confirm.component.html',
  styleUrl: './employee-delete-confirm.component.scss'
})
export class EmployeeDeleteConfirmComponent implements OnInit {
  employee: EmployeeSummary | null = null;
  isDeleting = false;

  // Placeholder employee lookup — replace with HttpClient call when API is ready
  private readonly placeholderEmployees: EmployeeSummary[] = [
    { id: 1, name: 'Alice Johnson',   position: 'Senior Developer',   department: 'Engineering' },
    { id: 2, name: 'Bob Martinez',    position: 'Marketing Lead',     department: 'Marketing' },
    { id: 3, name: 'Carol Williams',  position: 'Operations Manager', department: 'Operations' },
    { id: 4, name: 'David Chen',      position: 'Junior Developer',   department: 'Engineering' },
    { id: 5, name: 'Eva Thompson',    position: 'HR Coordinator',     department: 'Human Resources' },
    { id: 6, name: 'Frank Lee',       position: 'CEO',                department: 'Engineering' },
    { id: 7, name: 'Grace Kim',       position: 'Content Strategist', department: 'Marketing' },
    { id: 8, name: 'Henry Patel',     position: 'DevOps Engineer',    department: 'Engineering' }
  ];

  constructor(private route: ActivatedRoute, private router: Router) {}

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    this.employee = this.placeholderEmployees.find(e => e.id === id) ?? null;

    if (!this.employee) {
      // Employee not found — redirect back to directory
      this.router.navigate(['/employees']);
    }
  }

  onConfirmDelete(): void {
    if (!this.employee) return;
    this.isDeleting = true;

    // TODO: Replace with HttpClient.delete() call to the backend API
    // For now, simulate a brief delay then navigate back
    setTimeout(() => {
      this.isDeleting = false;
      this.router.navigate(['/employees']);
    }, 500);
  }
}
