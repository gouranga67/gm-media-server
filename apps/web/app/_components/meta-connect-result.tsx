"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { completeMeta } from "@/lib/publishing-api";
export function MetaConnectResult() {
  const pending = useRef<Promise<{ connected: number }> | undefined>(undefined);
  const [message, setMessage] = useState("Completing your account connection…");
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    if (!pending.current) {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code"),
        state = params.get("state");
      window.history.replaceState(null, "", "/publishing/connect");
      pending.current =
        code && state
          ? completeMeta(code, state)
          : Promise.reject(
              new Error(
                "Meta sign-in was cancelled or is incomplete. Start Connect Meta again.",
              ),
            );
    }
    void pending.current
      .then((value) => {
        if (!cancelled)
          setMessage(
            `${value.connected} publishing accounts connected. Nothing has been posted.`,
          );
      })
      .catch((value) => {
        if (!cancelled) {
          setError(true);
          setMessage(
            value instanceof Error
              ? value.message
              : "Account connection failed. Start Connect Meta again.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return (
    <main className="mx-auto max-w-xl space-y-5 px-4 py-12">
      <h1 className="text-2xl font-bold text-[#173F5F]">Meta connection</h1>
      <p
        className={error ? "text-[#A23B2A]" : "text-[#173F5F]"}
        role={error ? "alert" : "status"}
      >
        {message}
      </p>
      <Link
        className="inline-block min-h-11 py-2 font-bold text-[#173F5F] underline"
        href="/publishing"
      >
        Return to publishing
      </Link>
    </main>
  );
}
