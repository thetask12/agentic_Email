import { LeadDetailClient } from "./lead-detail-client";

export default async function LeadPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <LeadDetailClient id={id} />;
}
