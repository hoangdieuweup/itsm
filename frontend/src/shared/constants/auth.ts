export const AUTH_STATUS = {
  AUTHENTICATED: "authenticated",
  UNAUTHENTICATED: "unauthenticated",
} as const;

export type AuthStatus = (typeof AUTH_STATUS)[keyof typeof AUTH_STATUS];

export const AUTH_ERROR_CODE = {
  NOT_AUTHENTICATED: "auth_not_authenticated",
} as const;
