import { useEffect } from "react";
import { StockIntrospectionPanel } from "./StockIntrospectionPanel";

interface StockIntrospectionDialogProps {
  isOpen: boolean;
  onClose: () => void;
  ticker: string;
  asOfDate: string;
}

/** Modal shell around the shared MarketSurge chart panel (Screens / legacy callers). */
export function StockIntrospectionDialog({
  isOpen,
  onClose,
  ticker,
  asOfDate,
}: StockIntrospectionDialogProps) {
  useEffect(() => {
    if (!isOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <div className="flex h-[100dvh] w-full flex-col overflow-hidden border-l border-line bg-surface shadow-2xl sm:w-[min(92vw,42rem)] lg:w-[min(58vw,52rem)]">
        <StockIntrospectionPanel
          ticker={ticker}
          asOfDate={asOfDate}
          onClose={onClose}
          className="h-full"
        />
      </div>
    </div>
  );
}
