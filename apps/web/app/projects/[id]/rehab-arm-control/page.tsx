import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function RehabArmControlPage({ params }: { params: { id: string } }) {
  redirect(`/projects/${params.id}/robotics?from=legacy-rehab-arm-control`);
}
