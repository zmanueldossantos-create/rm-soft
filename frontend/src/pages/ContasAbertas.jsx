import OpenAccountsPanel from '../components/OpenAccountsPanel';

// The open accounts page (waiters, managers): the shared panel in full page, every point of sale of the activity.
// The cashier reaches the same panel from the till's side bar, limited to that till.
export default function ContasAbertas() {
  return <OpenAccountsPanel />;
}
