import type { Metadata } from "next";

import { UsageDashboard } from "@/app/_components/usage-dashboard";

export const metadata: Metadata = {
  title: "AI usage",
  description: "Monitor model and token usage for GM Studio editing jobs.",
};

export default function UsagePage() {
  return <UsageDashboard />;
}
