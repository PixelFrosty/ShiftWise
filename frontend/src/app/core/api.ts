// Mockoon mock API base URL (port 3000).
// Explicitly uses 127.0.0.1 on localhost to avoid rootless Podman IPv6 connection reset issues.
const host = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? '127.0.0.1'
  : window.location.hostname;

// Defaults to Mockoon (port 3000). To use the real Django backend, add "?backend=true" to the URL.
const useBackend = window.location.search.includes('backend=true');
const port = useBackend ? '8000' : '3000';

export const API_URL = `${window.location.protocol}//${host}:${port}/api`;
