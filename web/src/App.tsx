
import { useEffect, useState } from 'react';
import ChatPage from './pages/ChatPage';
import ReportsPage from './pages/ReportsPage';
import ProfilePage from './pages/ProfilePage';
import AuthModal from './components/AuthModal';
import { colors, fonts, gradient } from './components/styles';
import { AUTH_REQUIRED_EVENT, fetchMe, getToken, getStoredUser, clearSession, type AuthUser } from './api/auth';

type Page = 'chat' | 'reports' | 'profile';

function App() {
  const [page, setPage] = useState<Page>('chat');
  const [user, setUser] = useState<AuthUser | null>(() => getStoredUser());
  const [showAuth, setShowAuth] = useState(false);

  useEffect(() => {
    const onAuthRequired = () => {
      setUser(null);
      setShowAuth(true);
    };
    window.addEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    let active = true;
    if (getToken()) {
      void fetchMe().then(current => {
        if (active && current) setUser(current);
      }).catch(() => { /* Keep the session on temporary network failures. */ });
    } else {
      clearSession();
      setUser(null);
    }
    return () => {
      active = false;
      window.removeEventListener(AUTH_REQUIRED_EVENT, onAuthRequired);
    };
  }, []);

  const logout = () => {
    clearSession();
    setUser(null);
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      background: colors.bg, fontFamily: fonts.sans, color: colors.text,
    }}>
      {}
      <header style={{
        position: 'sticky', top: 0, zIndex: 20,
        display: 'flex', alignItems: 'center', gap: 8,
        height: 60, padding: '0 20px',
        background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(8px)',
        borderBottom: `1px solid ${colors.border}`,
      }}>
        <div
          onClick={() => setPage('chat')}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            cursor: 'pointer', userSelect: 'none',
          }}
        >
          <span style={{
            width: 34, height: 34, borderRadius: 12, flexShrink: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18,
            background: gradient.primary,
            boxShadow: '0 2px 8px rgba(14,159,143,0.30)',
          }}>
            🩺
          </span>
          <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: -0.3 }}>
            健康顾问
          </span>
        </div>

        <div style={{ flex: 1 }} />

        <nav style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <NavItem active={page === 'chat'} onClick={() => setPage('chat')}>问诊</NavItem>
          <NavItem active={page === 'reports'} onClick={() => setPage('reports')}>报告历史</NavItem>
          <NavItem active={page === 'profile'} onClick={() => setPage('profile')}>健康档案</NavItem>
        </nav>

        <div style={{ width: 1, height: 20, background: colors.border, margin: '0 8px' }} />

        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              display: 'flex', alignItems: 'center', gap: 8, fontSize: 13,
              fontWeight: 600, color: colors.text,
            }}>
              <span style={{
                width: 24, height: 24, borderRadius: '50%',
                background: gradient.primary,
                color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 700,
              }}>
                {(user.nickname || user.email || '用').slice(0, 1).toUpperCase()}
              </span>
              {user.nickname || user.email || '用户'}
            </span>
            <button
              onClick={logout}
              style={{
                padding: '6px 12px', fontSize: 12, fontWeight: 600,
                background: 'transparent', color: colors.textSecondary,
                border: `1px solid ${colors.border}`, borderRadius: 8, cursor: 'pointer',
              }}
            >
              退出
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: colors.textSecondary }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#059669' }} />
              试用模式
            </span>
            <button
              onClick={() => setShowAuth(true)}
              style={{
                padding: '6px 14px', fontSize: 13, fontWeight: 600,
                background: colors.primary, color: '#fff',
                border: 'none', borderRadius: 8, cursor: 'pointer',
              }}
            >
              登录 / 注册
            </button>
          </div>
        )}
      </header>

      {}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {page === 'chat' && <ChatPage />}
        {page === 'reports' && (
          <div style={{ maxWidth: 960, margin: '0 auto', width: '100%', padding: '24px 20px 60px' }}>
            <ReportsPage />
          </div>
        )}
        {page === 'profile' && (
          <div style={{ maxWidth: 960, margin: '0 auto', width: '100%', padding: '24px 20px 60px' }}>
            <ProfilePage />
          </div>
        )}
      </main>

      {showAuth && <AuthModal onClose={() => setShowAuth(false)} onAuthed={setUser} />}
    </div>
  );
}

function NavItem({
  active, onClick, children,
}: {
  active: boolean; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '6px 14px', fontSize: 13, borderRadius: 8, cursor: 'pointer',
        border: 'none', background: active ? colors.primaryLight : 'transparent',
        color: active ? colors.primary : colors.textSecondary,
        fontWeight: active ? 700 : 500, transition: 'all 0.15s',
      }}
    >
      {children}
    </button>
  );
}

export default App;
