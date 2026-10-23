import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "GM Studio",
    short_name: "GM Studio",
    description: "Send source footage to your private editing server.",
    start_url: "/jobs/new",
    display: "standalone",
    background_color: "#f7f7f5",
    theme_color: "#173f5f",
    orientation: "portrait-primary",
    icons: [
      {
        src: "/icon.svg",
        sizes: "any",
        type: "image/svg+xml",
        purpose: "any",
      },
    ],
  };
}
