"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { captureOrder, CheckoutError, createOrder } from "@/api/paypal";
import type { Checkout } from "@/types/paypal";

interface PayPalButtons {
  render: (container: HTMLElement) => Promise<void>;
  close?: () => Promise<void>;
}

interface PayPalSdk {
  Buttons: (options: {
    style?: Record<string, string | number>;
    createOrder: () => Promise<string>;
    onApprove: (data: { orderID: string }, actions: { restart: () => void }) => Promise<void> | void;
    onCancel?: () => void;
    onError?: (error: unknown) => void;
  }) => PayPalButtons;
}

declare global {
  interface Window {
    paypal?: PayPalSdk;
  }
}

let sdk: Promise<PayPalSdk> | null = null;

function loadSdk(clientId: string, currency: string): Promise<PayPalSdk> {
  if (window.paypal) return Promise.resolve(window.paypal);
  sdk ??= new Promise<PayPalSdk>((resolve, reject) => {
    const script = document.createElement("script");
    const query = new URLSearchParams({ "client-id": clientId, currency, intent: "capture", components: "buttons" });
    script.src = `https://www.paypal.com/sdk/js?${query}`;
    script.onload = () => (window.paypal ? resolve(window.paypal) : reject(new Error("The PayPal SDK did not start.")));
    script.onerror = () => {
      sdk = null;
      script.remove();
      reject(new Error("Could not load the PayPal SDK."));
    };
    document.head.appendChild(script);
  });
  return sdk;
}

/**
 * PayPal's button. Creating and capturing the order both go through this project's server, which refuses anything the risk
 * decision doesn't allow. A declined funding source restarts the payment so the buyer can choose another one, as PayPal advises.
 */
export function PayPalButton({ clientId, currency, checkoutId, onCaptured, onProblem }: {
  clientId: string;
  currency: string;
  checkoutId: string;
  onCaptured: (checkout: Checkout) => void;
  onProblem: (message: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const callbacks = useRef({ onCaptured, onProblem });
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");

  useEffect(() => {
    callbacks.current = { onCaptured, onProblem };
  });

  useEffect(() => {
    let on = true;
    let buttons: PayPalButtons | null = null;
    let reason: string | null = null; // our server's explanation, which PayPal's onError would otherwise replace with a generic one
    const slot = document.createElement("div"); // a fresh element per render: PayPal can't render twice into one
    host.current?.appendChild(slot);
    const explain = (e: unknown) => (e instanceof Error ? e.message : "PayPal could not complete the payment.");

    loadSdk(clientId, currency).then(
      (paypal) => {
        if (!on) return;
        buttons = paypal.Buttons({
          style: { layout: "vertical", color: "gold", shape: "pill", label: "paypal", height: 45 },
          createOrder: async () => {
            try {
              return (await createOrder(checkoutId)).order_id;
            } catch (e) {
              reason = explain(e);
              throw e;
            }
          },
          onApprove: async (data, actions) => {
            try {
              callbacks.current.onCaptured((await captureOrder(checkoutId, data.orderID)).checkout);
            } catch (e) {
              if (e instanceof CheckoutError && e.issue === "INSTRUMENT_DECLINED") {
                callbacks.current.onProblem("PayPal declined that funding source. Choose another one.");
                actions.restart();
                return;
              }
              callbacks.current.onProblem(explain(e));
            }
          },
          onCancel: () => callbacks.current.onProblem("You closed PayPal before approving. Nothing was charged."),
          onError: (e) => {
            callbacks.current.onProblem(reason ?? explain(e));
            reason = null;
          },
        });
        buttons.render(slot).then(
          () => on && setState("ready"),
          () => on && setState("failed"),
        );
      },
      () => on && setState("failed"),
    );

    return () => {
      on = false;
      void buttons?.close?.()?.catch(() => {});
      slot.remove();
    };
  }, [clientId, currency, checkoutId]);

  return (
    <div>
      {state === "loading" && (
        <p className="flex items-center gap-2 py-3 text-footnote text-label-secondary">
          <Loader2 className="size-4 animate-spin" aria-hidden /> Loading PayPal…
        </p>
      )}
      {state === "failed" && (
        <p className="py-3 text-footnote text-sys-red">
          PayPal&apos;s button could not load. Check your internet connection, and that an ad blocker isn&apos;t blocking paypal.com.
        </p>
      )}
      {/* This page is dark. On a browser set to light mode, a frame that doesn't match its page gets an opaque white background. */}
      <div ref={host} style={{ colorScheme: "light" }} />
    </div>
  );
}
