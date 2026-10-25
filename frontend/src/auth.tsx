import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import {
  getCurrentUser,
  login as loginRequest,
  logout as logoutRequest,
  type CurrentUser,
} from './api';

type AuthState =
  { phase: 'loading' } | { phase: 'authenticated'; user: CurrentUser } | { phase: 'anonymous' };

type AuthContextValue = {
  state: AuthState;
  logIn: (username: string, password: string) => Promise<void>;
  logOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ phase: 'loading' });

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((user) => {
        if (active) setState({ phase: 'authenticated', user });
      })
      .catch(() => {
        if (active) setState({ phase: 'anonymous' });
      });
    return () => {
      active = false;
    };
  }, []);

  const logIn = useCallback(async (username: string, password: string) => {
    const user = await loginRequest(username, password);
    setState({ phase: 'authenticated', user });
  }, []);

  const logOut = useCallback(async () => {
    try {
      await logoutRequest();
    } catch {
      // An expired server session is still logged out on the client.
    }
    setState({ phase: 'anonymous' });
  }, []);

  const value = useMemo(() => ({ state, logIn, logOut }), [state, logIn, logOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
