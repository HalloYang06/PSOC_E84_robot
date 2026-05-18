import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function LegacyObservabilityPage({ params }: { params: { id: string } }) {
  redirect(`/projects/${params.id}/company?from=legacy`);
}
