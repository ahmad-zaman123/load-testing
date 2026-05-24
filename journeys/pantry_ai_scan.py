"""Journey: Pantry AI Scan.

User opens their pantry, scans a few items by taking photos, waits for the
AI to identify them, and bulk-confirms the scanned items into their pantry.

Hits Gemini image generation + classification. **Requires LOAD_TEST_MODE=true**
on the backend — otherwise real Gemini calls fire.

The image upload here is a placeholder PNG, not a real photo of food. The
mock Gemini client returns canned data regardless; the goal is to exercise
the upload path, scan-session lifecycle, and bulk-create write path.
"""

import io
import random
import time
import uuid

from locust import SequentialTaskSet, between, tag, task

from common import AuthenticatedHttpUser


def _tiny_png_bytes():
    """A 1x1 transparent PNG. Smallest valid payload to exercise the upload
    multipart parsing without bloating the test."""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
        b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfa\xcf"
        b"\x00\x00\x00\x02\x00\x01\xe5'\xde\xfc\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@tag("journey", "pantry", "scan")
class PantryScanTasks(SequentialTaskSet):
    def on_start(self):
        self.scan_session_id = None
        self.images_uploaded = 0

    # --- step 1: user opens pantry ------------------------------------

    @task
    def view_pantry(self):
        self.client.get(
            "/pantry/list/",
            name="01 GET /pantry/list/",
        )

    # --- step 2: user taps "scan" and uploads images ------------------

    @task
    def upload_scan_images(self):
        """Real user uploads 1-4 photos in one session. We loop the upload
        endpoint for that many images."""
        num_images = random.randint(1, 4)
        for i in range(num_images):
            png = _tiny_png_bytes()
            files = {"image": (f"pantry-{uuid.uuid4().hex[:8]}.png", io.BytesIO(png), "image/png")}
            with self.client.post(
                "/pantry/scan/",
                files=files,
                name="02 POST /pantry/scan/ (image upload)",
                catch_response=True,
            ) as r:
                if r.status_code not in (200, 201, 202):
                    # Could be a payload-shape mismatch — note but don't abort
                    r.failure(f"scan upload returned {r.status_code}")
                    continue
                self.images_uploaded += 1
                try:
                    body = r.json()
                    if self.scan_session_id is None:
                        # First upload returns the new scan session
                        self.scan_session_id = body.get("id") or body.get("scan_session_id")
                except ValueError:
                    pass

    # --- step 3: user waits + polls scan status -----------------------

    @task
    def poll_scan_status(self):
        if not self.scan_session_id:
            self.interrupt()
            return
        # Realistic polling: user waits ~3s and refreshes once or twice
        for _ in range(2):
            time.sleep(random.uniform(1.5, 3.0))
            self.client.get(
                f"/pantry/scan/{self.scan_session_id}/",
                name="03 GET /pantry/scan/[uuid]/ (status poll)",
            )

    # --- step 4: user confirms detected items into pantry -------------

    @task
    def bulk_create_from_scan(self):
        if not self.scan_session_id:
            self.interrupt()
            return
        # Real flow would pick from `body.matched_products`; we send a
        # minimal payload — backend should accept or 400 cleanly.
        with self.client.post(
            f"/pantry/scan/{self.scan_session_id}/items/",
            json={"items": []},
            name="04 POST /pantry/scan/[uuid]/items/ (bulk create)",
            catch_response=True,
        ) as r:
            if r.status_code == 400:
                # Empty items list likely rejected — that's fine for a smoke
                r.success()

    # --- step 5: user leaves ------------------------------------------

    @task
    def end(self):
        time.sleep(random.uniform(0.5, 2.0))
        self.interrupt(reschedule=False)


class PantryScanUser(AuthenticatedHttpUser):
    wait_time = between(1.0, 3.0)
    tasks = [PantryScanTasks]
