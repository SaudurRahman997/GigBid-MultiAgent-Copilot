"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api/client";
import { DegradedBanner } from "./DegradedBanner";

const NAV = [
  ["/inbox", "Inbox"],
  ["/pipeline", "Pipeline"],
  ["/messages", "Messages"],
  ["/analytics", "Analytics"],
  ["/settings", "Settings"],
] as const;

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  if (path.startsWith("/onboarding")) return <main className="flex-1">{children}</main>;
  return (
    <div className="flex-1 flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:p-2 bg-panel">Skip to content</a>
      <DegradedBanner />
      <header className="border-b border-line bg-panel">
        <div className="mx-auto max-w-6xl flex items-center gap-4 px-4 h-14">
          <Link href="/inbox" className="font-bold text-lg">GigBid</Link>
          <button className="sm:hidden btn ml-auto" aria-expanded={open} aria-controls="nav" onClick={() => setOpen(!open)}>Menu</button>
          <nav id="nav" aria-label="Main" className={`${open ? "flex" : "hidden"} sm:flex absolute sm:static top-14 left-0 right-0 flex-col sm:flex-row gap-1 bg-panel sm:bg-transparent p-2 sm:p-0 border-b sm:border-0 border-line z-30`}>
            {NAV.map(([href, label]) => (
              <Link key={href} href={href} onClick={() => setOpen(false)} aria-current={path.startsWith(href) ? "page" : undefined}
                className={`rounded px-3 py-1.5 text-sm ${path.startsWith(href) ? "bg-accent/15 text-accent font-medium" : "hover:bg-panel2"}`}>
                {label}
              </Link>
            ))}
          </nav>
          <button className="hidden sm:block ml-auto text-sm text-muted hover:underline"
            onClick={async () => { await api.POST("/auth/logout"); router.replace("/onboarding"); }}>
            Sign out
          </button>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}
