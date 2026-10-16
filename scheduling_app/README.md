# SmartSchedule AI &bull; Intelligent Workforce Scheduling Platform

A full-stack workforce scheduling application with constraint-based automated rostering powered by **Google OR-Tools CP-SAT**, built with **Python 3.12**, **Django**, and **Tailwind CSS**.

Developed in accordance with the 6-phase engineering plan outlined in the build specification.

---

## 🏗️ Architecture & Implementation Phases

| Phase | Component | Key Capabilities |
| :--- | :--- | :--- |
| **Phase 0** | **Foundation** | Custom `User` model with `Role` (`CEO`, `MANAGER`, `EMPLOYEE`), Docker Compose for PostgreSQL, SQLite dev fallback, and core schema (`Department`, `Employee`, `EmployeeCompatibility`, `Schedule`, `Shift`, `ShiftAssignment`, `TimeOffRequest`). |
| **Phase 1** | **Employee Input & Compatibility** | Full CRUD for employees (name, department, position, contact info, productivity score, nullable pay rate, max weekly hours). Pairwise compatibility table keyed on unordered pairs (canonical `min_id, max_id`), treating missing pairs as neutral (5.0/10). |
| **Phase 2** | **Schedule Model & Manual Editor** | 7-day interactive shift calendar (Monday–Sunday). Managers define shifts with required headcounts, assign and unassign workers by hand, and transition schedule status (`Draft` &rarr; `Published` &rarr; `Archived`). |
| **Phase 3** | **Request Offs & Pile-up Spotter** | Employees submit date ranges and reasons. Managers review requests with an audit trail (who/when/notes). Includes a **per-day "people off" pile-up spotter** to detect under-coverage before approval. Approvals automatically unassign and block shifts in that range. |
| **Phase 4** | **Role Scoping (Full Backend Enforcement)** | Backend queryset and permission checks (`can_view_schedule`, `can_edit_schedule`, `role_required`). CEO sees everything; Manager sees schedules they created or department rosters; Employee sees published shifts they are assigned to. |
| **Phase 5** | **Priority Scheduling (Google OR-Tools CP-SAT)** | Mathematical constraint programming engine solving shift assignments in milliseconds. Satisfies 4 hard constraints and optimizes 2 soft constraints (productivity maximization and low-compatibility friction avoidance). |

---

## ⚡ Constraint Solver Engine (Phase 5)

The automated solver in `core/scheduler.py` uses **Google OR-Tools CP-SAT** to enforce:

### Hard Constraints (Strict Feasibility):
1. **Shift Coverage Met**: Each shift receives exactly its required `headcount_needed`.
2. **No Approved Time-Off Violated**: An employee with approved time-off overlapping a shift is strictly excluded ($x_{s, e} = 0$).
3. **No Overlapping Shifts**: An employee cannot work two shifts that overlap in time ($x_{s1, e} + x_{s2, e} \le 1$).
4. **Max Hours Per Week**: Total assigned minutes across the schedule cannot exceed $e.\text{max\_hours\_per\_week} \times 60$.

### Soft Constraints (Objective Optimization):
1. **Maximize Productivity**: Rewards high `productivity_score` employees on shifts ($\sum x_{s, e} \cdot \text{score}$).
2. **Penalize Low-Compatibility Friction**: For shifts requiring $\ge 2$ employees, pairs with compatibility $< 5.0$ incur a penalty weighted by their friction deficit ($5.0 - \text{score}$), actively preventing hostile coworkers from working together. Pairs with $> 5.0$ receive synergy bonuses.

---

## 🚀 Quick Start Guide

### 1. Activate Environment & Install Dependencies
```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Install requirements (if setting up fresh)
pip install -r requirements.txt
```

### 2. Apply Migrations & Seed Sample Data
```bash
python manage.py migrate
python manage.py seed_data
```

### 3. Run the Development Server
```bash
python manage.py runserver
```
Visit **http://127.0.0.1:8000** in your browser.

---

## 👥 Demo Accounts (Password: `password123`)

The `seed_data` command creates ready-to-test accounts:

| Role | Username | Password | Capabilities |
| :--- | :--- | :--- | :--- |
| **CEO** | `ceo` | `password123` | Organization-wide visibility, all schedules, all departments, full permission override. |
| **Manager** | `manager1` | `password123` | Manages Customer Experience department, creates schedules, runs AI auto-scheduler, reviews leave requests. |
| **Employee** | `emp1` (Alice Johnson) | `password123` | Senior Specialist (Productivity: 9.2). Views assigned shifts and submits time-off requests. |
| **Employee** | `emp2` (Bob Smith) | `password123` | Floor Associate (Productivity: 6.0). Has approved time-off on Wednesday & Thursday to test solver blocking. |

---

## 🧪 Running the Automated Test Suite

A comprehensive test suite covering all phases is included:

```bash
pytest -v
```

All 7 test suites pass covering:
- Role classification & custom user model
- Employee CRUD & pairwise compatibility symmetry
- Schedule model & manual assignment
- Time-off approval audit trail & automatic shift unassignment
- Role-based and object-level permission enforcement
- Google OR-Tools CP-SAT solver constraint satisfaction & friction penalties

---

## 🐳 Running with PostgreSQL (Docker Compose)

To run with PostgreSQL instead of SQLite:
```bash
# Start Postgres container
docker compose up -d

# Set environment variable and migrate
$env:USE_POSTGRES="True"
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```
