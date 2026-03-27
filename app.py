import base64
import imghdr
import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
      width: min(1080px, 100%);
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
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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
      <p>The page shows the newest received image and the X-Road metadata that reached this provider application.</p>
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
          <span class="label">Sent At</span>
          <span class="value" id="sent-at">-</span>
        </div>
        <div class="card">
          <span class="label">Received At</span>
          <span class="value" id="received-at">-</span>
        </div>
        <div class="card">
          <span class="label">X-Road Client</span>
          <span class="value" id="xroad-client">-</span>
        </div>
        <div class="card">
          <span class="label">X-Road Service</span>
          <span class="value" id="xroad-service">-</span>
        </div>
        <div class="card">
          <span class="label">Request ID</span>
          <span class="value" id="xroad-request-id">-</span>
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

    function getDisplayValue(value) {
      return value && String(value).trim() ? value : "-";
    }

    async function refreshLatestImage() {
      const response = await fetch("/api/latest", { cache: "no-store" });
      const data = await response.json();

      const image = document.getElementById("latest-image");
      const emptyState = document.getElementById("empty-state");
      const filename = document.getElementById("filename");
      const sentAt = document.getElementById("sent-at");
      const receivedAt = document.getElementById("received-at");
      const xroadClient = document.getElementById("xroad-client");
      const xroadService = document.getElementById("xroad-service");
      const xroadRequestId = document.getElementById("xroad-request-id");
      const status = document.getElementById("status");

      if (!data.latest_image) {
        image.style.display = "none";
        emptyState.style.display = "block";
        filename.textContent = "-";
        sentAt.textContent = "-";
        receivedAt.textContent = "-";
        xroadClient.textContent = "-";
        xroadService.textContent = "-";
        xroadRequestId.textContent = "-";
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
      filename.textContent = getDisplayValue(data.latest_image.original_filename);
      sentAt.textContent = getDisplayValue(data.latest_image.sent_at);
      receivedAt.textContent = getDisplayValue(data.latest_image.received_at);
      xroadClient.textContent = getDisplayValue(data.latest_image.xroad?.client_id);
      xroadService.textContent = getDisplayValue(data.latest_image.xroad?.service_id);
      xroadRequestId.textContent = getDisplayValue(
        data.latest_image.xroad?.request_id || data.latest_image.xroad?.message_id
      );
      status.textContent = data.latest_image.xroad?.service_id
        ? "Last receive completed through X-Road"
        : "Last receive completed without X-Road headers";
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
    openapi_server_url: str


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
        openapi_server_url=os.getenv("OPENAPI_SERVER_URL", "").strip().rstrip("/"),
    )


class ImageStore:
    def __init__(self, received_dir: Path, max_stored_images: int) -> None:
        self.received_dir = received_dir
        self.max_stored_images = max_stored_images
        self.lock = threading.Lock()
        self.received_dir.mkdir(parents=True, exist_ok=True)

    def latest_image(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self._latest_image_unlocked()

    def save_image(
        self,
        payload: Dict[str, str],
        xroad_metadata: Dict[str, str],
    ) -> Dict[str, Any]:
        raw_bytes = self._decode_image(payload["image_base64"])
        extension = self._resolve_extension(payload["filename"], payload["content_type"], raw_bytes)
        safe_original_name = Path(payload["filename"]).name
        stored_name = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
            f"__{uuid4().hex}__{safe_original_name}"
        )
        stored_name = Path(stored_name).with_suffix(extension).name
        target_path = self.received_dir / stored_name
        received_at = datetime.now(timezone.utc).isoformat()
        metadata = {
            "stored_filename": target_path.name,
            "original_filename": safe_original_name,
            "received_at": received_at,
            "sent_at": payload.get("sent_at", ""),
            "image_id": payload.get("image_id", ""),
            "content_type": payload.get("content_type", ""),
            "xroad": xroad_metadata,
        }

        with self.lock:
            target_path.write_bytes(raw_bytes)
            self._write_metadata(target_path, metadata)
            logging.info(
                "Stored image path=%s received_at=%s xroad_client=%s xroad_service=%s",
                target_path,
                received_at,
                xroad_metadata.get("client_id", "-"),
                xroad_metadata.get("service_id", "-"),
            )
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

    def _metadata_path(self, image_path: Path) -> Path:
        return image_path.with_suffix(f"{image_path.suffix}.json")

    def _write_metadata(self, image_path: Path, metadata: Dict[str, Any]) -> None:
        self._metadata_path(image_path).write_text(
            json.dumps(metadata, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _load_metadata(self, image_path: Path) -> Dict[str, Any]:
        metadata_path = self._metadata_path(image_path)
        if not metadata_path.exists():
            return {}
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            logging.warning("Failed to read metadata sidecar path=%s", metadata_path)
            return {}

    def _prune_old_images(self) -> None:
        images = self._list_images()
        while len(images) > self.max_stored_images:
            oldest = images.pop(0)
            oldest.unlink(missing_ok=True)
            self._metadata_path(oldest).unlink(missing_ok=True)
            logging.info("Deleted old image path=%s", oldest)

    def _latest_image_unlocked(self) -> Optional[Dict[str, Any]]:
        images = self._list_images()
        if not images:
            return None

        latest_path = images[-1]
        metadata = self._load_metadata(latest_path)
        received_at = metadata.get("received_at") or datetime.fromtimestamp(
            latest_path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
        original_filename = metadata.get("original_filename") or self._extract_original_filename(latest_path.name)
        return {
            "stored_filename": latest_path.name,
            "original_filename": original_filename,
            "received_at": received_at,
            "sent_at": metadata.get("sent_at", ""),
            "image_id": metadata.get("image_id", ""),
            "content_type": metadata.get("content_type", ""),
            "xroad": metadata.get("xroad", {}),
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


def extract_xroad_metadata(headers: Any) -> Dict[str, str]:
    metadata = {
        "client_id": headers.get("X-Road-Client", "").strip(),
        "service_id": headers.get("X-Road-Service", "").strip(),
        "request_id": headers.get("X-Road-Request-Id", "").strip(),
        "message_id": headers.get("X-Road-Id", "").strip(),
        "user_id": headers.get("X-Road-UserId", "").strip(),
        "issue": headers.get("X-Road-Issue", "").strip(),
        "security_server": headers.get("X-Road-Security-Server", "").strip(),
        "represented_party": headers.get("X-Road-Represented-Party", "").strip(),
    }
    return {key: value for key, value in metadata.items() if value}


def build_openapi_spec(base_url: str) -> Dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "X-Road Image Receiver API",
            "version": "1.0.0",
            "description": (
                "REST endpoints for receiving image payloads behind an X-Road "
                "Security Server and inspecting the latest received image."
            ),
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/images": {
                "post": {
                    "summary": "Receive an image payload",
                    "operationId": "receiveImage",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ImagePayload"}
                            }
                        },
                    },
                    "responses": {
                        "201": {
                            "description": "Image received successfully",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ImageReceiveResponse"}
                                }
                            },
                        },
                        "400": {"description": "Invalid request"},
                        "500": {"description": "Unexpected server error"},
                    },
                }
            },
            "/api/latest": {
                "get": {
                    "summary": "Get the latest received image metadata",
                    "operationId": "getLatestImage",
                    "responses": {
                        "200": {
                            "description": "Latest image metadata",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/LatestImageResponse"}
                                }
                            },
                        }
                    },
                }
            },
            "/api/health": {
                "get": {
                    "summary": "Health check",
                    "operationId": "healthCheck",
                    "responses": {
                        "200": {
                            "description": "Receiver health information",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"},
                                            "latest_image_available": {"type": "boolean"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
        },
        "components": {
            "schemas": {
                "ImagePayload": {
                    "type": "object",
                    "required": [
                        "image_id",
                        "filename",
                        "content_type",
                        "sent_at",
                        "image_base64",
                    ],
                    "properties": {
                        "image_id": {"type": "string", "format": "uuid"},
                        "filename": {"type": "string"},
                        "content_type": {"type": "string"},
                        "sent_at": {"type": "string", "format": "date-time"},
                        "image_base64": {"type": "string"},
                    },
                },
                "XRoadMetadata": {
                    "type": "object",
                    "properties": {
                        "client_id": {"type": "string"},
                        "service_id": {"type": "string"},
                        "request_id": {"type": "string"},
                        "message_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "issue": {"type": "string"},
                        "security_server": {"type": "string"},
                        "represented_party": {"type": "string"},
                    },
                },
                "LatestImage": {
                    "type": "object",
                    "properties": {
                        "stored_filename": {"type": "string"},
                        "original_filename": {"type": "string"},
                        "received_at": {"type": "string", "format": "date-time"},
                        "sent_at": {"type": "string", "format": "date-time"},
                        "image_id": {"type": "string", "format": "uuid"},
                        "content_type": {"type": "string"},
                        "url": {"type": "string"},
                        "xroad": {"$ref": "#/components/schemas/XRoadMetadata"},
                    },
                },
                "LatestImageResponse": {
                    "type": "object",
                    "properties": {
                        "latest_image": {
                            "oneOf": [
                                {"$ref": "#/components/schemas/LatestImage"},
                                {"type": "null"},
                            ]
                        }
                    },
                },
                "ImageReceiveResponse": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "latest_image": {"$ref": "#/components/schemas/LatestImage"},
                        "xroad": {"$ref": "#/components/schemas/XRoadMetadata"},
                    },
                },
            }
        },
    }


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

    @app.get("/openapi.json")
    def openapi_spec():
        base_url = config.openapi_server_url or request.url_root.rstrip("/")
        return jsonify(build_openapi_spec(base_url))

    @app.get("/api/latest")
    def latest():
        latest_image = image_store.latest_image()
        return jsonify({"latest_image": latest_image})

    @app.get("/api/health")
    def health():
        latest_image = image_store.latest_image()
        return jsonify(
            {
                "status": "ok",
                "latest_image_available": latest_image is not None,
            }
        )

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

        xroad_metadata = extract_xroad_metadata(request.headers)
        if xroad_metadata:
            logging.info(
                "Received X-Road request client=%s service=%s request_id=%s",
                xroad_metadata.get("client_id", "-"),
                xroad_metadata.get("service_id", "-"),
                xroad_metadata.get("request_id", "-"),
            )
        else:
            logging.info("Received image request without X-Road headers.")

        try:
            latest_image = image_store.save_image(payload, xroad_metadata)
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
                "xroad": xroad_metadata,
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
