"use client";

import { useState, useEffect, useCallback, createContext, useContext } from "react";

interface LocationState {
  lat: number | null;
  lon: number | null;
  status: "idle" | "prompt" | "granted" | "denied" | "dismissed";
  requestLocation: () => void;
  acceptAndRequest: () => void;
  dismissPrompt: () => void;
}

const LocationContext = createContext<LocationState>({
  lat: null,
  lon: null,
  status: "idle",
  requestLocation: () => {},
  acceptAndRequest: () => {},
  dismissPrompt: () => {},
});

export function useLocation() {
  return useContext(LocationContext);
}

const STORAGE_KEY = "user_location";
const PREF_KEY = "location_pref"; // "granted" | "denied" | "dismissed"

export function LocationProvider({ children }: { children: React.ReactNode }) {
  const [lat, setLat] = useState<number | null>(null);
  const [lon, setLon] = useState<number | null>(null);
  const [status, setStatus] = useState<LocationState["status"]>("idle");

  // Load cached location + preference on mount
  useEffect(() => {
    const pref = localStorage.getItem(PREF_KEY);
    if (pref === "denied") {
      setStatus("denied");
      return;
    }

    const cached = localStorage.getItem(STORAGE_KEY);
    if (cached) {
      try {
        const { lat: cLat, lon: cLon, ts } = JSON.parse(cached);
        // Cache valid for 1 hour
        if (Date.now() - ts < 3600000) {
          setLat(cLat);
          setLon(cLon);
          setStatus("granted");
          return;
        }
      } catch {
        // ignore
      }
    }

    if (pref === "granted") {
      // Previously granted — request silently
      requestBrowserLocation();
    }
    // Otherwise stay "idle" — will show prompt on first search
  }, []);

  const requestBrowserLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setStatus("denied");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const newLat = pos.coords.latitude;
        const newLon = pos.coords.longitude;
        setLat(newLat);
        setLon(newLon);
        setStatus("granted");
        localStorage.setItem(PREF_KEY, "granted");
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ lat: newLat, lon: newLon, ts: Date.now() })
        );
      },
      () => {
        setStatus("denied");
        localStorage.setItem(PREF_KEY, "denied");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  }, []);

  const requestLocation = useCallback(() => {
    // Show our custom prompt first (unless already decided)
    const pref = localStorage.getItem(PREF_KEY);
    if (pref === "denied") return;
    if (pref === "granted" || status === "granted") {
      requestBrowserLocation();
      return;
    }
    setStatus("prompt");
  }, [status, requestBrowserLocation]);

  // "Şimdi değil" — dismiss for this session only, ask again next visit
  const dismissPrompt = useCallback(() => {
    setStatus("dismissed");
    // No localStorage write — next visit will ask again
  }, []);

  // Called when user clicks "Evet" on our custom banner → triggers browser permission
  const acceptAndRequest = useCallback(() => {
    setStatus("granted"); // optimistic — will update if browser denies
    requestBrowserLocation();
  }, [requestBrowserLocation]);

  return (
    <LocationContext.Provider
      value={{ lat, lon, status, requestLocation, acceptAndRequest, dismissPrompt }}
    >
      {children}
    </LocationContext.Provider>
  );
}
