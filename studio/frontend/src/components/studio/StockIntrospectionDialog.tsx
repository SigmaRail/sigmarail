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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-2 sm:p-4 backdrop-blur-xs">
      <div className="flex h-[92vh] w-[96vw] max-w-[1480px] flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-2xl">
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
