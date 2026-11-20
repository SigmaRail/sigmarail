import {
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from '@sb/webapp-core/components/ui/dropdown-menu';
import { ThemeMode } from '@sb/webapp-core/providers/themeProvider';
import { Check, Laptop, Moon, Sun } from 'lucide-react';
import { FormattedMessage } from 'react-intl';

import { useAppearancePreference } from '../../hooks/useAppearancePreference';

export const AppearanceMenu = () => {
  const { themePreference, setTheme } = useAppearancePreference();

  return (
    <DropdownMenuSub>
      <DropdownMenuSubTrigger className="cursor-pointer gap-2">
        <Laptop className="h-4 w-4 shrink-0" />
        <FormattedMessage defaultMessage="Appearance" id="Appearance menu / Label" />
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="w-44">
        <DropdownMenuItem onSelect={() => setTheme(ThemeMode.LIGHT)} className="cursor-pointer gap-2">
          <Sun className="h-4 w-4 shrink-0" />
          <FormattedMessage defaultMessage="Light" id="Appearance menu / Light" />
          {themePreference === ThemeMode.LIGHT && <Check className="ml-auto h-4 w-4" />}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setTheme(ThemeMode.DARK)} className="cursor-pointer gap-2">
          <Moon className="h-4 w-4 shrink-0" />
          <FormattedMessage defaultMessage="Dark" id="Appearance menu / Dark" />
          {themePreference === ThemeMode.DARK && <Check className="ml-auto h-4 w-4" />}
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setTheme(ThemeMode.SYSTEM)} className="cursor-pointer gap-2">
          <Laptop className="h-4 w-4 shrink-0" />
          <FormattedMessage defaultMessage="System" id="Appearance menu / System" />
          {themePreference === ThemeMode.SYSTEM && <Check className="ml-auto h-4 w-4" />}
        </DropdownMenuItem>
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
};
