import type { Metadata } from "next";

import { LearningDashboard } from "@/app/_components/learning-dashboard";

export const metadata: Metadata = {
  title: "Learning loop",
  description: "Review the local evidence GM Studio uses to improve future edits.",
};

export default function LearningPage() {
  return <LearningDashboard />;
}
