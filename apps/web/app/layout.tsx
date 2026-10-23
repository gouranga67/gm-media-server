import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "GM Studio",
    template: "%s · GM Studio",
  },
  description: "Private, source-only media editing on your GM server.",
  applicationName: "GM Studio",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "GM Studio",
  },
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  colorScheme: "light",
  themeColor: "#173f5f",
};

export default function RootLayout({ children }: { readonly children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <TooltipProvider>{children}</TooltipProvider>
      </body>
    </html>
  );
}
