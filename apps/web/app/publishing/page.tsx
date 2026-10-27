import type { Metadata } from "next";
import { PublishingDashboard } from "@/app/_components/publishing-dashboard";
export const metadata: Metadata = {
  title: "Publishing · GM Studio",
  description: "Account connections and approved reel posting.",
};
export default function Page() {
  return <PublishingDashboard />;
}
