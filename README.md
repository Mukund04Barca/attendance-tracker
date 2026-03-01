# Attendance Tracking Web App

This is a Python **Django** + **pandas** based web application for tracking daily check-in and check-out times, computing weekly summaries, and handling holidays and allowances. It is designed to be responsive and work well on both mobile and laptop screens.

Configuration (attendance rules and logging) is driven by a YAML config file.

## Features

- **User login** using Django's built-in authentication.
- **Daily check-in / check-out** for each user.
- **Weekly summary** of worked hours using pandas.
- **Holiday awareness** from configuration (and extendable via database).
- **Allowance hours** (e.g. for special days/holidays).
- **Config-driven logging** setup via `config/settings.yaml`.

## Project structure (key files)

- `manage.py` - Django management script.
- `attendance_site/` - Django project settings and URLs.
- `attendance/` - Attendance tracking app.
- `config/settings.yaml` - YAML configuration for attendance rules and logging.
- `requirements.txt` - Python dependencies.

## Initial setup

1. **Create and activate a virtual environment**

   ```bash
   cd path/to/cursor

   python -m venv venv
   # PowerShell:
   venv\Scripts\Activate.ps1
   # Or Command Prompt:
   venv\Scripts\activate.bat
   ```

2. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

3. **Create database migrations and a superuser**

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

4. **Run the development server**

   ```bash
   python manage.py runserver
   ```

   Then open `http://127.0.0.1:8000/` in your browser.

## Configuration (`config/settings.yaml`)

The app reads configuration from `config/settings.yaml`. Example:

```yaml
attendance:
  workday_start: "09:00"
  workday_end: "18:00"
  weekly_hours_target: 40
  default_allowance_hours: 0.5

  holidays:
    - "2026-01-01"
    - "2026-12-25"

logging:
  version: 1
  disable_existing_loggers: false
  handlers:
    file:
      class: logging.FileHandler
      level: INFO
      filename: attendance.log
  loggers:
    django.request:
      handlers: [file]
      level: INFO
      propagate: true
    attendance:
      handlers: [file]
      level: INFO
      propagate: true
```

You can override the config path per environment using the `ATTENDANCE_CONFIG_FILE` environment variable.

## Usage

1. Log in at `/accounts/login/` (use the superuser or other users you create via the admin).
2. Go to the home page (`/`) to **check in / check out**.
3. View your weekly summary at `/summary/`.
4. Manage holidays and allowances via the Django admin (`/admin/`) or by editing the config file.

## Deployment (Apache overview)

For production you can deploy using **Apache + mod_wsgi** (Apache is free and open source). High-level steps:

- Install Apache and `mod_wsgi`.
- Configure a `VirtualHost` pointing to `attendance_site/wsgi.py`.
- Run `python manage.py collectstatic` and configure Apache to serve static files.
- Point your domain to the server and restart Apache.

Refer to the Django and mod_wsgi documentation for exact deployment steps.

