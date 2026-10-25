import { Activity, GitBranch, LogOut, ScrollText, Server, Workflow } from 'lucide-react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth';

const baseNavigation = [
  { to: '/flows', label: 'Flows', icon: Workflow },
  { to: '/runs', label: 'Runs', icon: Activity },
  { to: '/settings/providers', label: 'Providers', icon: Server },
];

export function AppShell() {
  const { state, logOut } = useAuth();
  const navigate = useNavigate();
  const user = state.phase === 'authenticated' ? state.user : null;
  const navigation =
    user?.role === 'admin'
      ? [...baseNavigation, { to: '/audit', label: 'Audit', icon: ScrollText }]
      : baseNavigation;

  const handleLogout = async () => {
    await logOut();
    navigate('/login');
  };

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <GitBranch size={19} />
          </span>
          <div>
            <strong>AgentFlow</strong>
            <small>Operations</small>
          </div>
        </div>

        <nav aria-label="Primary">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              <item.icon size={17} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          {user && (
            <>
              <span className="user-name">{user.display_name ?? user.username}</span>
              <span>{user.role}</span>
            </>
          )}
          <button type="button" className="ghost-button" onClick={handleLogout}>
            <LogOut size={16} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <main className="main-frame">
        <Outlet />
      </main>
    </div>
  );
}
