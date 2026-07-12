import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function UnityClientRetiredPage({ params }: { params: { id: string } }) {
  redirect(`/projects/${encodeURIComponent(params.id)}/robotics`);
}
