import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default function LegacyDatasetsPage({ params }: { params: { id: string } }) {
  redirect(`/projects/${params.id}/robotics?tab=dataset&from=legacy`);
}
