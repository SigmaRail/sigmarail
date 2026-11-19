import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ConfirmDialog } from '@sb/webapp-core/components/confirmDialog';
import { Button } from '@sb/webapp-core/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@sb/webapp-core/components/ui/dialog';
import { Input } from '@sb/webapp-core/components/ui/input';
import { deleteSavedScreen } from '../../api/screens';
import type { SavedScreen, ScreenTemplateSummary } from '../../types';

interface ScreenPickerDialogProps {
  isOpen: boolean;
  onClose: () => void;
  templates: ScreenTemplateSummary[];
  templatesLoading?: boolean;
  templatesError?: string | null;
  screens: SavedScreen[];
  screensLoading?: boolean;
  screensError?: string | null;
  screensWarning?: string | null;
  onRetryLoad?: () => void;
  onSelectTemplate: (templateId: string) => void;
  onSelectScreen: (screen: SavedScreen) => void;
}

type FilterCategory = 'all' | 'system' | 'custom';

export function ScreenPickerDialog({
  isOpen,
  onClose,
  templates,
  templatesLoading = false,
  templatesError = null,
  screens,
  screensLoading = false,
  screensError = null,
  screensWarning = null,
  onRetryLoad,
  onSelectTemplate,
  onSelectScreen,
}: ScreenPickerDialogProps) {
  const [filter, setFilter] = useState<FilterCategory>('all');
  const [search, setSearch] = useState('');
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: (id: string | number) => deleteSavedScreen(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-screens'] });
      queryClient.invalidateQueries({ queryKey: ['saved-screens-dialog'] });
    },
  });

  const templateIds = new Set(templates.map((template) => template.id));
  const legacySystemScreens = screens.filter(
    (screen) => screen.is_system && !templateIds.has(String(screen.id)),
  );
  const savedScreens = screens.filter((screen) => !screen.is_system);
  const displayedTemplates = templates.filter((template) => {
    if (filter === 'custom') return false;
    if (!search.trim()) return true;
    const query = search.toLowerCase();
    return (
      template.label.toLowerCase().includes(query) ||
      template.id.toLowerCase().includes(query) ||
      (template.description && template.description.toLowerCase().includes(query))
    );
  });
  const displayedScreens = savedScreens.filter((screen) => {
    if (filter === 'system') return false;
    if (!search.trim()) return true;
    const query = search.toLowerCase();
    return (
      screen.name.toLowerCase().includes(query) ||
      (screen.description &&
        screen.description.toLowerCase().includes(query)) ||
      String(screen.id).toLowerCase().includes(query)
    );
  });
  const displayedSystemScreens = legacySystemScreens.filter((screen) => {
    if (filter === 'custom') return false;
    if (!search.trim()) return true;
    const query = search.toLowerCase();
    return (
      screen.name.toLowerCase().includes(query) ||
      (screen.description && screen.description.toLowerCase().includes(query)) ||
      String(screen.id).toLowerCase().includes(query)
    );
  });

  function selectScreen(screen: SavedScreen) {
    onSelectScreen(screen);
    onClose();
  }

  function selectTemplate(template: ScreenTemplateSummary) {
    onSelectTemplate(template.id);
    onClose();
  }

  const resultCount =
    displayedTemplates.length + displayedSystemScreens.length + displayedScreens.length;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        size="md"
        className="flex h-[min(42rem,calc(100dvh-2rem))] max-h-[calc(100dvh-2rem)] flex-col gap-0 overflow-hidden p-0"
      >
        <DialogHeader className="shrink-0 border-b border-border px-4 py-3 pr-12">
          <DialogTitle className="text-base">Load universe screen</DialogTitle>
          <DialogDescription className="sr-only">
            Choose a system screen or one of your saved screens.{' '}
            {templates.length + legacySystemScreens.length + savedScreens.length} available.
          </DialogDescription>
        </DialogHeader>

        <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/30 px-4 py-2">
          <div
            className="inline-flex min-w-0 flex-wrap rounded-md border border-border bg-background p-0.5"
            aria-label="Filter screens"
          >
            {(
              [
                [
                  'all',
                  `All (${templates.length + legacySystemScreens.length + savedScreens.length})`,
                ],
                [
                  'system',
                  `System (${templates.length + legacySystemScreens.length})`,
                ],
                ['custom', `Saved (${savedScreens.length})`],
              ] as const
            ).map(([category, label]) => (
              <Button
                key={category}
                type="button"
                variant={filter === category ? 'secondary' : 'ghost'}
                size="sm"
                className="h-8 px-2.5 text-xs"
                aria-pressed={filter === category}
                onClick={() => setFilter(category)}
              >
                {label}
              </Button>
            ))}
          </div>

          <Input
            type="search"
            placeholder="Search screens…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="h-9 w-full text-sm sm:w-48"
            aria-label="Search screens"
          />
        </div>

        <div className="min-h-0 flex-1 divide-y divide-border overflow-y-auto overscroll-y-contain [webkit-overflow-scrolling:touch]">
          {templatesError && filter !== 'custom' && (
            <div
              role="alert"
              className="border-b border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive"
            >
              Built-in templates could not be loaded: {templatesError}
            </div>
          )}
          {screensError && filter !== 'system' && (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-2 border-b border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive"
            >
              <span>Saved screens could not be loaded. Built-in templates remain available. {screensError}</span>
              {onRetryLoad && (
                <Button type="button" variant="outline" size="sm" onClick={onRetryLoad}>
                  Retry
                </Button>
              )}
            </div>
          )}
          {screensWarning && filter === 'all' && !screensError && (
            <div
              role="status"
              className="border-b border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground"
            >
              {screensWarning}
            </div>
          )}
          {resultCount === 0 && (screensLoading || templatesLoading) ? (
            <p
              role="status"
              className="p-8 text-center text-sm text-muted-foreground"
            >
              Loading screen catalog…
            </p>
          ) : resultCount === 0 &&
            (screensError || screensWarning || templatesError) ? null : resultCount === 0 ? (
            <p className="p-8 text-center text-sm text-muted-foreground">
              {search.trim()
                ? 'No screens match your search.'
                : filter === 'custom'
                  ? 'You have no saved screens yet. Save a screen from the Screener and it will appear here.'
                  : filter === 'system'
                    ? 'No built-in screens are available.'
                    : 'No screens are available yet.'}
            </p>
          ) : (
            <>
              {displayedTemplates.map((template) => (
                <div
                  key={`template:${template.id}`}
                  className="group flex items-center gap-2 px-4 py-3 transition-colors hover:bg-muted/40"
                >
                  <Button
                    type="button"
                    variant="ghost"
                    className="h-auto min-w-0 flex-1 flex-col items-start justify-center gap-1 whitespace-normal px-0 py-1 text-left"
                    onClick={() => selectTemplate(template)}
                    aria-label={`Load template ${template.label}`}
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-foreground">{template.label}</span>
                      <span className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground">
                        System template
                      </span>
                    </span>
                    {template.description && (
                      <span className="text-xs font-normal leading-snug text-muted-foreground">
                        {template.description}
                      </span>
                    )}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => selectTemplate(template)}
                  >
                    Load
                  </Button>
                </div>
              ))}
              {[...displayedSystemScreens, ...displayedScreens].map((screen) => (
              <div
                key={String(screen.id)}
                className="group flex items-center gap-2 px-4 py-3 transition-colors hover:bg-muted/40"
              >
                <Button
                  type="button"
                  variant="ghost"
                  className="h-auto min-w-0 flex-1 flex-col items-start justify-center gap-1 whitespace-normal px-0 py-1 text-left"
                  onClick={() => selectScreen(screen)}
                >
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-foreground">
                      {screen.name}
                    </span>
                    <span className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground">
                      {screen.is_system
                        ? 'System'
                        : screen.is_shared
                          ? 'Shared'
                          : 'My library'}
                    </span>
                  </span>
                  {screen.description ? (
                    <span className="text-xs font-normal leading-snug text-muted-foreground">
                      {screen.description}
                    </span>
                  ) : screen.created_at ? (
                    <span className="text-xs font-normal text-muted-foreground">
                      Saved {new Date(screen.created_at).toLocaleDateString()}
                    </span>
                  ) : null}
                </Button>

                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => selectScreen(screen)}
                  >
                    Load
                  </Button>
                  {!screen.is_system && !screen.is_shared && (
                    <ConfirmDialog
                      onContinue={() => deleteMutation.mutate(screen.id)}
                      variant="destructive"
                      title="Delete saved screen?"
                      description={`“${screen.name}” will be permanently deleted.`}
                      continueLabel="Delete screen"
                    >
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={deleteMutation.isPending}
                        className="h-9 w-9 text-muted-foreground hover:text-destructive sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                        aria-label={`Delete screen ${screen.name}`}
                        title="Delete screen"
                      >
                        <span aria-hidden="true">×</span>
                      </Button>
                    </ConfirmDialog>
                  )}
                </div>
              </div>
              ))}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
