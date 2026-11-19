import StudioWorkbench from '../../../../../studio/frontend/src/App';

export const SigmaRailWorkbench = () => (
  <div data-testid="workbench-route-frame" className="flex min-w-0 w-full flex-1 flex-col">
    <StudioWorkbench embedded />
  </div>
);

export default SigmaRailWorkbench;
