import "./globals.css";

export const metadata = { title: "Simple MP3 Creator", description: "Turn text into private MP3 audio." };

export default function RootLayout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}

