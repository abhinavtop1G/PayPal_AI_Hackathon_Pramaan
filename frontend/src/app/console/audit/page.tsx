import { Suspense } from "react";
import { AuditLog } from "@/components/audit/AuditLog";

export const metadata = { title: "Audit log · PRAMAAN" };

// AuditLog reads ?q= (links from the overview); search params need a Suspense boundary on a prerendered route
export default function AuditPage() {
  return (
    <Suspense>
      <AuditLog />
    </Suspense>
  );
}
