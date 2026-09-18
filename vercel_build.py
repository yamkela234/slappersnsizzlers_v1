"""Build step for Vercel: apply migrations and seed the menu (collectstatic is run by Vercel)."""
import subprocess
import sys

for command in (["migrate", "--noinput"], ["seed_menu"]):
    subprocess.run([sys.executable, "manage.py", *command], check=True)
