"use client";

import { useLocation } from "./LocationProvider";

interface LocationBannerProps {
  onAccept: () => void;
}

export default function LocationBanner({ onAccept }: LocationBannerProps) {
  const { status, dismissPrompt } = useLocation();

  if (status !== "prompt") return null;

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-2xl p-4 animate-in fade-in">
      <div className="flex items-start gap-3">
        <span className="text-2xl shrink-0">📍</span>
        <div className="flex-1">
          <p className="text-sm font-bold text-gray-800">
            Yakınındaki mağazaları öne çıkaralım mı?
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Konumunuza en yakın ve stoklu mağazalar listenin başında görünür.
          </p>
          <div className="flex gap-2 mt-3">
            <button
              onClick={onAccept}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-semibold rounded-xl
                         active:scale-95 transition-transform"
            >
              Evet, göster
            </button>
            <button
              onClick={dismissPrompt}
              className="px-4 py-2 bg-white border border-gray-200 text-sm text-gray-600 font-medium rounded-xl
                         active:scale-95 transition-transform"
            >
              Şimdi değil
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
