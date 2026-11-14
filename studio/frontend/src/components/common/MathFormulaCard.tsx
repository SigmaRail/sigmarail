import { useMemo } from "react";
import katex from "katex";
import type { MathPresentation } from "../../types";

export interface MathFormulaCardProps {
  math?: MathPresentation | null;
  className?: string;
  title?: string;
}

export function MathFormulaCard({
  math,
  className = "",
  title = "Mathematical Formula",
}: MathFormulaCardProps) {
  if (!math || !math.latex) return null;

  const html = useMemo(() => {
    try {
      return katex.renderToString(math.latex, {
        throwOnError: false,
        displayMode: true,
      });
    } catch {
      return null;
    }
  }, [math.latex]);

  const hasVariables = math.variables && Object.keys(math.variables).length > 0;

  return (
    <div className={`rounded-lg border border-line bg-surface p-3 text-ink ${className}`}>
      <div className="flex items-center justify-between pb-2 border-b border-line/60">
        <span className="text-[10px] font-bold uppercase tracking-wider text-ink-muted">
          {title}
        </span>
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(math.latex)}
          className="text-[9.5px] font-mono text-accent hover:underline"
          title="Copy raw LaTeX"
        >
          Copy LaTeX
        </button>
      </div>

      {/* KaTeX formula display */}
      <div className="my-2.5 overflow-x-auto py-2 text-center text-sm font-medium">
        {html ? (
          <div dangerouslySetInnerHTML={{ __html: html }} />
        ) : (
          <pre className="font-mono text-xs text-accent">{math.latex}</pre>
        )}
      </div>

      {/* Variables Glossary */}
      {hasVariables && (
        <div className="mt-2 pt-2 border-t border-line/40 space-y-1">
          <span className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
            Symbol Glossary
          </span>
          <div className="space-y-1">
            {Object.entries(math.variables).map(([sym, desc]) => {
              let symHtml = "";
              try {
                symHtml = katex.renderToString(sym, { throwOnError: false });
              } catch {
                symHtml = sym;
              }
              return (
                <div key={sym} className="flex items-start gap-2 text-[10px] leading-tight">
                  <span
                    className="flex-shrink-0 font-medium text-accent"
                    dangerouslySetInnerHTML={{ __html: symHtml }}
                  />
                  <span className="text-ink-muted">: {desc}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export default MathFormulaCard;
