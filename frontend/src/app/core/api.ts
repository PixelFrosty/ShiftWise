// Real Django backend API (port 8000) by default.
// Explicitly uses 127.0.0.1 on localhost to avoid rootless Podman IPv6 connection reset issues.
const host = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  ? '127.0.0.1'
  : window.location.hostname;

// To test with Mockoon mock API, add "?mockoon=true" to the URL.
const useMockoon = window.location.search.includes('mockoon=true');
const port = useMockoon ? '3000' : '8000';

export const API_URL = `${window.location.protocol}//${host}:${port}/api`;
