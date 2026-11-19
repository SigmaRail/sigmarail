import { currentUserFactory, fillCommonQueryWithUser } from '@sb/webapp-api-client/tests/factories';
import { screen } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router-dom';

import { Role } from '../../../../../modules/auth/auth.types';
import { render } from '../../../../../tests/utils/rendering';
import { AuthRoute, AuthRouteProps } from '../authRoute.component';

describe('AuthRoute: Component', () => {
  const defaultProps: AuthRouteProps = {};
  const LoginLocation = () => {
    const location = useLocation();
    return <span data-testid="login-location">{location.search}</span>;
  };

  const Component = (props: Partial<AuthRouteProps>) => (
    <Routes>
      <Route path="*" element={<AuthRoute {...defaultProps} {...props} />}>
        <Route index element={<span data-testid="content" />} />
      </Route>
      <Route path="/en/auth/login" element={<LoginLocation />} />
      <Route path="/en/404" element={<span data-testid="404-content" />} />
    </Routes>
  );

  describe('user profile is fetched', () => {
    describe('no allowedRoles prop is specified', () => {
      it('should render content', async () => {
        const apolloMocks = [
          fillCommonQueryWithUser(
            currentUserFactory({
              roles: [Role.ADMIN],
            })
          ),
        ];
        render(<Component />, { apolloMocks });
        expect(await screen.findByTestId('content')).toBeInTheDocument();
      });
    });

    describe('user has required role', () => {
      it('should render content', async () => {
        const apolloMocks = [
          fillCommonQueryWithUser(
            currentUserFactory({
              roles: [Role.ADMIN],
            })
          ),
        ];
        render(<Component allowedRoles={Role.ADMIN} />, { apolloMocks });
        expect(await screen.findByTestId('content')).toBeInTheDocument();
      });
    });

    describe('user doesnt have required role', () => {
      it('should redirect to not found page', async () => {
        const apolloMocks = [
          fillCommonQueryWithUser(
            currentUserFactory({
              roles: [Role.USER],
            })
          ),
        ];
        render(<Component allowedRoles={Role.ADMIN} />, { apolloMocks });
        expect(await screen.findByTestId('404-content')).toBeInTheDocument();
        expect(screen.queryByTestId('content')).not.toBeInTheDocument();
      });
    });

    describe('user is not logged in', () => {
      it('should redirect to login page', async () => {
        render(<Component allowedRoles={Role.ADMIN} />, {
          routerProps: { initialEntries: ['/en/stock/JOB/chart?as_of=2026-11-15'] },
        });
        expect(await screen.findByTestId('login-location')).toHaveTextContent(
          'redirect=%2Fen%2Fstock%2FJOB%2Fchart%3Fas_of%3D2026-11-15',
        );
        expect(screen.queryByTestId('content')).not.toBeInTheDocument();
      });
    });
  });
});
