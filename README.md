# ShiftWise

ShiftWise is a web-based tool designed to reduce the time and effort managers spend building employee schedules. Its primary users are managers and team leads. Employees are indirect users who submit their availability and skills. The core functionality includes an algorithm that weighs availability, skill fit, productivity, and project importance to assign employees to shifts, a manager dashboard with a calendar/grid view for reviewing and manually overriding generated schedules, an employee-facing form for submitting availability updates, and error-flagging for issues like understaffing or double-booking.

# Technologies Used

- Django
- Angular
- SQLite (to be replaced with PostGre)
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

# Run Django Migrations
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
