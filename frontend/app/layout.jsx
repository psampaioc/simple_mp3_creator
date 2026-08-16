import "./globals.css";
import { Analytics } from "@vercel/analytics/next";

export const metadata = { title: "Simple MP3 Creator", description: "Turn text into private MP3 audio." };

export default function RootLayout({ children }) {
  return <html lang="en"><body>{children}<Analytics /></body></html>;
}
