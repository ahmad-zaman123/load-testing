"""Read-only scenario — communications app.

Two GET endpoints: the user's notification feed and their notification
preferences. Seeded users have no notifications (feed is empty but still
exercises the paginated query); preferences are auto-created per user.
"""

from locust import between, tag, task

from common import AuthenticatedHttpUser, read_wait


@tag("reads", "communications", "read")
class CommunicationsReadUser(AuthenticatedHttpUser):
    wait_time = read_wait()

    @task(8)
    def notifications(self):
        self.client.get(
            "/communications/notifications/",
            name="GET /communications/notifications/",
        )

    @task(5)
    def notification_preferences(self):
        self.client.get(
            "/communications/notification-preferences/",
            name="GET /communications/notification-preferences/",
        )
