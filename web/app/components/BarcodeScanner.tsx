"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Html5Qrcode } from "html5-qrcode";

interface BarcodeScannerProps {
  onScan: (barcode: string) => void;
  onClose: () => void;
}

export default function BarcodeScanner({ onScan, onClose }: BarcodeScannerProps) {
  const [error, setError] = useState("");
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const scannedRef = useRef(false);

  const stopScanner = useCallback(async () => {
    try {
      if (scannerRef.current?.isScanning) {
        await scannerRef.current.stop();
      }
      scannerRef.current?.clear();
    } catch {
      // Ignore cleanup errors
    }
    scannerRef.current = null;
  }, []);

  useEffect(() => {
    const startScanner = async () => {
      try {
        const scanner = new Html5Qrcode("barcode-reader");
        scannerRef.current = scanner;

        await scanner.start(
          { facingMode: "environment" },
          {
            fps: 10,
            qrbox: { width: 280, height: 150 },
            aspectRatio: 1.0,
          },
          (decodedText) => {
            if (!scannedRef.current) {
              scannedRef.current = true;
              onScan(decodedText);
              stopScanner();
            }
          },
          () => {
            // Ignore scan failures (happens every frame until barcode found)
          }
        );
      } catch (err) {
        const msg = String(err);
        if (msg.includes("NotAllowedError") || msg.includes("Permission")) {
          setError("Kamera izni verilmedi. Tarayıcı ayarlarından kamera iznini açın.");
        } else if (msg.includes("NotFoundError")) {
          setError("Kamera bulunamadı.");
        } else {
          setError("Kamera açılamadı. Lütfen tekrar deneyin.");
        }
      }
    };

    startScanner();

    return () => {
      stopScanner();
    };
  }, [onScan, stopScanner]);

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex flex-col items-center justify-center p-4">
      {/* Close button */}
      <button
        onClick={() => {
          stopScanner();
          onClose();
        }}
        className="absolute top-4 right-4 w-10 h-10 bg-white/20 hover:bg-white/30
                   rounded-full flex items-center justify-center text-white text-xl
                   backdrop-blur-sm transition-colors z-10"
        aria-label="Kapat"
      >
        &times;
      </button>

      {/* Header */}
      <p className="text-white text-lg font-semibold mb-4">
        Barkodu kameraya tutun
      </p>

      {/* Scanner viewport */}
      <div
        ref={containerRef}
        className="w-full max-w-sm bg-black rounded-2xl overflow-hidden"
      >
        <div id="barcode-reader" className="w-full" />
      </div>

      {/* Error */}
      {error && (
        <div className="mt-4 bg-red-500/90 text-white px-4 py-3 rounded-xl text-sm max-w-sm text-center">
          {error}
        </div>
      )}

      {/* Manual input hint */}
      <p className="text-white/60 text-sm mt-4 text-center">
        veya barkod numarasını arama kutusuna yazın
      </p>
    </div>
  );
}
