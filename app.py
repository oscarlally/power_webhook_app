from flask import Flask, request, jsonify
from datetime import datetime
import os
import json
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

app = Flask(__name__)

# ===== CONFIG =====
FOLDER_ID = "1uun13tmNf1b7RvixKku9jIQ8pu8Zncaq"  # Replace with your Drive folder ID
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# ===== WRITE SERVICE ACCOUNT SECRET TO FILE =====
service_account_path = "service_account.json"

if "SERVICE_ACCOUNT_JSON" not in os.environ:
    raise ValueError("SERVICE_ACCOUNT_JSON secret not found in environment!")

with open(service_account_path, "w") as f:
    f.write(os.environ["SERVICE_ACCOUNT_JSON"])

# ===== Google Drive Service =====
credentials = service_account.Credentials.from_service_account_file(
    service_account_path, scopes=SCOPES
)
drive_service = build("drive", "v3", credentials=credentials)

# ===== Ensure local data folder exists =====
if not os.path.exists("data"):
    os.makedirs("data")

# ===== Routes =====
@app.route("/upload-json", methods=["POST"])
def upload_json():
    try:
        data = request.get_json(force=True)

        # Save locally first
        filename = f"data/data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)

        # Upload to Google Drive
        file_metadata = {
            "name": filename,
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

# ===== Run app =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
