import type { Metadata } from "next";
import "./globals.css";

import { AuthProvider } from "@/components/AuthProvider";

export const metadata: Metadata = {
  title: "PaceMate",
  description: "AI 기반 개인 학습 플래너",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
