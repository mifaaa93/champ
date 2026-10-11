import { Suspense } from "react";
import { EventHome } from "@/components/EventHome";

export const dynamic = "force-dynamic";

export default function Home() {
  return (
    <Suspense fallback={<div className="po" />}>
      <EventHome />
    </Suspense>
  );
}
