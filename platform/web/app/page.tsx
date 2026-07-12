import { redirect } from "next/navigation";

import { getCurrentAuthState } from "../lib/server-data";

export default async function HomePage() {
  const authState = await getCurrentAuthState();
  const hasActiveSession = Boolean(authState.data?.user?.id ?? authState.data?.user?.email);

  redirect(hasActiveSession ? "/projects" : "/login");
}
