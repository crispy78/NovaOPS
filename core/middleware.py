"""
Demo security middleware.

In DEMO_MODE, this middleware:
- Blocks all access to /admin/ (redirects to dashboard)
- Blocks new user creation
- Blocks user deletion
These restrictions prevent demo visitors from creating back-door accounts
or otherwise compromising the shared demo environment.
"""
from __future__ import annotations

import re

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect


class DemoSecurityMiddleware:
    BLOCKED_PREFIXES = ['/admin/']

    BLOCKED_POSTS = [
        re.compile(r'^/users/new/$'),
        re.compile(r'^/users/\d+/delete/$'),
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, 'DEMO_MODE', False):
            path = request.path_info

            for prefix in self.BLOCKED_PREFIXES:
                if path.startswith(prefix):
                    return redirect('dashboard')

            if request.method == 'POST':
                for pattern in self.BLOCKED_POSTS:
                    if pattern.match(path):
                        messages.warning(
                            request,
                            'This action is disabled in the demo environment.',
                        )
                        return redirect('dashboard')

        return self.get_response(request)
