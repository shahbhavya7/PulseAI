import type { Metadata } from "next";
import { AuroraBackground } from "@/components/AuroraBackground";
import { TopNav } from "@/components/TopNav";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulseAI — Customer Signal Dashboard",
  description: "Upload customer tickets, see what matters this week.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <AuroraBackground />
        <TooltipProvider delayDuration={200}>
          {/* Content sits ABOVE the fixed aurora (z-0). relative + z-10 guarantees
              every glass panel blurs the moving colour behind it. */}
          <div className="relative z-10 min-h-screen">
            {/* Floating glass top navbar (sticky, inset, detached over the aurora). */}
            <TopNav />
            {/* Content flows full-width below the bar; pt clears the sticky bar
                (top-4 inset + ~56px bar height). */}
            <main className="mx-auto w-full max-w-6xl px-4 pb-10 pt-6 md:px-8">
              {children}
            </main>
          </div>
        </TooltipProvider>
      </body>
    </html>
  );
}
