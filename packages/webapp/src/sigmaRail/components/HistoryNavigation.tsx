import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { Button } from "@sb/webapp-core/components/ui/button";
import { RuntimeStatus } from "./RuntimeStatus";

function currentHistoryIndex(): number {
  const index = window.history.state?.idx;
  return typeof index === "number" && Number.isFinite(index) ? index : 0;
}

/** App-level browser history controls. Track the furthest in-app entry so Forward is
 * available after Back, without guessing from the browser's total (cross-site) history.
 */
export function HistoryNavigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const navigationType = useNavigationType();
  const [position, setPosition] = useState(currentHistoryIndex);
  const furthestPosition = useRef(position);

  useEffect(() => {
    const nextPosition = currentHistoryIndex();
    if (navigationType === "PUSH") {
      // A new navigation after Back replaces the old forward path.
      furthestPosition.current = nextPosition;
    } else {
      furthestPosition.current = Math.max(furthestPosition.current, nextPosition);
    }
    setPosition(nextPosition);
  }, [location.key, navigationType]);

  const canGoBack = position > 0;
  const canGoForward = position < furthestPosition.current;

  return (
    <header className="sticky top-0 z-30 flex h-9 shrink-0 items-center gap-1 border-b border-line bg-surface/95 px-2 backdrop-blur-sm" aria-label="Page history">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        aria-label="Go back"
        title="Go back"
        disabled={!canGoBack}
        onClick={() => navigate(-1)}
      >
        <ArrowLeft className="h-4 w-4" />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-7 w-7"
        aria-label="Go forward"
        title="Go forward"
        disabled={!canGoForward}
        onClick={() => navigate(1)}
      >
        <ArrowRight className="h-4 w-4" />
      </Button>
      <RuntimeStatus />
    </header>
  );
}
