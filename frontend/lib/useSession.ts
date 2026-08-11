"use client";

/* PLAN-v5 Stage 0: know who's signed in, client-side.

   A tiny standalone version of the same idea — a hook is just a function
   that runs on every render and remembers things between renders with
   useState/useEffect:

     function useClock() {
       const [now, setNow] = useState(() => new Date());
       useEffect(() => {
         const id = setInterval(() => setNow(new Date()), 1000);
         return () => clearInterval(id);
       }, []);
       return now;
     }

   `useClock()` in any component gives that component the current time and
   re-renders it every second, without that component managing the interval
   itself. `useSession()` below does the same for "who is signed in" — it
   asks the backend once on mount and hands back the answer, so a page never
   has to write its own fetch-and-remember boilerplate. */

import { useEffect, useState } from "react";
import { fetchMe, type SessionUser } from "@/lib/api";

interface SessionState {
  user: SessionUser | null;
  loading: boolean;
}

export function useSession(): SessionState {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetchMe().then((result) => {
      if (!cancelled) {
        setUser(result);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return { user, loading };
}
