import { useMutation } from '@apollo/client/react';
import { getFragmentData } from '@sb/webapp-api-client/graphql';
import { commonQueryCurrentUserFragment, useCommonQuery } from '@sb/webapp-api-client/providers';
import { useTheme } from '@sb/webapp-core/hooks/useTheme/useTheme';
import { ThemeMode } from '@sb/webapp-core/providers/themeProvider';
import { useToast } from '@sb/webapp-core/toast/useToast';
import { useCallback, useEffect } from 'react';

import { authUpdateUserProfileMutation } from '../components/auth/editProfileForm/editProfileForm.graphql';

export const useAppearancePreference = () => {
  const { data } = useCommonQuery();
  const profile = getFragmentData(commonQueryCurrentUserFragment, data?.currentUser);
  const { themePreference, setTheme } = useTheme();
  const [updateUserProfile] = useMutation(authUpdateUserProfileMutation);
  const { toast } = useToast();

  useEffect(() => {
    const savedPreference = profile?.appearance;
    if (savedPreference && Object.values(ThemeMode).includes(savedPreference as ThemeMode)) {
      setTheme(savedPreference as ThemeMode);
    }
  }, [profile?.id, profile?.appearance, setTheme]);

  const updateAppearance = useCallback(
    (mode: ThemeMode) => {
      setTheme(mode);
      if (!profile) return;

      void updateUserProfile({ variables: { input: { appearance: mode } } }).catch((error: unknown) => {
        toast({
          title: 'Appearance was not saved',
          description: error instanceof Error ? error.message : 'Please try again.',
          variant: 'destructive',
        });
      });
    },
    [profile, setTheme, toast, updateUserProfile]
  );

  return { themePreference, setTheme: updateAppearance };
};

export const AppearancePreferenceSync = () => {
  useAppearancePreference();
  return null;
};
