"""Shared Firebase Admin SDK initialization.

Every backend module goes through here so the app is initialized exactly once
per process. Frontend never touches Firestore/Auth — see CLAUDE.md.
"""

import os

import firebase_admin
from firebase_admin import credentials, firestore

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "steward-hackathon-505217")


def get_app() -> firebase_admin.App:
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.ApplicationDefault(), {"projectId": PROJECT_ID}
        )
    return firebase_admin.get_app()


def get_db():
    get_app()
    return firestore.client()
