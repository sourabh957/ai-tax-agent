import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AppProvider } from "@/hooks/use-app";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Taxly — AI Tax Agent",
  description: "AI-powered Indian tax assistant grounded in your financial documents.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.className} h-full antialiased`}>
      <body className="min-h-full bg-slate-50 text-slate-900">
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
