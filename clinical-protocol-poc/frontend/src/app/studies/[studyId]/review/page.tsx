import { ReviewQueue } from "../../../../features/review/ReviewQueue";

export default async function ReviewPage({
  params,
}: Readonly<{ params: Promise<{ studyId: string }> }>) {
  const { studyId } = await params;
  return <ReviewQueue studyId={studyId} />;
}
