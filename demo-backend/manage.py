#!/usr/bin/env python
"""Dev-only Django project: a realistic DRF + drf-spectacular backend.

Purpose: produce a REAL OpenAPI schema fixture for the admin app tests,
and act as the backend for browser E2E testing. NOT the user's production
cloud API — config.json in app/ points the thin client anywhere.
"""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    # The rig's INSTALLED_APPS names the plugin, and `pip install -e ../plugin` is
    # impossible on a lane without setuptools — boot it from this checkout.
    from core.devpaths import ensure_admincraft_on_path
    ensure_admincraft_on_path()
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
