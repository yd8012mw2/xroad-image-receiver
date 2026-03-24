# X-Road Image Receiver

This sample program accepts image payloads through an HTTP API, stores them locally, and shows the most recently received image in a browser.

## Run

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and update values.
4. Start the receiver with `python app.py`.
5. Open `http://localhost:5000` in a browser.

## Notes

- Stored images are kept under the configured receive directory.
- The application keeps only the newest 6 files and deletes the oldest ones first.
- The page updates automatically by polling the latest-image API.
