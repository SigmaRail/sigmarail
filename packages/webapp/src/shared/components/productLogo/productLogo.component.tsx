import { cn } from '@sb/webapp-core/lib/utils';

type ProductLogoProps = {
  compact?: boolean;
  className?: string;
};

export const ProductLogo = ({ compact = false, className }: ProductLogoProps) => (
  <div
    className={cn('inline-flex items-center gap-2 text-foreground', className)}
    aria-label="SigmaRail"
  >
    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-foreground text-sm font-bold text-background">
      S
    </span>
    {!compact && <span className="font-semibold tracking-tight">SigmaRail</span>}
  </div>
);
