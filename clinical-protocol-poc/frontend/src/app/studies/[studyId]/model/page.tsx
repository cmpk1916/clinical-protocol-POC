import { redirect } from "next/navigation";

export default async function ModelPage({
  params,
}: Readonly<{ params: Promise<{ studyId: string }> }>) {
  const { studyId } = await params;
  redirect(`/studies/${encodeURIComponent(studyId)}/review`);
}
