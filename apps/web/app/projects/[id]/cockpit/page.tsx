import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default function ProjectCockpitRetiredPage({ params }: { params: { id: string } }) {
  redirect(`/projects/${encodeURIComponent(params.id)}/2d-upgrade`);
}
