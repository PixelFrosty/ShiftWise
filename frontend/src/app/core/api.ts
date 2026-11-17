// Backend base URL. Uses the same host the page was opened on (localhost or 127.0.0.1) so it
// always matches one of the origins allowed by CORS_ALLOWED_ORIGINS in backend/config/settings.py.
export const API_URL = `${window.location.protocol}//${window.location.hostname}:8000/api`;
