"use client";

import { LocationProvider } from "./LocationProvider";

export default function ClientProviders({ children }: { children: React.ReactNode }) {
  return <LocationProvider>{children}</LocationProvider>;
}
