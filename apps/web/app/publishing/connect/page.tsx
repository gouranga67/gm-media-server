import type { Metadata } from "next";
import { MetaConnectResult } from "@/app/_components/meta-connect-result";
export const metadata: Metadata = {
  title: "Connect Meta · GM Studio",
  referrer: "no-referrer",
  robots: { index: false, follow: false },
};
export default function Page() {
  return <MetaConnectResult />;
}
