import type { Metadata } from "next";

import { NewJobForm } from "@/app/_components/new-job-form";

export const metadata: Metadata = {
  title: "New job",
  description: "Send source footage, photos, and audio to your private editing server.",
};

export default function NewJobPage() {
  return <NewJobForm />;
}
