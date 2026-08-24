"use client";

import Script from "next/script";
import { useCallback, useRef, useState } from "react";

type CredentialResponse = { credential?: string };
type GoogleIdentity = {
  initialize: (options: { client_id: string; callback: (response: CredentialResponse) => void; auto_select: boolean; cancel_on_tap_outside: boolean }) => void;
  renderButton: (element: HTMLElement, options: Record<string, string | number>) => void;
};

declare global {
  interface Window {
    google?: { accounts: { id: GoogleIdentity & { disableAutoSelect: () => void } } };
  }
}

export default function GoogleSignIn({ onCredential }: { onCredential: (credential: string) => void }) {
  const button = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

  const renderGoogleButton = useCallback(() => {
    if (!clientId) {
      setError("Google sign-in has not been configured yet.");
      return;
    }
    if (!window.google || !button.current) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: response => {
        if (response.credential) onCredential(response.credential);
        else setError("Google did not return a sign-in credential. Please try again.");
      },
      auto_select: false,
      cancel_on_tap_outside: true,
    });
    button.current.replaceChildren();
    const availableWidth = button.current.parentElement?.clientWidth || 320;
    window.google.accounts.id.renderButton(button.current, {
      type: "standard",
      theme: "outline",
      size: "large",
      text: "signin_with",
      shape: "rectangular",
      logo_alignment: "left",
      width: Math.max(200, Math.min(320, availableWidth)),
    });
  }, [clientId, onCredential]);

  return (
    <div className="google-signin">
      <Script src="https://accounts.google.com/gsi/client" strategy="afterInteractive" onReady={renderGoogleButton} />
      <div ref={button} aria-label="Sign in with Google" />
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
