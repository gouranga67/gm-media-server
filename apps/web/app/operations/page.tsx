import type { Metadata } from "next";
import { OperationsManager } from "@/app/_components/operations-manager";
export const metadata: Metadata = { title: "Operations", description: "Manage GM Studio usage, workload, storage, and retention." };
export default function OperationsPage() { return <OperationsManager />; }
