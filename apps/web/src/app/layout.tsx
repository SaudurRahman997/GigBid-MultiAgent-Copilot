import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Suspense } from "react";
import { Shell } from "@/components/Shell";
import { Loading } from "@/components/States";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "GigBid",
  description: "Multi-agent freelancer copilot — a human approves every proposal and message",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <Suspense fallback={<Loading />}>
          <Shell>{children}</Shell>
        </Suspense>
      </body>
    </html>
  );
}
