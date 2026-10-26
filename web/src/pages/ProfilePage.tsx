
import { useState, useEffect, useCallback } from 'react';
import { colors, fonts, shadows } from '../components/styles';
import { apiFetch } from '../api/auth';

interface ProfileItem {
  id: string;
  kind: string;
  content: string;
  source: string;
  version?: number;
  pending_confirmation?: boolean;
  created_at?: string;
}

const KIND_LABELS: Record<string, { label: string; icon: string; color: string; bg: string }> = {
  basic:      { label: '基本信息', icon: '🧾', color: '#2563EB', bg: '#EFF6FF' },
  condition:  { label: '既往病史', icon: '🩺', color: '#DC2626', bg: '#FEF2F2' },
  medication: { label: '长期用药', icon: '💊', color: '#7C3AED', bg: '#F5F3FF' },
  allergy:    { label: '过敏史',   icon: '⚠️', color: '#D97706', bg: '#FFFBEB' },
  goal:       { label: '健康目标', icon: '🎯', color: '#059669', bg: '#ECFDF5' },
  exercise:   { label: '运动基础', icon: '🏃', color: '#0D9488', bg: '#F0FDFA' },
};

const PLACEHOLDERS: Record<string, string> = {
  basic: '输入基本信息，如：男 / 32 岁 / 身高 175cm',
  condition: '输入既往病史，如：高血压 3 年、脂肪肝',
  medication: '输入长期用药，如：二甲双胍 0.5g 每日两次',
  allergy: '输入过敏史，如：青霉素过敏、海鲜过敏',
  goal: '输入健康目标，如：减脂、控糖、改善血脂',
  exercise: '输入运动基础，如：每周跑步 3 次，每次 30 分钟',
};

const API_BASE = '';

export default function ProfilePage() {
  const [items, setItems] = useState<ProfileItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [newKind, setNewKind] = useState('basic');
  const [newContent, setNewContent] = useState('');
  const [saving, setSaving] = useState(false);

  const [editingId, setEditingId] = useState('');
  const [editContent, setEditContent] = useState('');

  const loadProfile = useCallback(async () => {
    try {
      const resp = await apiFetch(`${API_BASE}/api/v1/profile`);
      const json = await resp.json();
      if (json.code === 0) {
        setItems(json.data?.items || []);
      } else {
        setError(json.error?.message || '加载失败');
      }
    } catch {

      console.warn('Profile API 不可达，使用空列表');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const addItem = async () => {
    if (!newContent.trim()) return;
    setSaving(true);
    setError('');

    try {
      const resp = await apiFetch(`${API_BASE}/api/v1/profile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: newKind,
          content: newContent.trim(),
          source: 'user_stated',
        }),
      });
      const json = await resp.json();

      if (json.code === 0) {
        setNewContent('');

        await loadProfile();
      } else {
        setError(json.error?.message || '保存失败');
      }
    } catch (err) {

      console.warn('Profile API 不可达，本地添加');
      setItems((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          kind: newKind,
          content: newContent.trim(),
          source: 'user_stated',
        },
      ]);
      setNewContent('');
    } finally {
      setSaving(false);
    }
  };

  const startEdit = (item: ProfileItem) => {
    setEditingId(item.id);
    setEditContent(item.content);
  };

  const saveEdit = async (id: string) => {
    if (!editContent.trim()) return;
    try {
      const resp = await apiFetch(`${API_BASE}/api/v1/profile/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent.trim() }),
      });
      const json = await resp.json();
      if (json.code === 0) {
        await loadProfile();
      } else {
        setError(json.error?.message || '更新失败');
      }
    } catch {
      setError('更新失败：服务不可达');
    } finally {
      setEditingId('');
      setEditContent('');
    }
  };

  const confirmItem = async (id: string) => {
    try {
      const resp = await apiFetch(`${API_BASE}/api/v1/profile/${id}/confirm`, { method: 'POST' });
      const json = await resp.json();
      if (json.code === 0) {
        setItems((prev) =>
          prev.map((i) => (i.id === id ? { ...i, pending_confirmation: false } : i)),
        );
      } else {
        setError(json.error?.message || '确认失败');
      }
    } catch {
      setError('确认失败：服务不可达');
    }
  };

  const deleteItem = async (id: string) => {
    try {
      const resp = await apiFetch(`${API_BASE}/api/v1/profile/${id}`, { method: 'DELETE' });
      const json = await resp.json();
      if (json.code === 0) {
        setItems((prev) => prev.filter((i) => i.id !== id));
      } else {

        setItems((prev) => prev.filter((i) => i.id !== id));
      }
    } catch {

      setItems((prev) => prev.filter((i) => i.id !== id));
    }
  };

  const deleteAll = async () => {
    if (!confirm('确认删除全部档案？此操作不可恢复。')) return;

    try {
      await apiFetch(`${API_BASE}/api/v1/profile`, { method: 'DELETE' });
    } catch {
      console.warn('Profile API 不可达，本地全量删除');
    }
    setItems([]);
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: colors.textSecondary }}>
        ⏳ 加载中...
      </div>
    );
  }

  return (
    <div style={{ fontFamily: fonts.sans }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 20, flexWrap: 'wrap', gap: 10,
      }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: colors.text }}>
          📋 我的健康档案
        </h2>
        <button
          onClick={deleteAll}
          disabled={items.length === 0}
          style={{
            padding: '8px 16px', fontSize: 13, fontWeight: 600,
            background: items.length === 0 ? '#F1F5F9' : '#FEF2F2',
            color: items.length === 0 ? '#94A3B8' : '#DC2626',
            border: `1px solid ${items.length === 0 ? '#E2E8F0' : '#FECACA'}`,
            borderRadius: 8, cursor: items.length === 0 ? 'not-allowed' : 'pointer',
          }}
        >
          全量删除
        </button>
      </div>

      {error && (
        <div style={{
          marginBottom: 16, padding: '10px 14px', borderRadius: 8,
          background: '#FEF2F2', color: colors.danger, fontSize: 13,
          border: '1px solid #FEE2E2',
        }}>
          {error}
        </div>
      )}

      {}
      {items.length === 0 ? (
        <div style={{
          padding: 40, textAlign: 'center', color: colors.textSecondary,
          background: colors.bgCard, borderRadius: 10, border: `1px solid ${colors.border}`,
          marginBottom: 24,
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📭</div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
            暂无档案条目
          </div>
          <div style={{ fontSize: 13, opacity: 0.7 }}>
            补充既往病史、用药与运动基础，获取个性化健康建议
          </div>
        </div>
      ) : (
        <div style={{
          display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 24,
        }}>
          {items.map((item) => {
            const kind = KIND_LABELS[item.kind] || KIND_LABELS.basic;
            const editing = editingId === item.id;
            return (
              <div
                key={item.id}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '12px 16px', background: colors.bgCard, borderRadius: 8,
                  border: `1px solid ${item.pending_confirmation ? '#F59E0B' : colors.border}`,
                  boxShadow: shadows.card,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
                  <span style={{
                    padding: '3px 10px', borderRadius: 6, fontSize: 12, fontWeight: 600,
                    background: kind.bg, color: kind.color, whiteSpace: 'nowrap',
                  }}>
                    {kind.icon} {kind.label}
                  </span>
                  {editing ? (
                    <input
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && saveEdit(item.id)}
                      autoFocus
                      style={{
                        flex: 1, minWidth: 120, padding: '6px 10px', fontSize: 14,
                        border: `1px solid ${colors.primary}`, borderRadius: 6,
                        fontFamily: fonts.sans, outline: 'none',
                      }}
                    />
                  ) : (
                    <span style={{ fontWeight: 600, fontSize: 15, color: colors.text }}>
                      {item.content}
                    </span>
                  )}
                  <span style={{
                    fontSize: 11, color: colors.textSecondary,
                    background: '#F1F5F9', padding: '1px 6px', borderRadius: 3,
                    whiteSpace: 'nowrap',
                  }}>
                    {item.source === 'user_stated' ? '手动录入' : 'AI自动记录'}
                  </span>
                  {(item.version ?? 1) > 1 && (
                    <span style={{
                      fontSize: 11, color: colors.textSecondary, whiteSpace: 'nowrap',
                    }}>
                      v{item.version}
                    </span>
                  )}
                  {item.pending_confirmation && (
                    <span style={{
                      fontSize: 11, color: '#B45309', background: '#FEF3C7',
                      padding: '1px 6px', borderRadius: 3, whiteSpace: 'nowrap',
                    }}>
                      ⏳ 待确认
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 6, marginLeft: 10 }}>
                  {item.pending_confirmation && (
                    <button
                      onClick={() => confirmItem(item.id)}
                      style={{
                        padding: '5px 12px', fontSize: 12, fontWeight: 500,
                        background: '#ECFDF5', color: '#059669',
                        border: '1px solid #A7F3D0', borderRadius: 6, cursor: 'pointer',
                      }}
                    >
                      确认
                    </button>
                  )}
                  {editing ? (
                    <>
                      <button
                        onClick={() => saveEdit(item.id)}
                        style={{
                          padding: '5px 12px', fontSize: 12, fontWeight: 500,
                          background: colors.primary, color: '#fff',
                          border: 'none', borderRadius: 6, cursor: 'pointer',
                        }}
                      >
                        保存
                      </button>
                      <button
                        onClick={() => setEditingId('')}
                        style={{
                          padding: '5px 12px', fontSize: 12, fontWeight: 500,
                          background: 'transparent', color: colors.textSecondary,
                          border: `1px solid ${colors.border}`, borderRadius: 6, cursor: 'pointer',
                        }}
                      >
                        取消
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => startEdit(item)}
                      style={{
                        padding: '5px 12px', fontSize: 12, fontWeight: 500,
                        background: 'transparent', color: colors.primary,
                        border: `1px solid ${colors.border}`, borderRadius: 6, cursor: 'pointer',
                      }}
                    >
                      编辑
                    </button>
                  )}
                  <button
                    onClick={() => deleteItem(item.id)}
                    style={{
                      padding: '5px 12px', fontSize: 12, fontWeight: 500,
                      background: 'transparent', color: '#DC2626',
                      border: '1px solid #FECACA', borderRadius: 6, cursor: 'pointer',
                    }}
                  >
                    删除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {}
      <div style={{
        padding: 20, background: '#F8FAFC', borderRadius: 10,
        border: `1px solid ${colors.border}`,
      }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: 15, fontWeight: 700, color: colors.text }}>
          添加档案条目
        </h4>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <select
            value={newKind}
            onChange={(e) => setNewKind(e.target.value)}
            style={{
              padding: '8px 12px', fontSize: 14, border: `1px solid ${colors.border}`,
              borderRadius: 6, fontFamily: fonts.sans, minWidth: 120,
            }}
          >
            <option value="basic">基本信息</option>
            <option value="condition">既往病史</option>
            <option value="medication">长期用药</option>
            <option value="allergy">过敏史</option>
            <option value="goal">健康目标</option>
            <option value="exercise">运动基础</option>
          </select>
          <input
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder={PLACEHOLDERS[newKind] || '输入档案内容'}
            style={{
              flex: 1, minWidth: 160,
              padding: '8px 14px', fontSize: 14,
              border: `1px solid ${colors.border}`, borderRadius: 6,
              fontFamily: fonts.sans, outline: 'none',
            }}
            onFocus={e => (e.target.style.borderColor = colors.primary)}
            onBlur={e => (e.target.style.borderColor = colors.border)}
            onKeyDown={(e) => e.key === 'Enter' && addItem()}
          />
          <button
            onClick={addItem}
            disabled={saving || !newContent.trim()}
            style={{
              padding: '8px 20px', fontSize: 14, fontWeight: 600,
              background: saving || !newContent.trim() ? '#E2E8F0' : colors.primary,
              color: saving || !newContent.trim() ? '#94A3B8' : '#fff',
              border: 'none', borderRadius: 6, cursor: saving || !newContent.trim() ? 'not-allowed' : 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {saving ? '保存中...' : '添加'}
          </button>
        </div>
      </div>
    </div>
  );
}
