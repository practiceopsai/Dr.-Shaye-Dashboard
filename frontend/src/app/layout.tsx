import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Eli Command Center", description: "Dr. Shaye's daily priority and action center" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}

