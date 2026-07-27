from __future__ import annotations
from typing import Callable
from clipforge.models import ClipMetadata

_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _default_service_factory():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import os

    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", _SCOPES)

    if creds and not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open("token.json", "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception:
                # Refresh failed (e.g., token revoked or 7-day limit in GCP Testing state)
                creds = None
        else:
            creds = None

    if not creds:
        if os.path.exists("token.json"):
            try:
                os.remove("token.json")
            except Exception:
                pass
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secret.json", _SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)



def _default_media_factory(path: str):
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(path, chunksize=-1, resumable=True)


class YouTubeUploader:
    def __init__(self, privacy_status: str, category_id: str,
                 service_factory: Callable[[], object] = _default_service_factory,
                 media_factory: Callable[[str], object] = _default_media_factory):
        self._privacy = privacy_status
        self._category = category_id
        self._service_factory = service_factory
        self._media_factory = media_factory

    def upload(self, clip_path: str, meta: ClipMetadata) -> str:
        description = meta.description
        if "#Shorts" not in description and "#shorts" not in description:
            description = (description + "\n\n#Shorts").strip()
        body = {
            "snippet": {
                "title": meta.title,
                "description": description,
                "tags": meta.tags,
                "categoryId": self._category,
            },
            "status": {"privacyStatus": self._privacy,
                       "selfDeclaredMadeForKids": False},
        }
        try:
            service = self._service_factory()
            media = self._media_factory(clip_path)
            request = service.videos().insert(
                part="snippet,status", body=body, media_body=media)
            response = request.execute()
            return response["id"]
        except Exception as e:
            raise RuntimeError(f"youtube upload failed: {e}") from e
