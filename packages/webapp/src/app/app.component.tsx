import { DEFAULT_LOCALE } from '@sb/webapp-core/config/i18n';
import { DynamicIntlProvider } from '@sb/webapp-core/providers';
import { useGenerateLocalePath } from '@sb/webapp-core/hooks';
import { PermissionAuthRoute } from '@sb/webapp-tenants/components/routes/permissionAuthRoute';
import { lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { Role } from '../modules/auth/auth.types';
import { AnonymousRoute, AuthRoute } from '../shared/components/routes';
import { ConfirmEmail, Login, Logout, NotFound, Profile, Signup, SSOCallback, SSOError, SSOLogin } from './asyncComponents';
import { LANG_PREFIX, RoutesConfig, TENANT_PREFIX } from './config/routes';
import { ValidRoutesProviders } from './providers';

const SigmaRailWorkbench = lazy(() => import('../routes/sigmaRail'));
const Admin = lazy(() => import('../routes/admin').then(({ Admin }) => ({ default: Admin })));
const PasswordReset = lazy(() => import('../routes/auth/passwordReset').then(({ PasswordReset }) => ({ default: PasswordReset })));
const ValidateOtp = lazy(() => import('../routes/auth/validateOtp'));

const DemoItem = lazy(() => import('@sb/webapp-contentful/routes').then(({ DemoItem }) => ({ default: DemoItem })));
const DemoItems = lazy(() => import('@sb/webapp-contentful/routes').then(({ DemoItems }) => ({ default: DemoItems })));
const PrivacyPolicy = lazy(() => import('@sb/webapp-contentful/routes').then(({ PrivacyPolicy }) => ({ default: PrivacyPolicy })));
const TermsAndConditions = lazy(() => import('@sb/webapp-contentful/routes').then(({ TermsAndConditions }) => ({ default: TermsAndConditions })));
const CrudDemoItem = lazy(() => import('@sb/webapp-crud-demo/routes').then(({ CrudDemoItem }) => ({ default: CrudDemoItem })));
const Documents = lazy(() => import('@sb/webapp-documents/routes').then(({ Documents }) => ({ default: Documents })));
const ActiveSubscriptionContext = lazy(() => import('@sb/webapp-finances/components/activeSubscriptionContext').then(({ ActiveSubscriptionContext }) => ({ default: ActiveSubscriptionContext })));
const CancelSubscription = lazy(() => import('@sb/webapp-finances/routes').then(({ CancelSubscription }) => ({ default: CancelSubscription })));
const CurrentSubscriptionContent = lazy(() => import('@sb/webapp-finances/routes').then(({ CurrentSubscriptionContent }) => ({ default: CurrentSubscriptionContent })));
const EditPaymentMethod = lazy(() => import('@sb/webapp-finances/routes').then(({ EditPaymentMethod }) => ({ default: EditPaymentMethod })));
const EditSubscription = lazy(() => import('@sb/webapp-finances/routes').then(({ EditSubscription }) => ({ default: EditSubscription })));
const PaymentConfirm = lazy(() => import('@sb/webapp-finances/routes').then(({ PaymentConfirm }) => ({ default: PaymentConfirm })));
const PaymentMethodContent = lazy(() => import('@sb/webapp-finances/routes').then(({ PaymentMethodContent }) => ({ default: PaymentMethodContent })));
const Subscriptions = lazy(() => import('@sb/webapp-finances/routes').then(({ Subscriptions }) => ({ default: Subscriptions })));
const TransactionHistory = lazy(() => import('@sb/webapp-finances/routes').then(({ TransactionHistory }) => ({ default: TransactionHistory })));
const TransactionsHistoryContent = lazy(() => import('@sb/webapp-finances/routes').then(({ TransactionsHistoryContent }) => ({ default: TransactionsHistoryContent })));
const SaasIdeas = lazy(() => import('@sb/webapp-generative-ai/routes').then(({ SaasIdeas }) => ({ default: SaasIdeas })));
const TenantBackupSettings = lazy(() => import('@sb/webapp-backup').then(({ TenantBackupSettings }) => ({ default: TenantBackupSettings })));
const AccessDenied = lazy(() => import('@sb/webapp-tenants/routes').then(({ AccessDenied }) => ({ default: AccessDenied })));
const AddTenantForm = lazy(() => import('@sb/webapp-tenants/routes').then(({ AddTenantForm }) => ({ default: AddTenantForm })));
const TenantActivityLogs = lazy(() => import('@sb/webapp-tenants/routes').then(({ TenantActivityLogs }) => ({ default: TenantActivityLogs })));
const TenantGeneralSettings = lazy(() => import('@sb/webapp-tenants/routes').then(({ TenantGeneralSettings }) => ({ default: TenantGeneralSettings })));
const TenantInvitation = lazy(() => import('@sb/webapp-tenants/routes').then(({ TenantInvitation }) => ({ default: TenantInvitation })));
const TenantMembers = lazy(() => import('@sb/webapp-tenants/routes').then(({ TenantMembers }) => ({ default: TenantMembers })));
const TenantRoles = lazy(() => import('@sb/webapp-tenants/routes').then(({ TenantRoles }) => ({ default: TenantRoles })));
const TenantSecuritySettings = lazy(() => import('@sb/webapp-tenants/routes').then(({ TenantSecuritySettings }) => ({ default: TenantSecuritySettings })));
const TenantSettings = lazy(() => import('@sb/webapp-tenants/routes').then(({ TenantSettings }) => ({ default: TenantSettings })));

const ResearchHomeRedirect = () => {
  const generateLocalePath = useGenerateLocalePath();
  return <Navigate to={generateLocalePath('screens')} replace />;
};

export const App = () => {
  return (
    <Routes>
      <Route element={<ValidRoutesProviders />}>
        <Route path={LANG_PREFIX}>
          <Route path={RoutesConfig.logout} element={<Logout />} />

          <Route element={<AnonymousRoute />}>
            <Route path={RoutesConfig.signup} element={<Signup />} />
            <Route path={RoutesConfig.login} element={<Login />} />
            <Route path={RoutesConfig.validateOtp} element={<ValidateOtp />} />
            {/* SSO routes - accessible without authentication */}
            <Route path={RoutesConfig.ssoLogin} element={<SSOLogin />} />
            <Route path={RoutesConfig.ssoCallback} element={<SSOCallback />} />
            <Route path={RoutesConfig.ssoError} element={<SSOError />} />
            <Route path="*" element={<NotFound />} />
          </Route>

          {/* SigmaRail product routes live in the AppTension authenticated application shell. */}
          <Route element={<AuthRoute />}>
            <Route path="screens/*" element={<SigmaRailWorkbench />} />
            <Route path="charts/*" element={<SigmaRailWorkbench />} />
            <Route path="stock/*" element={<SigmaRailWorkbench />} />
            <Route path="watchlists/*" element={<SigmaRailWorkbench />} />
            <Route path="market/*" element={<SigmaRailWorkbench />} />
            <Route path="strategies/*" element={<SigmaRailWorkbench />} />
            <Route path="backtests/*" element={<SigmaRailWorkbench />} />
            <Route path="optimize/*" element={<SigmaRailWorkbench />} />
            <Route path="deploy/*" element={<SigmaRailWorkbench />} />
            <Route path="monitor/*" element={<SigmaRailWorkbench />} />
          </Route>

          <Route path={TENANT_PREFIX} element={<AuthRoute />}>
            <Route index element={<ResearchHomeRedirect />} />
            {/* Organization Settings - each sub-route has its own permission check */}
            <Route element={<PermissionAuthRoute permissions={['org.settings.view', 'members.view', 'org.roles.view', 'security.view', 'security.logs.view']} mode="any" />}>
              <Route element={<TenantSettings />}>
                {/* Members route - requires members.view */}
                <Route element={<PermissionAuthRoute permissions="members.view" />}>
                  <Route path={RoutesConfig.tenant.settings.members} element={<TenantMembers />} />
                </Route>
                {/* General settings - requires org.settings.view */}
                <Route element={<PermissionAuthRoute permissions="org.settings.view" />}>
                  <Route path={RoutesConfig.tenant.settings.general} element={<TenantGeneralSettings />} />
                </Route>
                {/* Security settings - requires security.view */}
                <Route element={<PermissionAuthRoute permissions="security.view" />}>
                  <Route path={RoutesConfig.tenant.settings.security} element={<TenantSecuritySettings />} />
                </Route>
                {/* Activity logs - requires security.logs.view */}
                <Route element={<PermissionAuthRoute permissions="security.logs.view" />}>
                  <Route path={RoutesConfig.tenant.settings.activityLogs} element={<TenantActivityLogs />} />
                </Route>
                {/* Roles management - requires org.roles.view to see, org.roles.manage to edit */}
                <Route element={<PermissionAuthRoute permissions="org.roles.view" />}>
                  <Route path={RoutesConfig.tenant.settings.roles} element={<TenantRoles />} />
                </Route>
                {/* Backup settings - requires backup.view */}
                <Route element={<PermissionAuthRoute permissions="backup.view" />}>
                  <Route path={RoutesConfig.tenant.settings.backup} element={<TenantBackupSettings />} />
                </Route>
              </Route>
            </Route>
            {/* Billing/Subscriptions - requires billing.view */}
            <Route element={<PermissionAuthRoute permissions="billing.view" />}>
              <Route element={<ActiveSubscriptionContext />}>
                <Route element={<Subscriptions />}>
                  <Route index path={RoutesConfig.subscriptions.index} element={<CurrentSubscriptionContent />} />
                  <Route path={RoutesConfig.subscriptions.paymentMethods.index} element={<PaymentMethodContent />} />
                  <Route
                    path={RoutesConfig.subscriptions.transactionHistory.index}
                    element={<TransactionsHistoryContent />}
                  />
                </Route>
                <Route path={RoutesConfig.subscriptions.currentSubscription.edit} element={<EditSubscription />} />
                <Route path={RoutesConfig.subscriptions.currentSubscription.cancel} element={<CancelSubscription />} />
                <Route path={RoutesConfig.subscriptions.paymentMethods.edit} element={<EditPaymentMethod />} />
              </Route>
              <Route path={RoutesConfig.finances.paymentConfirm} element={<PaymentConfirm />} />
              <Route path={RoutesConfig.subscriptions.transactionHistory.history} element={<TransactionHistory />} />
            </Route>
            {/* Content Items - protected by features.content.view */}
            <Route element={<PermissionAuthRoute permissions="features.content.view" />}>
              <Route path={RoutesConfig.demoItems} element={<DemoItems />} />
              <Route path={RoutesConfig.demoItem} element={<DemoItem routesConfig={{ notFound: RoutesConfig.notFound, list: RoutesConfig.demoItems }} />} />
            </Route>
            {/* CRUD Demo - protected by features.crud.view */}
            <Route element={<PermissionAuthRoute permissions="features.crud.view" />}>
              <Route path={RoutesConfig.crudDemoItem.index} element={<CrudDemoItem routesConfig={RoutesConfig} />} />
            </Route>
            {/* Documents - protected by features.documents.view */}
            <Route element={<PermissionAuthRoute permissions="features.documents.view" />}>
              <Route path={RoutesConfig.documents} element={<Documents />} />
            </Route>
            {/* OpenAI Integration - protected by features.ai.use */}
            <Route element={<PermissionAuthRoute permissions="features.ai.use" />}>
              <Route path={RoutesConfig.saasIdeas} element={<SaasIdeas />} />
            </Route>
            <Route path={RoutesConfig.tenant.accessDenied} element={<AccessDenied />} />
            <Route path="*" element={<NotFound />} />
          </Route>

          <Route element={<AuthRoute />}>
            <Route path={RoutesConfig.profile} element={<Profile />} />
            <Route path={RoutesConfig.addTenant} element={<AddTenantForm />} />
            <Route path={RoutesConfig.tenantInvitation} element={<TenantInvitation />} />
            <Route path="*" element={<NotFound />} />
          </Route>

          <Route element={<AuthRoute allowedRoles={Role.ADMIN} />}>
            <Route path={RoutesConfig.admin} element={<Admin />} />
          </Route>

          <Route path={RoutesConfig.confirmEmail} element={<ConfirmEmail />} />
          <Route path={RoutesConfig.privacyPolicy} element={<PrivacyPolicy />} />
          <Route path={RoutesConfig.termsAndConditions} element={<TermsAndConditions />} />
          <Route path={RoutesConfig.passwordReset.index} element={<PasswordReset />} />
        </Route>

        {/* <-- INJECT ROUTE --> */}

        <Route
          path="*"
          element={
            <DynamicIntlProvider locale={DEFAULT_LOCALE}>
              <NotFound />
            </DynamicIntlProvider>
          }
        />
      </Route>
    </Routes>
  );
};

export default App;
