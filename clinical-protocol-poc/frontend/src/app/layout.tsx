import type { ReactNode } from "react";

import "./globals.css";

export const metadata = {
  title: "Clinical Protocol POC",
  description: "Synthetic-only protocol study workspace",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
