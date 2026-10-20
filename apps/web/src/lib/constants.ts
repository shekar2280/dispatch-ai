export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000`
    : "http://localhost:8000");

const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

export const API_ROUTES = {
  org: {
    byId: (id: string) => `${API_BASE_URL}/api/v1/org/${id}`,
  },
  ws: {
    clinic: (orgId: string) => `${WS_BASE_URL}/api/v1/ws/clinic/${orgId}`,
  },
} as const;

export const APP_CONFIG = {
  name: "DISPATCH",
  nameAccent: "AI",
  logoPath: "/images/icon.png",
  profileIcon: "/images/profile.png",
  receptionistProfileIcon: "/images/receptionist.png",
} as const;
