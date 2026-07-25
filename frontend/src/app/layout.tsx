import type { Metadata } from "next";
import { AppShell } from "@/components/AppShell";
import { AuroraBackground } from "@/components/AuroraBackground";
import { AuthProvider } from "@/components/AuthProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulseAI: Customer Signal Dashboard",
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
        <AuthProvider>
          <TooltipProvider delayDuration={200}>
            {/* Content sits ABOVE the fixed aurora (z-0). The shell shows the
                floating nav + guards content; the sign-in route renders bare. */}
            <AppShell>{children}</AppShell>
          </TooltipProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
