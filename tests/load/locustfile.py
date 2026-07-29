"""
TinyIntent Load Testing with Locust

This module provides load testing scenarios for the TinyIntent API.

Usage:
    # Start TinyIntent server first
    tinyintent serve

    # Run Locust with web UI
    cd tests/load && locust -f locustfile.py --host http://localhost:8787

    # Run headless
    locust -f locustfile.py --host http://localhost:8787 --headless \
        --users 50 --spawn-rate 5 --run-time 60s

Scenarios:
    - TinyIntentUser: Standard user behavior (shortcut routes, health checks)
    - PowerUser: Heavy API usage (multiple helpers, metrics)
    - AdminUser: System operations (health, status, metrics)
"""

import json
import os
import random
from locust import HttpUser, task, between, tag


class TinyIntentUser(HttpUser):
    """
    Standard TinyIntent user simulating iPhone Shortcut interactions.

    Primarily uses the /shortcut/route endpoint with voice commands.
    """

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests

    def on_start(self):
        """Setup authentication on user start."""
        self.headers = {
            "X-Shortcut-Token": os.getenv("SHORTCUT_TOKEN", "test-token"),
            "Content-Type": "application/json"
        }

        # Sample voice commands for testing
        self.voice_commands = [
            "What's the weather like in Austin?",
            "Check my system performance",
            "Show CPU usage",
            "What's the memory status?",
            "Check network latency",
            "Show my trading positions",
            "Are there any log errors?",
            "What's the traffic like?",
            "Check system health",
            "Show disk usage",
        ]

    @task(5)
    @tag("shortcut", "critical")
    def shortcut_route(self):
        """
        Test the shortcut routing endpoint (most common operation).

        Weight: 5 (most frequent)
        """
        command = random.choice(self.voice_commands)

        with self.client.post(
            "/shortcut/route",
            json={
                "text": command,
                "return_format": "text"
            },
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 401:
                response.failure("Authentication failed")
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(3)
    @tag("route", "critical")
    def main_route(self):
        """
        Test the main routing endpoint.

        Weight: 3 (common)
        """
        command = random.choice(self.voice_commands)

        with self.client.post(
            "/route",
            json={
                "text": command,
                "route": "auto",
                "execute": False
            },
            headers=self.headers,
            catch_response=True
        ) as response:
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("status") == "success":
                        response.success()
                    else:
                        response.failure(f"API error: {data.get('status')}")
                except json.JSONDecodeError:
                    response.failure("Invalid JSON response")
            else:
                response.failure(f"Status: {response.status_code}")

    @task(1)
    @tag("health")
    def health_check(self):
        """
        Test the health endpoint.

        Weight: 1 (occasional)
        """
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")


class PowerUser(HttpUser):
    """
    Power user with heavy API usage across multiple endpoints.
    """

    wait_time = between(0.5, 2)  # Faster interactions

    def on_start(self):
        """Setup authentication and API secret."""
        self.headers = {
            "X-TinyIntent-Secret": os.getenv("TINYINTENT_SECRET", "test-secret"),
            "X-Shortcut-Token": os.getenv("SHORTCUT_TOKEN", "test-token"),
            "Content-Type": "application/json"
        }

        self.helpers = ["weather", "system_monitor", "log_tailer", "bot_guard"]

    @task(4)
    @tag("shortcut")
    def shortcut_with_helper(self):
        """Test shortcut routing with specific helper hints."""
        helper = random.choice(self.helpers)
        commands = {
            "weather": "What's the weather forecast?",
            "system_monitor": "Show system performance",
            "log_tailer": "Check recent log errors",
            "bot_guard": "Show trading status"
        }

        self.client.post(
            "/shortcut/route",
            json={
                "text": commands.get(helper, "Check status"),
                "return_format": "text"
            },
            headers=self.headers
        )

    @task(3)
    @tag("route", "execute")
    def route_with_preview(self):
        """Test route endpoint in preview mode."""
        helper = random.choice(self.helpers)

        self.client.post(
            "/route",
            json={
                "text": f"Use {helper} helper",
                "route": "act",
                "helper_id": helper,
                "execute": False  # Preview only
            },
            headers=self.headers
        )

    @task(2)
    @tag("helpers")
    def check_helper_health(self):
        """Check health of a random helper."""
        helper = random.choice(self.helpers)

        self.client.get(
            f"/helpers/health/{helper}",
            headers=self.headers
        )

    @task(2)
    @tag("metrics")
    def get_router_metrics(self):
        """Get router performance metrics."""
        self.client.get(
            "/router/metrics",
            headers=self.headers
        )

    @task(1)
    @tag("helpers")
    def list_helpers(self):
        """List all available helpers."""
        self.client.get("/helpers", headers=self.headers)


class AdminUser(HttpUser):
    """
    Admin user focusing on system operations and monitoring.
    """

    wait_time = between(2, 5)  # Less frequent, monitoring-style

    def on_start(self):
        """Setup admin authentication."""
        self.headers = {
            "X-TinyIntent-Secret": os.getenv("TINYINTENT_SECRET", "test-secret"),
            "Content-Type": "application/json"
        }

    @task(3)
    @tag("health", "monitoring")
    def health_ready(self):
        """Check readiness endpoint."""
        self.client.get("/health/ready", headers=self.headers)

    @task(2)
    @tag("metrics", "monitoring")
    def router_metrics(self):
        """Get router metrics for monitoring."""
        self.client.get("/router/metrics", headers=self.headers)

    @task(2)
    @tag("helpers", "monitoring")
    def all_helpers_health(self):
        """Check health of all helpers."""
        self.client.get("/helpers/health", headers=self.headers)

    @task(1)
    @tag("system", "monitoring")
    def system_doctor(self):
        """Run system doctor check."""
        self.client.get("/system/doctor", headers=self.headers)

    @task(1)
    @tag("router", "monitoring")
    def training_summary(self):
        """Get router training summary."""
        self.client.get("/router/train_summary", headers=self.headers)

    @task(1)
    @tag("info")
    def root_endpoint(self):
        """Check root API info."""
        self.client.get("/")


class StressTestUser(HttpUser):
    """
    Aggressive stress test user for finding breaking points.
    """

    wait_time = between(0.1, 0.5)  # Very fast requests

    def on_start(self):
        """Setup for stress testing."""
        self.headers = {
            "X-Shortcut-Token": os.getenv("SHORTCUT_TOKEN", "test-token"),
            "Content-Type": "application/json"
        }

    @task(10)
    @tag("stress", "shortcut")
    def rapid_shortcut(self):
        """Rapid-fire shortcut requests."""
        self.client.post(
            "/shortcut/route",
            json={"text": "Quick test", "return_format": "text"},
            headers=self.headers
        )

    @task(5)
    @tag("stress", "health")
    def rapid_health(self):
        """Rapid health checks."""
        self.client.get("/health")

    @task(3)
    @tag("stress", "route")
    def rapid_route(self):
        """Rapid route requests."""
        self.client.post(
            "/route",
            json={"text": "Test", "route": "auto"},
            headers=self.headers
        )
