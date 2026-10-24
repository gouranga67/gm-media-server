import type { Metadata } from "next";

import { MediaLibrary } from "@/app/_components/media-library";

export const metadata: Metadata = {
  title: "Media library",
  description: "Search, organize, and safely archive private source media in GM Studio.",
};

export default function MediaLibraryPage() {
  return <MediaLibrary />;
}
