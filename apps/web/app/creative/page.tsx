import type { Metadata } from "next";
import { CreativeAssetsManager } from "@/app/_components/creative-assets-manager";

export const metadata: Metadata = { title: "Creative assets", description: "Manage licensed music, sounds, stickers, GIFs, and meme assets." };
export default function CreativeAssetsPage() { return <CreativeAssetsManager />; }
