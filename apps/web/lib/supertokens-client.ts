"use client";

import SuperTokens from "supertokens-web-js";
import EmailPassword from "supertokens-web-js/recipe/emailpassword";
import EmailVerification from "supertokens-web-js/recipe/emailverification";
import Session from "supertokens-web-js/recipe/session";

let initialized = false;

export function isSupertokensFrontendEnabled() {
  return process.env.NEXT_PUBLIC_AUTH_PROVIDER?.trim().toLowerCase() === "supertokens";
}

export function getSupertokensApiDomain() {
  return process.env.NEXT_PUBLIC_SUPERTOKENS_API_DOMAIN?.trim() || "http://127.0.0.1:8000";
}

export function getSupertokensApiBasePath() {
  return process.env.NEXT_PUBLIC_SUPERTOKENS_API_BASE_PATH?.trim() || "/api/st-auth";
}

export function initSuperTokensClient() {
  if (initialized || !isSupertokensFrontendEnabled()) {
    return;
  }

  SuperTokens.init({
    appInfo: {
      appName: process.env.NEXT_PUBLIC_SUPERTOKENS_APP_NAME?.trim() || "AI协作平台",
      apiDomain: getSupertokensApiDomain(),
      apiBasePath: getSupertokensApiBasePath(),
    },
    recipeList: [
      EmailPassword.init(),
      Session.init({
        tokenTransferMethod: "cookie",
      }),
      EmailVerification.init(),
    ],
  });

  initialized = true;
}
