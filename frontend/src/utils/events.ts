import {
  Activity,
  AppWindow,
  CircleDollarSign,
  Download,
  Fingerprint,
  Hand,
  IndianRupee,
  KeyRound,
  Link,
  MessageSquare,
  Landmark,
  type LucideIcon,
  PhoneCall,
  PhoneOff,
  Send,
  UserPlus,
} from "lucide-react";
import type { DemoInput, EventType } from "@/types/demo";
import { rupees } from "./format";

const ICON: Partial<Record<EventType, LucideIcon>> = {
  CALL_START: PhoneCall,
  CALL_END: PhoneOff,
  APP_INSTALL: Download,
  UPI_APP_OPEN: AppWindow,
  BALANCE_CHECK: Landmark,
  PAYEE_ADD: UserPlus,
  PAYMENT_ATTEMPT: Send,
  PAYMENT_SUCCESS: CircleDollarSign,
  BIO_WINDOW: Fingerprint,
  SMS_RECEIVED: MessageSquare,
  LINK_CLICK: Link,
  ACCESSIBILITY_GRANT: Hand,
  OTP_RECEIVED: KeyRound,
  CREDIT_RECEIVED: IndianRupee,
};

const CALLER: Record<string, string> = { unknown: "unknown number", voip_intl: "internet (VoIP) number", contact: "contact" };

/** One-line analyst description of a raw event. */
export function describe(e: DemoInput): { icon: LucideIcon; label: string } {
  const icon = ICON[e.event] ?? Activity;
  switch (e.event) {
    case "CALL_START":
      return { icon, label: `${e.call_video ? "Video" : "Voice"} call from ${CALLER[e.caller_kind ?? "unknown"]}` };
    case "CALL_END":
      return { icon, label: "Call ended" };
    case "APP_INSTALL":
      return { icon, label: `App installed (${e.app_source === "sideload" ? "sideloaded" : "store"})` };
    case "UPI_APP_OPEN":
      return { icon, label: "UPI app opened" };
    case "BALANCE_CHECK":
      return { icon, label: "Balance checked" };
    case "PAYEE_ADD":
      return {
        icon,
        label: `New payee · ${e.payee_vpa_age_days != null ? `${Math.round(e.payee_vpa_age_days)}-day-old account` : "unknown age"}`,
      };
    case "PAYMENT_ATTEMPT":
      return { icon, label: `Payment attempt ${rupees(e.amount ?? 0)}` };
    case "PAYMENT_SUCCESS":
      return { icon, label: `Payment completed ${rupees(e.amount ?? 0)}` };
    case "BIO_WINDOW":
      return { icon, label: "Touch telemetry window" };
    case "SMS_RECEIVED":
      return { icon, label: `SMS from ${e.sms_sender_kind === "bank_shortcode" ? "a bank-style sender" : "an unknown number"}${e.sms_has_link ? " with a link" : ""}` };
    case "LINK_CLICK":
      return { icon, label: "Link opened" };
    case "ACCESSIBILITY_GRANT":
      return { icon, label: "Screen-control permission granted" };
    case "OTP_RECEIVED":
      return { icon, label: "OTP received" };
    case "CREDIT_RECEIVED":
      return { icon, label: `Money received ${rupees(e.amount ?? 0)}` };
    default:
      return { icon, label: e.event.replaceAll("_", " ").toLowerCase() };
  }
}
