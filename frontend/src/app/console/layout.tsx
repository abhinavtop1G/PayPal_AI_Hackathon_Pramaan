import { ConsoleFrame } from "@/components/console/ConsoleFrame";

export default function ConsoleLayout({ children }: LayoutProps<"/console">) {
  return <ConsoleFrame>{children}</ConsoleFrame>;
}
