import { useGenerateLocalePath, useLocale } from '@sb/webapp-core/hooks';
import { createSearchParams, useLocation } from 'react-router-dom';

export const useGenerateRedirectSearchParams = () => {
  const generateLocalePath = useGenerateLocalePath();
  const locale = useLocale();
  const { pathname, search, hash } = useLocation();

  const generateRedirectSearchParams = () => {
    const re = new RegExp(`/${locale}/?`);
    const pathnameWithoutLocale = pathname.replace(re, '');
    const redirect = `${generateLocalePath(pathnameWithoutLocale)}${search}${hash}`;
    return pathnameWithoutLocale ? createSearchParams({ redirect }).toString() : undefined;
  };

  return generateRedirectSearchParams;
};
