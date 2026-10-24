import type { Metadata } from "next";

import { ApplianceHealth } from "@/app/_components/appliance-health";

export const metadata: Metadata = {
  title: "System health & backup",
  description: "Read-only health and encrypted backup status for the GM Studio appliance.",
};

export default function SystemHealthPage() {
  return <ApplianceHealth />;
}
