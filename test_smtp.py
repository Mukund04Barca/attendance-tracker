import os
import smtplib
from dotenv import load_dotenv

load_dotenv(".env")

email = os.getenv("EMAIL_HOST_USER")
password = os.getenv("EMAIL_HOST_PASSWORD")
host = os.getenv("EMAIL_HOST") or "smtp.gmail.com"
port = int(os.getenv("EMAIL_PORT") or 587)

print(f"Testing connection for {email} on {host}:{port}...")

try:
    server = smtplib.SMTP(host, port)
    server.starttls()
    server.login(email, password)
    print("Login successful!")
    server.quit()
except Exception as e:
    print(f"Login failed: {e}")
