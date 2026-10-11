import type { Metadata } from "next";
import { AdminChrome } from "@/components/AdminChrome";
import "../admin.css";

export const metadata: Metadata = {
  title: "PO Championship | Admin",
  robots: { index: false, follow: false },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminChrome>{children}</AdminChrome>;
}
