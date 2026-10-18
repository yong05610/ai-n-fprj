import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PaceMate",
  description: "AI 기반 개인 학습 플래너",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
