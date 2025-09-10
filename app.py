from flask import Flask, request, jsonify
from datetime import datetime
import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

app = Flask(__name__)

# ===== CONFIG =====
FOLDER_ID = "1AbCDefGhIJklMnOpQrsTuvWxYZ12345"  # Replace with your Drive folder ID
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

SECRET_FILE_PATH = "/etc/secrets/service_account.json"

if not os.path.exists(SECRET_FILE_PATH):
    raise ValueError(f"Secret file not found at {SECRET_FILE_PATH}")

service_account_path = "service_account.json"

# Copy secret file to working directory
with open(SECRET_FILE_PATH, "r") as src:
    with open(service_account_path, "w") as dst:
        dst.write(src.read())


# ===== Initialize Google Drive Service =====
try:
    credentials = service_account.Credentials.from_service_account_file(
        service_account_path, scopes=SCOPES
    )
    drive_service = build("drive", "v3", credentials=credentials)
except Exception as e:
    raise RuntimeError(f"Failed to initialize Google Drive service: {e}")

# ===== Ensure local data folder exists =====
LOCAL_DATA_FOLDER = "data"
if not os.path.exists(LOCAL_DATA_FOLDER):
    os.makedirs(LOCAL_DATA_FOLDER)

# ===== Routes =====
@app.route("/upload-json", methods=["POST"])
def upload_json():
    try:
        data = request.get_json(force=True)

        # Save locally first
        filename = f"{LOCAL_DATA_FOLDER}/data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)

        # Upload to Google Drive
        file_metadata = {
            "name": os.path.basename(filename),
            "parents": [FOLDER_ID],
            "mimeType": "application/json"
        }
        media = MediaFileUpload(filename, mimetype="application/json")
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, parents"
        ).execute()

        return jsonify({
            "status": "success",
            "saved_local": filename,
            "uploaded_file_id": uploaded.get("id")
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/", methods=["GET"])
def home():
    return "Flask JSON → Google Drive (Render) 🚀", 200


# ===== Run App =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask app on 0.0.0.0:{port}...")
    print(f"SERVICE_ACCOUNT_JSON exists: {'SERVICE_ACCOUNT_JSON' in os.environ}")
    app.run(host="0.0.0.0", port=port)
