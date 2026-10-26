
import { useState } from 'react';
import { login, register, type AuthUser } from '../api/auth';
import { colors, fonts, shadows } from './styles';

interface AuthModalProps {
  onClose: () => void;
  onAuthed: (user: AuthUser) => void;
}

export default function AuthModal({ onClose, onAuthed }: AuthModalProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [nickname, setNickname] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (!email.trim() || !password.trim()) {
      setError('请输入邮箱和密码');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const data = mode === 'login'
        ? await login(email.trim(), password)
        : await register(email.trim(), password, nickname.trim() || undefined);
      onAuthed(data.user);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败');
    } finally {
      setLoading(false);
    }
  };

  const switchMode = () => {
    setMode(mode === 'login' ? 'register' : 'login');
    setError('');
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(15,23,42,0.45)', backdropFilter: 'blur(2px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 400,
          background: colors.bgCard, borderRadius: 16,
          boxShadow: shadows.elevated, padding: '28px 28px 24px',
          fontFamily: fonts.sans,
        }}
      >
        {}
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
          <span style={{ fontSize: 20, fontWeight: 800, color: colors.text }}>
            {mode === 'login' ? '登录' : '注册'}
          </span>
          <div style={{ flex: 1 }} />
          <button
            onClick={onClose}
            aria-label="关闭"
            style={{
              width: 28, height: 28, borderRadius: 8, border: 'none',
              background: colors.bg, color: colors.textSecondary,
              cursor: 'pointer', fontSize: 16, lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        {}
        {error && (
          <div style={{
            marginBottom: 14, padding: '10px 12px', borderRadius: 8,
            background: '#FEF2F2', color: colors.danger, fontSize: 13,
            border: '1px solid #FEE2E2',
          }}>
            {error}
          </div>
        )}

        {}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {mode === 'register' && (
            <Field label="昵称（可选）">
              <input
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                placeholder="例如：小明"
                style={inputStyle}
              />
            </Field>
          )}
          <Field label="邮箱">
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              type="email"
              autoFocus
              style={inputStyle}
            />
          </Field>
          <Field label="密码">
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submit()}
              placeholder={mode === 'register' ? '至少 6 位' : '请输入密码'}
              type="password"
              style={inputStyle}
            />
          </Field>

          <button
            onClick={submit}
            disabled={loading}
            style={{
              marginTop: 6, padding: '11px 16px', fontSize: 15, fontWeight: 700,
              background: loading ? '#8FD9D2' : colors.primary, color: '#fff',
              border: 'none', borderRadius: 8, cursor: loading ? 'not-allowed' : 'pointer',
            }}
          >
            {loading ? '处理中...' : mode === 'login' ? '登录' : '注册并登录'}
          </button>
        </div>

        {}
        <div style={{ marginTop: 16, textAlign: 'center', fontSize: 13, color: colors.textSecondary }}>
          {mode === 'login' ? '还没有账号？' : '已有账号？'}
          <button
            onClick={switchMode}
            style={{
              border: 'none', background: 'transparent', cursor: 'pointer',
              color: colors.primary, fontWeight: 600, fontSize: 13,
            }}
          >
            {mode === 'login' ? '去注册' : '去登录'}
          </button>
        </div>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '9px 12px', fontSize: 14,
  border: `1px solid ${colors.border}`, borderRadius: 8,
  fontFamily: fonts.sans, outline: 'none', boxSizing: 'border-box',
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: colors.textSecondary }}>{label}</span>
      {children}
    </label>
  );
}
