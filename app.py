from flask import Flask, request, jsonify, redirect, url_for, session
import os, json
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# ===== Config =====
LOCAL_DATA_FOLDER = "/tmp/data"
os.makedirs(LOCAL_DATA_FOLDER, exist_ok=True)

CLIENT_SECRETS_FILE = "credentials.json"
TOKEN_FILE = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "/tmp/token.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
REDIRECT_URI = "/oauth2callback"

# Drive folder ID where JSON files will be uploaded
FOLDER_ID = "1uun13tmNf1b7RvixKku9jIQ8pu8Zncaq"

# ===== Write OAuth client secret to file =====
with open(CLIENT_SECRETS_FILE, "w") as f:
    f.write(os.environ["GOOGLE_OAUTH_JSON"])

# ===== Routes =====
@app.route("/")
def home():
    return "Flask JSON → Google Drive via OAuth 🚀", 200

@app.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=request.url_root[:-1] + REDIRECT_URI
    )
    auth_url, state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    session["state"] = state
    return redirect(auth_url)

@app.route(REDIRECT_URI)
def oauth2callback():
    state = session["state"]
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state,
        redirect_uri=request.url_root[:-1] + REDIRECT_URI
    )
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # Save token to file for future use
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    return "Authorization successful! You can now POST JSON to /upload-json."

def get_drive_service():
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        raise RuntimeError("No OAuth token found. Visit /authorize first.")

    # Refresh if needed
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        # Save refreshed token
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)

@app.route("/upload-json", methods=["POST"])
def upload_json():
    try:
        drive_service = get_drive_service()
        data = request.get_json(force=True)

        # Save locally
        filename = f"{LOCAL_DATA_FOLDER}/data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)

        # Upload to specified Drive folder
        file_metadata = {
            "name": os.path.basename(filename),
            "parents": [FOLDER_ID]
        }
        media = MediaFileUpload(filename, mimetype="application/json")
        uploaded = drive_service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()

        return jsonify({
            "status": "success",
            "saved_local": filename,
            "uploaded_file_id": uploaded.get("id")
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# ===== Run App =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
