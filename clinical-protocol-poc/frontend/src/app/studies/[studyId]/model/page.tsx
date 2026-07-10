import { demoModelApi } from "../../../../lib/api";
import { ModelExplorer } from "../../../../features/model/ModelExplorer";

export default async function ModelPage({
  params,
}: Readonly<{ params: Promise<{ studyId: string }> }>) {
  const { studyId } = await params;
  const model = await demoModelApi.getStudyModel(studyId);

  return <ModelExplorer model={model} />;
}
