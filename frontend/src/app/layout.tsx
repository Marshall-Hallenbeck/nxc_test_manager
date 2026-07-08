import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ThemeToggle } from "@/components/ThemeToggle";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "NetExec Test Manager",
  description: "E2E testing manager for NetExec pull requests",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ThemeProvider>
          <nav className="bg-gray-900 text-white px-6 py-4">
            <div className="max-w-[1600px] mx-auto flex items-center gap-6">
              <Link href="/" className="font-bold text-lg">NetExec Test Manager</Link>
              <Link href="/runs" className="text-gray-300 hover:text-white">Test Runs</Link>
              <Link href="/compare" className="text-gray-300 hover:text-white">Compare</Link>
              <div className="ml-auto">
                <ThemeToggle />
              </div>
            </div>
          </nav>
          <main className="max-w-[1600px] mx-auto px-6 py-8">
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
