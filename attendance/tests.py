from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import AttendanceRecord, TimesheetActivity
from datetime import date

class AttendanceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()
        self.client.login(username='testuser', password='password123')

    def test_dashboard_load(self):
        response = self.client.get(reverse('checkin_checkout'))
        self.assertEqual(response.status_code, 200)

    def test_timesheet_load(self):
        response = self.client.get(reverse('timesheet'))
        self.assertEqual(response.status_code, 200)

    def test_invalid_timesheet_params(self):
        # Test that bad year/month don't crash the server
        response = self.client.get(reverse('timesheet'), {'year': 'abc', 'month': '99'})
        self.assertEqual(response.status_code, 200)

    def test_timesheet_save_atomic(self):
        # Simple save test
        post_data = {
            'action': 'save_timesheet',
            'act_0_srno': '1',
            'act_0_activity': 'Test Task',
            'act_0_day_1': '8',
        }
        response = self.client.post(reverse('timesheet'), post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TimesheetActivity.objects.filter(user=self.user).count(), 1)
