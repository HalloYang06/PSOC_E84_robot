import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function Retired3dDevModePage() {
  redirect("/projects");
}
