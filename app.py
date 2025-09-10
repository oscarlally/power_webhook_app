from flask import Flask, request, jsonify, redirect, session
import os, json
from datetime import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# ===== Config =====
LOCAL_DATA_FOLDER = "/tmp/data"
os.makedirs(LOCAL_DATA_FOLDER, exist_ok=True)

CLIENT_SECRETS_FILE = "web_client_secret.json"
TOKEN_FILE = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "/tmp/token.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
FOLDER_ID = "1uun13tmNf1b7RvixKku9jIQ8pu8Zncaq"

# Hardcoded redirect URI registered in Google Cloud
REDIRECT_URI = "https://power-webhook-app.onrender.com/oauth2callback"

# ===== Routes =====
@app.route("/")
def home():
    return "Flask JSON → Google Drive via OAuth 🚀", 200

@app.route("/authorize")
def authorize():
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        
        # Store state in session for verification in callback
        session["state"] = state

        print(f"Authorization URL: {auth_url}")
        return redirect(auth_url)
        
    except FileNotFoundError:
        return jsonify({
            "status": "error", 
            "message": "Client secrets file not found. Make sure 'web_client_secret.json' is available in Render secrets."
        }), 500
    except Exception as e:
        print(f"Authorization error: {str(e)}")
        return jsonify({"status": "error", "message": f"Error during authorization setup: {str(e)}"}), 500

@app.route("/oauth2callback")
def oauth2callback():
    try:
        # Verify state parameter
        state = session.get("state")
        if not state:
            return jsonify({"status": "error", "message": "Missing state parameter"}), 400
        
        # Recreate Flow with the same redirect URI and state
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=REDIRECT_URI
        )
        
        # Get the full redirect URL Google sent
        authorization_response = request.url
        
        # Force HTTPS if Google redirected via HTTP
        if authorization_response.startswith("http://") and REDIRECT_URI.startswith("https://"):
            authorization_response = authorization_response.replace("http://", "https://", 1)
        
        # Remove accidental spaces in scope parameter (if any)
        if "scope=" in authorization_response:
            parts = authorization_response.split("scope=")
            before_scope = parts[0]
            scope_value = parts[1].split("&")[0].replace(" ", "%20")
            after_scope = "&".join(parts[1].split("&")[1:])
            if after_scope:
                authorization_response = f"{before_scope}scope={scope_value}&{after_scope}"
            else:
                authorization_response = f"{before_scope}scope={scope_value}"
        
        print(f"Fetching token with URL: {authorization_response}")  # Debug
        
        # Exchange code for token
        flow.fetch_token(authorization_response=authorization_response)
        creds = flow.credentials
        
        # Save credentials to token file
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        
        # Clear session state
        session.pop("state", None)
        
        return jsonify({
            "status": "success",
            "message": "Authorization successful! You can now POST JSON to /upload-json."
        }), 200
        
    except Exception as e:
        print(f"OAuth callback error: {str(e)}")
        return jsonify({"status": "error", "message": f"OAuth callback error: {str(e)}"}), 400


def get_drive_service():
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError("No OAuth token found. Visit /authorize first.")
    
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    except Exception as e:
        raise RuntimeError(f"Invalid token file: {str(e)}")
    
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            raise RuntimeError(f"Token refresh failed: {str(e)}")
    elif creds.expired:
        raise RuntimeError("Token expired and no refresh token available. Re-authorize at /authorize")
    
    return build("drive", "v3", credentials=creds)

@app.route("/upload-json", methods=["POST"])
def upload_json():
    try:
        drive_service = get_drive_service()
        data = request.get_json(force=True)
        
        if not data:
            return jsonify({"status": "error", "message": "No JSON data received"}), 400
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{LOCAL_DATA_FOLDER}/data_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
        
        file_metadata = {
            "name": os.path.basename(filename),
            "parents": [FOLDER_ID]
        }
        
        media = MediaFileUpload(filename, mimetype="application/json")
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,name,webViewLink"
        ).execute()
        
        os.remove(filename)
        
        return jsonify({
            "status": "success",
            "uploaded_file_id": uploaded.get("id"),
            "filename": uploaded.get("name"),
            "web_view_link": uploaded.get("webViewLink")
        }), 200
        
    except RuntimeError as e:
        return jsonify({"status": "error", "message": str(e)}), 401
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500

@app.route("/check-auth")
def check_auth():
    try:
        if not os.path.exists(TOKEN_FILE):
            return jsonify({"authenticated": False, "message": "No token file found"}), 200
        
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        if creds.expired:
            if creds.refresh_token:
                return jsonify({"authenticated": False, "message": "Token expired but can be refreshed"}), 200
            else:
                return jsonify({"authenticated": False, "message": "Token expired, re-authorization needed"}), 200
        else:
            return jsonify({"authenticated": True, "message": "Ready to upload"}), 200
    except Exception as e:
        return jsonify({"authenticated": False, "message": f"Auth check failed: {str(e)}"}), 200

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

# ===== Error Handlers =====
@app.errorhandler(404)
def not_found(error):
    return jsonify({"status": "error", "message": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# ===== Run App =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=port, debug=debug)
