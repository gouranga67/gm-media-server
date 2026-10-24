import type { Metadata } from "next";
import { Onboarding } from "@/app/_components/onboarding";
export const metadata: Metadata = { title: "Welcome", description: "Set up GM Studio." };
export default function WelcomePage() { return <Onboarding />; }
