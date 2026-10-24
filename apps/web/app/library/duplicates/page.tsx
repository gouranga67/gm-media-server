import type { Metadata } from "next";

import { DuplicateAudit } from "@/app/_components/duplicate-audit";

export const metadata: Metadata = {
  title: "Exact duplicate audit",
  description: "Review byte-for-byte duplicate originals in the private GM Studio media library.",
};

export default function DuplicateAuditPage() {
  return <DuplicateAudit />;
}
