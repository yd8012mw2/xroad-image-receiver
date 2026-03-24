import base64
import imghdr
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request, send_from_directory


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>X-Road Image Receiver</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3efe8;
      --surface: rgba(255, 252, 245, 0.9);
      --border: #d5c7ae;
      --ink: #2d2419;
      --muted: #6f5c46;
      --accent: #c45c2e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(196, 92, 46, 0.15), transparent 34%),
        linear-gradient(135deg, #efe4d3 0%, #f7f3ea 45%, #ece7df 100%);
      display: grid;
      place-items: center;
      padding: 24px;
    }
    main {
      width: min(960px, 100%);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 24px;
      box-shadow: 0 24px 60px rgba(77, 50, 23, 0.12);
      overflow: hidden;
    }
    header {
      padding: 28px 28px 12px;
    }
    h1 {
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3rem);
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.6;
    }
    .frame {
      padding: 20px 28px 28px;
    }
    .image-shell {
      aspect-ratio: 16 / 10;
      width: 100%;
      border-radius: 18px;
      border: 1px solid var(--border);
      background: linear-gradient(180deg, rgba(255,255,255,0.7), rgba(239,228,211,0.6));
      display: grid;
      place-items: center;
      overflow: hidden;
      position: relative;
    }
    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: none;
      background: #fffaf2;
    }
    .empty {
      text-align: center;
      color: var(--muted);
      padding: 24px;
      font-size: 1.1rem;
    }
    .meta {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .card {
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: rgba(255, 250, 242, 0.84);
    }
    .label {
      display: block;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }
    .value {
      font-size: 1rem;
      word-break: break-word;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Latest X-Road Image</h1>
      <p>The page shows only the newest received image. Stored files are capped at six and rotated automatically.</p>
    </header>
    <section class="frame">
      <div class="image-shell">
        <img id="latest-image" alt="Latest received image">
        <div class="empty" id="empty-state">No image received yet.</div>
      </div>
      <div class="meta">
        <div class="card">
          <span class="label">Filename</span>
          <span class="value" id="filename">-</span>
        </div>
        <div class="card">
          <span class="label">Received At</span>
          <span class="value" id="received-at">-</span>
        </div>
        <div class="card">
          <span class="label">Status</span>
          <span class="value" id="status">Waiting for data</span>
        </div>
      </div>
    </section>
  </main>
  <script>
    const pollIntervalMs = {{ poll_interval_ms }};
    let lastImagePath = null;

    async function refreshLatestImage() {
      const response = await fetch("/api/latest", { cache: "no-store" });
      const data = await response.json();

      const image = document.getElementById("latest-image");
      const emptyState = document.getElementById("empty-state");
      const filename = document.getElementById("filename");
      const receivedAt = document.getElementById("received-at");
      const status = document.getElementById("status");

      if (!data.latest_image) {
        image.style.display = "none";
        emptyState.style.display = "block";
        filename.textContent = "-";
        receivedAt.textContent = "-";
        status.textContent = "Waiting for data";
        lastImagePath = null;
        return;
      }

      if (data.latest_image.url !== lastImagePath) {
        image.src = data.latest_image.url + "?v=" + encodeURIComponent(data.latest_image.received_at);
        lastImagePath = data.latest_image.url;
      }

      image.style.display = "block";
      emptyState.style.display = "none";
      filename.textContent = data.latest_image.original_filename;
      receivedAt.textContent = data.latest_image.received_at;
      status.textContent = "Last receive completed successfully";
    }

    refreshLatestImage().catch(console.error);
    setInterval(() => {
      refreshLatestImage().catch(console.error);
    }, pollIntervalMs);
  </script>
</body>
</html>
"""


@dataclass
class ReceiverConfig:
    app_host: str
    app_port: int
    received_dir: Path
    max_stored_images: int
    ui_poll_interval_sec: int


def load_config() -> ReceiverConfig:
    load_dotenv()
    received_dir = Path(os.getenv("RECEIVED_DIR", "./received")).expanduser()
    max_stored_images = int(os.getenv("MAX_STORED_IMAGES", "6"))
    ui_poll_interval_sec = int(os.getenv("UI_POLL_INTERVAL_SEC", "3"))
    if max_stored_images < 1:
        raise ValueError("MAX_STORED_IMAGES must be at least 1.")
    if ui_poll_interval_sec < 1:
        raise ValueError("UI_POLL_INTERVAL_SEC must be at least 1.")

    return ReceiverConfig(
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=int(os.getenv("APP_PORT", "5000")),
        received_dir=received_dir,
        max_stored_images=max_stored_images,
        ui_poll_interval_sec=ui_poll_interval_sec,
    )


class ImageStore:
    def __init__(self, received_dir: Path, max_stored_images: int) -> None:
        self.received_dir = received_dir
        self.max_stored_images = max_stored_images
        self.lock = threading.Lock()
        self.received_dir.mkdir(parents=True, exist_ok=True)

    def latest_image(self) -> Optional[Dict[str, str]]:
        with self.lock:
            return self._latest_image_unlocked()

    def save_image(self, payload: Dict[str, str]) -> Dict[str, str]:
        raw_bytes = self._decode_image(payload["image_base64"])
        extension = self._resolve_extension(payload["filename"], payload["content_type"], raw_bytes)
        safe_original_name = Path(payload["filename"]).name
        stored_name = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
            f"__{uuid4().hex}__{safe_original_name}"
        )
        stored_name = Path(stored_name).with_suffix(extension).name
        target_path = self.received_dir / stored_name

        with self.lock:
            target_path.write_bytes(raw_bytes)
            logging.info("Stored image path=%s received_at=%s", target_path, datetime.now(timezone.utc).isoformat())
            self._prune_old_images()
            latest = self._latest_image_unlocked()

        if latest is None:
            raise RuntimeError("Latest image state not available after save.")
        return latest

    def _decode_image(self, image_base64: str) -> bytes:
        try:
            return base64.b64decode(image_base64, validate=True)
        except Exception as exc:
            raise ValueError("Invalid Base64 image payload.") from exc

    def _resolve_extension(self, filename: str, content_type: str, raw_bytes: bytes) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png"}:
            return suffix

        if content_type == "image/jpeg":
            return ".jpg"
        if content_type == "image/png":
            return ".png"

        detected = imghdr.what(None, h=raw_bytes)
        if detected == "jpeg":
            return ".jpg"
        if detected == "png":
            return ".png"
        raise ValueError("Unsupported image type. Only JPEG and PNG are allowed.")

    def _prune_old_images(self) -> None:
        images = self._list_images()
        while len(images) > self.max_stored_images:
            oldest = images.pop(0)
            oldest.unlink(missing_ok=True)
            logging.info("Deleted old image path=%s", oldest)

    def _latest_image_unlocked(self) -> Optional[Dict[str, str]]:
        images = self._list_images()
        if not images:
            return None

        latest_path = images[-1]
        received_at = datetime.fromtimestamp(
            latest_path.stat().st_mtime, tz=timezone.utc
        ).isoformat()
        original_filename = self._extract_original_filename(latest_path.name)
        return {
            "stored_filename": latest_path.name,
            "original_filename": original_filename,
            "received_at": received_at,
            "url": f"/images/{latest_path.name}",
        }

    def _extract_original_filename(self, stored_name: str) -> str:
        parts = stored_name.split("__", 2)
        if len(parts) == 3:
            return parts[2]
        return stored_name

    def _list_images(self) -> List[Path]:
        images = [
            path
            for path in self.received_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ]
        return sorted(images, key=lambda path: path.stat().st_mtime)


def validate_payload(payload: Dict[str, str]) -> Tuple[bool, Optional[str]]:
    required_fields = {
        "image_id",
        "filename",
        "content_type",
        "sent_at",
        "image_base64",
    }
    missing = sorted(field for field in required_fields if not payload.get(field))
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"
    return True, None


def create_app() -> Flask:
    config = load_config()
    image_store = ImageStore(
        received_dir=config.received_dir,
        max_stored_images=config.max_stored_images,
    )

    app = Flask(__name__)
    app.config["IMAGE_STORE"] = image_store
    app.config["RECEIVER_CONFIG"] = config

    @app.get("/")
    def index():
        return render_template_string(
            HTML_TEMPLATE,
            poll_interval_ms=config.ui_poll_interval_sec * 1000,
        )

    @app.get("/api/latest")
    def latest():
        latest_image = image_store.latest_image()
        return jsonify({"latest_image": latest_image})

    @app.post("/api/images")
    def receive_image():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            logging.error("Invalid request body: JSON object expected.")
            return jsonify({"error": "JSON object body is required."}), 400

        is_valid, error_message = validate_payload(payload)
        if not is_valid:
            logging.error("Payload validation failed: %s", error_message)
            return jsonify({"error": error_message}), 400

        try:
            latest_image = image_store.save_image(payload)
        except ValueError as exc:
            logging.error("Image decode/save failed: %s", exc)
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            logging.exception("Unexpected error while storing image.")
            return jsonify({"error": "Internal server error.", "detail": str(exc)}), 500

        return jsonify(
            {
                "message": "Image received successfully.",
                "latest_image": latest_image,
            }
        ), 201

    @app.get("/images/<path:filename>")
    def serve_image(filename: str):
        return send_from_directory(config.received_dir, filename)

    return app


app = create_app()


if __name__ == "__main__":
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    receiver_config = app.config["RECEIVER_CONFIG"]
    app.run(
        host=receiver_config.app_host,
        port=receiver_config.app_port,
        debug=False,
    )
