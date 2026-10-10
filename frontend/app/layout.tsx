import type { Metadata } from "next";
import "./globals.css";
import AuthGate from "@/components/auth-gate";

export const metadata: Metadata = {
  title: {
    default: "AQERITH | Recruitment Intelligence",
    template: "%s | AQERITH",
  },
  applicationName: "AQERITH",
  description: "AQERITH is a recruitment operations platform for modern hiring teams.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><AuthGate>{children}</AuthGate></body>
    </html>
  );
}
