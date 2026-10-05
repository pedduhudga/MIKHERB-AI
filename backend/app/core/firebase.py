import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("mikherb.firebase")

_firebase_initialized: bool = False
_firebase_auth_client = None
_firestore_client = None

def init_firebase() -> bool:
    """
    Optionally initializes the Firebase Admin SDK if credentials or environment are provided.
    Does not crash if credentials are absent, allowing local-first operation.
    """
    global _firebase_initialized, _firebase_auth_client, _firestore_client
    if _firebase_initialized:
        return True

    try:
        import firebase_admin
        from firebase_admin import credentials, auth, firestore

        cred = None
        service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        service_account_raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY")

        if service_account_path and os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            logger.info(f"Loaded Firebase credentials from file: {service_account_path}")
        elif service_account_raw:
            try:
                cert_dict = json.loads(service_account_raw)
                cred = credentials.Certificate(cert_dict)
                logger.info("Loaded Firebase credentials from environment JSON string")
            except Exception as e:
                logger.warning(f"Could not parse FIREBASE_SERVICE_ACCOUNT_KEY: {e}")
        elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
            cred = credentials.ApplicationDefault()
            logger.info("Loaded Firebase credentials from default Google application credentials")

        if cred:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            _firebase_auth_client = auth
            _firestore_client = firestore.client()
            _firebase_initialized = True
            logger.info("Firebase Admin successfully initialized")
            return True
        else:
            logger.info("No Firebase Admin credentials provided. Running in local SQLite mode.")
            return False

    except Exception as exc:
        logger.warning(f"Firebase Admin initialization skipped/failed: {exc}")
        return False

def is_firebase_active() -> bool:
    return _firebase_initialized

def verify_firebase_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies a Firebase Auth ID token if Firebase Admin is active.
    Returns decoded token dictionary or None.
    """
    if not _firebase_initialized or not _firebase_auth_client:
        return None
    try:
        decoded = _firebase_auth_client.verify_id_token(id_token)
        return decoded
    except Exception as e:
        logger.warning(f"Failed to verify Firebase token: {e}")
        return None

def sync_project_to_firestore(project_data: Dict[str, Any]) -> bool:
    """
    Syncs a Project document to Firestore under 'projects' collection if Firebase is active.
    """
    if not _firebase_initialized or not _firestore_client:
        return False
    try:
        project_id = str(project_data.get("id", project_data.get("name", "unknown")))
        doc_ref = _firestore_client.collection("projects").document(project_id)
        doc_ref.set(project_data, merge=True)
        return True
    except Exception as e:
        logger.warning(f"Error syncing project to Firestore: {e}")
        return False
