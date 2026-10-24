import type { Metadata } from "next";
import { JobsWorkspace } from "@/app/_components/jobs-workspace";
export const metadata: Metadata = { title: "Jobs", description: "Manage GM Studio editing work." };
export default function JobsPage() { return <JobsWorkspace />; }
