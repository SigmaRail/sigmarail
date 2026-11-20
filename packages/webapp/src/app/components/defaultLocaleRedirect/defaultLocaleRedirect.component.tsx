import { useAvailableLocales } from '@sb/webapp-core/hooks';
import { Loader2 } from 'lucide-react';
import { Navigate, useLocation } from 'react-router-dom';

/**
 * Redirects to the default locale configured in the admin panel.
 * 
 * Waits for the locales to be fetched from the API to ensure
 * we redirect to the correct default language.
 */
export const DefaultLocaleRedirect = () => {
  const { pathname, search } = useLocation();
  const { defaultLocale, isLoading } = useAvailableLocales();

  // Wait for locales to load before redirecting
  // This ensures we get the correct default from the admin panel
  if (isLoading) {
    return (
      <div role="status" aria-live="polite" className="flex min-h-[40vh] items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        Loading SigmaRail…
      </div>
    );
  }

  // Build the redirect path
  // If we're at "/", redirect to "/{locale}"
  // If we're at "/something", redirect to "/{locale}/something"
  const redirectPath = pathname === '/' 
    ? `/${defaultLocale}` 
    : `/${defaultLocale}${pathname}`;

  return <Navigate to={`${redirectPath}${search}`} replace />;
};

