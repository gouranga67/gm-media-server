import type { Metadata } from "next";
import { AccessManager } from "@/app/_components/access-manager";
export const metadata: Metadata = { title: "People & access", description: "Manage GM Studio Tailscale access." };
export default function AccessPage() { return <AccessManager />; }
