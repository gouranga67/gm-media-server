import type { Metadata } from "next";

import { JobPreview } from "@/app/_components/job-preview";

export const metadata: Metadata = {
  title: "Edit preview",
  description: "Review and download a source-led GM Studio edit.",
};

export default async function JobPreviewPage({
  params,
}: {
  readonly params: Promise<{ readonly jobId: string }>;
}) {
  const { jobId } = await params;
  return <JobPreview jobId={jobId} />;
}
