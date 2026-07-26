import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Keyboard, ScanLine } from "lucide-react";

type Props = {
  onDetected: (code: string, format: string) => void;
  disabled?: boolean;
};

type NativeBarcode = {
  rawValue: string;
  format: string;
};

type NativeBarcodeDetector = {
  detect: (source: HTMLVideoElement) => Promise<NativeBarcode[]>;
};

type NativeBarcodeDetectorConstructor = {
  new (options?: { formats?: string[] }): NativeBarcodeDetector;
  getSupportedFormats?: () => Promise<string[]>;
};

type ScannerControls = {
  stop: () => void;
};

const NATIVE_FORMATS = [
  "ean_8",
  "ean_13",
  "upc_a",
  "code_128",
  "data_matrix",
  "qr_code"
];

export default function BarcodeScanner({ onDetected, disabled = false }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const controlsRef = useRef<ScannerControls | null>(null);
  const animationRef = useRef<number | null>(null);
  const stoppedRef = useRef(true);
  const [cameraActive, setCameraActive] = useState(false);
  const [engine, setEngine] = useState<"native" | "zxing" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [manualCode, setManualCode] = useState("");

  const stopCamera = useCallback(() => {
    stoppedRef.current = true;
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    controlsRef.current?.stop();
    controlsRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, []);

  const reportCode = useCallback(
    (code: string, format: string) => {
      const normalized = code.trim();
      if (!normalized || stoppedRef.current) return;
      stopCamera();
      navigator.vibrate?.(80);
      onDetected(normalized, format);
    },
    [onDetected, stopCamera]
  );

  const runNativeDetector = useCallback(
    async (
      Detector: NativeBarcodeDetectorConstructor,
      video: HTMLVideoElement
    ) => {
      const supported = Detector.getSupportedFormats
        ? await Detector.getSupportedFormats()
        : NATIVE_FORMATS;
      const formats = NATIVE_FORMATS.filter((format) =>
        supported.includes(format)
      );
      const detector = new Detector({ formats });
      let detecting = false;
      const scanFrame = async () => {
        if (stoppedRef.current) return;
        if (!detecting && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
          detecting = true;
          try {
            const codes = await detector.detect(video);
            if (codes[0]) {
              reportCode(codes[0].rawValue, codes[0].format);
              return;
            }
          } catch {
            // A következő képkockán újrapróbáljuk.
          } finally {
            detecting = false;
          }
        }
        animationRef.current = requestAnimationFrame(scanFrame);
      };
      animationRef.current = requestAnimationFrame(scanFrame);
      setEngine("native");
    },
    [reportCode]
  );

  const startCamera = useCallback(async () => {
    if (disabled || cameraActive) return;
    setError(null);
    stoppedRef.current = false;
    const video = videoRef.current;
    if (!video || !navigator.mediaDevices?.getUserMedia) {
      setError("Ezen az eszközön nem érhető el böngészős kamera.");
      stoppedRef.current = true;
      return;
    }
    const Detector = (
      window as typeof window & {
        BarcodeDetector?: NativeBarcodeDetectorConstructor;
      }
    ).BarcodeDetector;
    try {
      if (Detector) {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 }
          }
        });
        streamRef.current = stream;
        video.srcObject = stream;
        await video.play();
        setCameraActive(true);
        await runNativeDetector(Detector, video);
        return;
      }

      const { BrowserMultiFormatReader } = await import("@zxing/browser");
      const reader = new BrowserMultiFormatReader();
      const controls = await reader.decodeFromConstraints(
        {
          audio: false,
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 }
          }
        },
        video,
        (result) => {
          if (result) {
            reportCode(result.getText(), result.getBarcodeFormat().toString());
          }
        }
      );
      controlsRef.current = controls;
      setEngine("zxing");
      setCameraActive(true);
    } catch (caught) {
      stopCamera();
      const denied =
        caught instanceof DOMException &&
        ["NotAllowedError", "PermissionDeniedError"].includes(caught.name);
      setError(
        denied
          ? "A kameraengedélyt a böngészőben kell megadni."
          : "A kamera nem indítható. Használd a kézi vagy Bluetooth bevitelt."
      );
    }
  }, [
    cameraActive,
    disabled,
    reportCode,
    runNativeDetector,
    stopCamera
  ]);

  useEffect(() => stopCamera, [stopCamera]);

  function submitManualCode() {
    const normalized = manualCode.trim();
    if (!normalized) return;
    onDetected(normalized, "manual");
    setManualCode("");
  }

  return (
    <div className={`barcode-scanner ${cameraActive ? "active" : ""}`}>
      <div className="scanner-viewport">
        <video ref={videoRef} playsInline muted aria-label="Kamera előnézet" />
        {!cameraActive && (
          <div className="scanner-placeholder">
            <ScanLine aria-hidden="true" />
            <strong>EAN vagy QR beolvasása</strong>
            <span>A hátlapi kamera automatikusan fókuszál a kódra.</span>
          </div>
        )}
        {cameraActive && (
          <>
            <span className="scanner-corners" aria-hidden="true" />
            <span className="scanner-beam" aria-hidden="true" />
            <span className="scanner-engine">
              {engine === "native" ? "BarcodeDetector" : "ZXing fallback"}
            </span>
          </>
        )}
      </div>

      <button
        type="button"
        className={cameraActive ? "secondary-button" : "primary-button"}
        onClick={cameraActive ? stopCamera : startCamera}
        disabled={disabled}
      >
        {cameraActive ? (
          <CameraOff aria-hidden="true" />
        ) : (
          <Camera aria-hidden="true" />
        )}
        {cameraActive ? "Kamera leállítása" : "Kamera indítása"}
      </button>

      <div
        className="scanner-manual-entry"
      >
        <Keyboard aria-hidden="true" />
        <label>
          <span className="sr-only">Kód kézi vagy Bluetooth bevitele</span>
          <input
            value={manualCode}
            onChange={(event) => setManualCode(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submitManualCode();
              }
            }}
            placeholder="Kód beírása vagy olvasó használata"
            inputMode="numeric"
            autoComplete="off"
            disabled={disabled}
          />
        </label>
        <button
          type="button"
          disabled={disabled || !manualCode.trim()}
          onClick={submitManualCode}
        >
          Keresés
        </button>
      </div>
      {error && <p className="scanner-error">{error}</p>}
    </div>
  );
}
