from flask import Flask, request, jsonify, redirect, url_for, session
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

# Use the secret files directly from Render
CLIENT_SECRETS_FILE = "web_client_secret.json"  # This file already exists in Render
TOKEN_FILE = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "/tmp/token.json")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Drive folder ID where JSON files will be uploaded
FOLDER_ID = "1uun13tmNf1b7RvixKku9jIQ8pu8Zncaq"

def get_redirect_uri():
    """Generate the correct redirect URI based on the current request"""
    if request.is_secure or 'onrender.com' in request.host:
        scheme = 'https'
    else:
        scheme = 'http'
    return f"{scheme}://{request.host}/oauth2callback"

# ===== Routes =====
@app.route("/")
def home():
    return "Flask JSON → Google Drive via OAuth 🚀", 200

@app.route("/authorize")
def authorize():
    try:
        redirect_uri = get_redirect_uri()
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Generate authorization URL with proper parameters
        auth_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent"
        )
        
        # Store state and redirect_uri in session for verification
        session["state"] = state
        session["redirect_uri"] = redirect_uri
        
        print(f"Authorization URL: {auth_url}")  # For debugging
        print(f"Redirect URI: {redirect_uri}")   # For debugging
        
        return redirect(auth_url)
        
    except FileNotFoundError:
        return jsonify({
            "status": "error", 
            "message": "Client secrets file not found. Make sure 'web_client_secret.json' is available in Render secrets."
        }), 500
    except Exception as e:
        print(f"Authorization error: {str(e)}")  # For debugging
        return jsonify({
            "status": "error",
            "message": f"Error during authorization setup: {str(e)}"
        }), 500

@app.route("/oauth2callback")
def oauth2callback():
    try:
        # Verify state parameter
        state = session.get("state")
        if not state:
            return jsonify({"status": "error", "message": "Missing state parameter"}), 400
            
        # Get the redirect URI from session
        redirect_uri = session.get("redirect_uri")
        if not redirect_uri:
            redirect_uri = get_redirect_uri()
            
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=redirect_uri
        )
        
        # Use the full URL including query parameters
        authorization_response = request.url
        
        # Handle HTTP vs HTTPS redirect mismatch
        if authorization_response.startswith('http://') and redirect_uri.startswith('https://'):
            authorization_response = authorization_response.replace('http://', 'https://', 1)
        
        flow.fetch_token(authorization_response=authorization_response)
        creds = flow.credentials
        
        # Save token to file for future use
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
            
        # Clear session data
        session.pop("state", None)
        session.pop("redirect_uri", None)
            
        return jsonify({
            "status": "success",
            "message": "Authorization successful! You can now POST JSON to /upload-json."
        }), 200
        
    except Exception as e:
        print(f"OAuth callback error: {str(e)}")  # For debugging
        return jsonify({
            "status": "error",
            "message": f"OAuth callback error: {str(e)}"
        }), 400

def get_drive_service():
    """Get authenticated Google Drive service"""
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError("No OAuth token found. Visit /authorize first.")
    
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    except Exception as e:
        raise RuntimeError(f"Invalid token file: {str(e)}")
    
    # Refresh if needed
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Save refreshed token
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
        
        # Save locally with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{LOCAL_DATA_FOLDER}/data_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=4)
        
        # Upload to specified Drive folder
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
        
        # Clean up local file to save space
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
        print(f"Upload error: {str(e)}")  # For debugging
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500

@app.route("/check-auth")
def check_auth():
    """Check if user is currently authenticated"""
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
    """Health check endpoint"""
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
