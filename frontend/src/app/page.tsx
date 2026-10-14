import { AppShell } from "@/components/layout/AppShell";
import { DemoProvider } from "@/context/DemoContext";

/** The RAKSHAM demo: session replay, bank-wide wall, mule network and a live session builder (see AppShell). */
export default function DemoPage() {
  return (
    <DemoProvider>
      <AppShell />
    </DemoProvider>
  );
}
