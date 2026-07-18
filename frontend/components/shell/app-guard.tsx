"use client";
import { api } from "@/lib/api";
import { useAuth } from "@clerk/nextjs";
import { CircleNotch } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Routes are already auth-protected by middleware. This guard additionally
 * ensures the signed-in user has completed farm onboarding; if not, it sends
 * them to /onboarding before any app page renders.
 */
export function AppGuard({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      router.replace("/sign-in");
      return;
    }
    let active = true;
    (async () => {
      try {
        // ensure Clerk token is warm before the api helper reads it
        await getToken();
        // Onboarding is complete only once there's a profile AND at least one
        // farm. The onboarding page itself resumes at whichever step is missing.
        const { profile, farms } = await api.profileExists();
        if (!active) return;
        if (!profile || farms === 0) router.replace("/onboarding");
        else setReady(true);
      } catch {
        if (active) setReady(true); // let the page show its own error state
      }
    })();
    return () => {
      active = false;
    };
  }, [isLoaded, isSignedIn, getToken, router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <CircleNotch className="h-6 w-6 animate-spin text-field-600" />
      </div>
    );
  }
  return <>{children}</>;
}
