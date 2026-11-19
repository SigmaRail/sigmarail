import type { FillSession } from "../../lib/pipelineSlotBindings";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Button } from "@sb/webapp-core/components/ui/button";

interface ExecutionSlotCardProps {
  fillSession: FillSession;
  onChangeFillSession: (v: FillSession) => void;
}

export function ExecutionSlotCard({
  fillSession,
  onChangeFillSession,
}: ExecutionSlotCardProps) {
  return (
    <Card className="grid grid-cols-2 gap-2 p-3.5 shadow-sm">
      {(["moo", "moc"] as const).map((session) => (
        <Button
          key={session}
          type="button"
          variant={fillSession === session ? "secondary" : "outline"}
          size="sm"
          title={
            session === "moo"
              ? "Use prior completed daily data and submit before the market open"
              : "Use prior completed daily data and submit before the market close"
          }
          onClick={() => onChangeFillSession(session)}
          className="h-8"
          aria-pressed={fillSession === session}
        >
          {session === "moo" ? "MOO (open of T)" : "MOC (close of T)"}
        </Button>
      ))}
      <p className="col-span-full text-[10px] text-ink-faint">
        Uses the prior completed daily data. Orders are submitted before the selected open or close.
      </p>
    </Card>
  );
}
