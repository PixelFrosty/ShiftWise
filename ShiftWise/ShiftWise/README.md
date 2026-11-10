# ShiftWise

ShiftWise is a web-based tool designed to reduce the time and effort managers spend building employee schedules. Its primary users are managers and team leads. Employees are indirect users who submit their availability and skills. The core functionality includes an algorithm that weighs availability, skill fit, productivity, and project importance to assign employees to shifts, a manager dashboard with a calendar/grid view for reviewing and manually overriding generated schedules, an employee-facing form for submitting availability updates, and error-flagging for issues like understaffing or double-booking.

# Technologies Used

- Django
- Angular
- PostgreSQL
- Podman

# Installation & Development

## 1. Prerequisites
### Install Podman

#### Windows
Podman's official documentation recommends using **WSL** to run Podman on windows.
A tutorial for installing WSL can be found [here.](https://learn.microsoft.com/en-us/windows/wsl/install) Once WSL is installed, you can follow the Linux instructions.

#### Linux
Podman can be installed using most package managers. 

On Ubuntu for example, you can install it with:
```bash
sudo apt install podman
sudo apt install podman-compose 
```

Podman-compose can alternatively be installed using the python package manager pip:
```bash
pip3 install podman-compose --user
```

#### MacOS
Podman recommends using the official installer for MacOS which can be found [here.](https://podman.io/)

## 2. Clone the Repository

Clone the repository using either Bash or the Desktop App. 
```bash
git clone https://github.com/PixelFrosty/ShiftWise.git
```

## 3. Running the Stack

```bash
# Go to the project root folder
cd ShiftWise

# Start both containers
# --build is for first time usage and when making changes
podman-compose up --build
# When not making changes to code, you can omit --build,
# use -d at the end to run in background

# Run Django Migrations (also needed after pulling new changes, e.g. the Projects tables)
podman-compose exec backend python manage.py migrate

# Create a Django Admin
podman-compose exec backend python manage.py createsuperuser

# To stop the containers, run the following command
# You will need another terminal if not ran in the background.
podman-compose down

# Active containers can be checked using
podman ps
```

## 4. Accessing the Application

Once the stack is running, you can access the frontend by navigating to `http://localhost:4200` in your web browser.
The backend API calls and Admin page can be accessed at `http://localhost:8000` followed by `/admin/` or the relevant API call.

## Roles and demo data

There are three roles: **General Manager** (creates the company and its departments, has every permission), **Manager** (edits the schedule for the departments the General Manager gave them, sees their employees, answers time-off requests, makes employee join codes) and **Employee** (read-only schedule for their department and their weekly hours, submits and tracks their own time off, can ask coworkers to give away, take or swap shifts).
People sign up as a General Manager (new company) or join an existing company with a single-use **join code** made by the General Manager (manager or employee codes) or a manager (employee codes).
The General Manager is stored in the database as the role `ceo`.

A full description of the code, database, API and every page is in [`ShiftWise_Technical_Documentation.pdf`](../ShiftWise_Technical_Documentation.pdf).

To wipe the database and load mock data for testing (this deletes every account and company!):
```bash
podman-compose exec backend python manage.py reset_demo_data --yes
```
The demo data posts the current week and leaves next week as a draft so the posting flow can be tried. It prints the test logins (all use the password `ShiftWise123!`): `ceo@example.com`, `manager@example.com`, `manager2@example.com`, `employee@example.com`, `employee2@example.com`, plus a few unused join codes.

### Posting a schedule
A week of a department is a **draft** until a manager of that department or the General Manager posts it. Employees only see posted weeks (they get a "not posted yet" message). Posting goes through a **review summary** (open spots and warnings) and then a **confirmation popup**. After a week is posted, edits go live at once and only the people affected are notified. Managers and the General Manager can view every department, but only edit the ones they run.

### Availability, warnings and offering shifts
- When an employee changes their availability, the managers of their department and the General Manager get an alert (one alert for a burst of edits).
- Scheduling someone outside their availability (or outside the hours of operation) asks "are you sure?" first; the same warnings are listed in the review step before posting.
- Besides giving a shift to one coworker, an employee can **Offer to everyone**: everyone in the department is notified and the first to accept gets the shift.

### Extra departments
Each person has one **home** department and can also work in extra departments (set in the Employees page by the General Manager or the home manager). The auto-scheduler only fills the home department; a manager schedules the person in other departments by hand.

### Projects (optional)
The **Projects** tab lets managers and the General Manager create projects (for a department or the whole company), add milestones (title, description, due date, status) and assign several people to each. Everyone can see the projects of their departments and the company-wide ones, with all milestones, but only managers see who is assigned. Employees see their own milestones highlighted and can change the status of only their own. Nothing else depends on it; with no projects the page just shows an empty state.

### Compatibility scores
In the **Employees** page, managers and the General Manager tick two or more people and choose **Rate compatibility** to give the group one score from 1 to 10 for how well they work together. Rating the same people again replaces the score. Managers only see and rate people in the departments they manage; employees cannot see scores.

### Full time, part time and minors
- Managers and the General Manager mark each employee **full time** (40 hours a week) or **part time** (5-39 hours) in the Employees page, and can tick **Allow overtime** for full-time people so they may be scheduled over 40 hours.
- The birth date is used to work out age. Anyone **under 18** has a yellow name on the schedule (everyone else is green). Roster-only people (no login) get a birth date when they are added or edited.
- Scheduling someone past their weekly hour limit, or a minor for more than 8 hours in a day, more than 18 hours in a week, or past 9 PM, asks the manager "are you sure?" first.

### Auto-schedule
On the Weekly Schedule, managers and the General Manager can press **Auto-schedule** to fill the open spots of the viewed week and department (people already on shifts stay). The best productivity scores are placed first, using each person's availability, approved time off and hour limits, and these compatibility rules: **1-3** avoid pairing unless completely necessary, **4-6** okay but other options are tried first, **7-10** pair them if possible. Overtime is only used as a last resort. If any time-off requests for that week are still pending, a popup asks whether to continue first.

### Weekly schedule
- The **General Manager** sets the company's **hours of operation** (one open/close time for every day). Shifts must fall inside those hours.
- **Managers and the General Manager** add shifts (date, start, end, number of people needed), save reusable **shift templates** and apply them to days of the viewed week, and assign people by name. If someone has approved time off that day, a warning asks *"(Name)'s request off was approved, are you sure you would like to schedule them?"* with Yes/No.
- **Employees** open a shift to **give away** their shift, **take** a coworker's shift, or **swap** shifts. Only the other employee has to accept; the department's managers (or the General Manager) get a notification saying what happened.

## Notes

Packages for python and node can be installed from within the running containers or outside the containers assuming all dependancies are installed locally on your machine.
The container terminals can be accessed using the following:
```bash
podman-compose exec frontend bash
podman-compose exec backend bash
# You can also substitude "bash" for any command you'd regularly use within the terminal
# For example, you can list the backend's current directory using:
podman-compose exec backend ls
```
Before committing changes, run the following command to add python packages to the `requirements.txt`
```bash
podman-compose exec backend pip freeze > backend/requirements.txt
```


WIP

# Team

- Eli Wilburn
- Ethan Gretna
- Hunter Aden
- Kaitlyn Young

## Mentors

- Leo Malacaman
- Steele Russell
- Parker Chiasson
- Chris Derouen
