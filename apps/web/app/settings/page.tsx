import type { Metadata } from "next";
import { BrandProfileManager } from "@/app/_components/brand-profile-manager";

export const metadata: Metadata = { title: "Brand & presets", description: "Manage GM Studio brand kits and creative profiles." };

export default function SettingsPage() { return <BrandProfileManager />; }
