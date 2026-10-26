
import { useState, useCallback, useRef } from 'react';
import { colors, shadows } from './styles';
import { apiFetch } from '../api/auth';

export interface MemoryProposalItem {
  candidateId: string;
  kind: string;
  label: string;
  detail: string;
  confidence: number;
}

interface MissingInfoData {
  items: string[];
  guidance: string;
}

interface PublishSummary {
  reportVersion: string;
  abnormalMetricCount: number;
  evidenceCount: number;
  sections: string[];
}

export type HITLAction = 'awaiting_images' | 'awaiting_memory_confirm' | 'awaiting_publish_confirm';

interface Props {
  action: HITLAction;
  taskId: string;
  missingInfo?: MissingInfoData;
  proposals?: MemoryProposalItem[];
  publishSummary?: PublishSummary;
  onResume: (resumeData: {
    action: string;
    new_image_keys?: string[];
    new_images?: { key: string; position: string }[];
    decisions?: { candidate_id: string; accepted: boolean }[];
  }) => Promise<void>;
  onCancel?: () => void;
}

const KIND_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  basic:      { label: '🧾 基本信息',  color: '#2563EB', bg: '#EFF6FF' },
  condition:  { label: '🩺 既往病史',  color: '#DC2626', bg: '#FEF2F2' },
  medication: { label: '💊 长期用药',  color: '#7C3AED', bg: '#F5F3FF' },
  allergy:    { label: '⚠️ 过敏史',    color: '#D97706', bg: '#FFFBEB' },
  goal:       { label: '🎯 健康目标',  color: '#059669', bg: '#ECFDF5' },
  exercise:   { label: '🏃 运动基础',  color: '#0D9488', bg: '#F0FDFA' },
};

const RETAKE_POSITIONS = [
  { key: 'exam_report', label: '体检报告首页' },
  { key: 'lab_sheet', label: '化验单' },
  { key: 'other', label: '其他资料' },
];

function MissingImagesPrompt({ missingInfo, onResume, onCancel }: {
  missingInfo: MissingInfoData;
  taskId: string;
  onResume: Props['onResume'];
  onCancel?: () => void;
}) {
  const [newImages, setNewImages] = useState<{ key: string; position: string }[]>([]);
  const [position, setPosition] = useState('exam_report');
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const uploadFile = useCallback(async (file: File, pos: string) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('position', pos);
    const resp = await apiFetch('/api/v1/uploads', { method: 'POST', body: formData });
    const json = await resp.json();
    if (json.code !== 0) throw new Error(json.error?.message || '上传失败');
    return {
      key: json.data.image_key as string,
      position: (json.data.position as string) || pos,
    };
  }, []);

  const handleFiles = useCallback(async (files: FileList) => {
    setUploading(true);
    const next = [...newImages];
    for (const f of Array.from(files)) {
      try {
        next.push(await uploadFile(f, position));
      } catch (e) {
        console.error('补图上传失败:', e);
      }
    }
    setNewImages(next);
    setUploading(false);
  }, [newImages, uploadFile, position]);

  const handleResume = () => {
    onResume({
      action: 'add_images',
      new_images: newImages,
      new_image_keys: newImages.map(i => i.key),
    });
  };

  return (
    <div style={{
      background: '#FFF7ED', borderRadius: 12, padding: 24,
      border: '1.5px solid #FBBF24', boxShadow: shadows.card, marginBottom: 24,
    }}>
      {}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ fontSize: 28 }}>📸</span>
        <div>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: '#92400E' }}>
            需要补充体检材料
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: 13, color: '#A16207' }}>
            请按下列具体动作补充体检报告图片（选择正确图位），然后继续分析
          </p>
        </div>
      </div>

      {}
      <div style={{ marginBottom: 20 }}>
        {missingInfo.items.map((item, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 0',
            borderBottom: i < missingInfo.items.length - 1 ? '1px solid #FDE68A' : 'none',
          }}>
            <span style={{
              width: 22, height: 22, borderRadius: '50%', background: '#FBBF24',
              color: '#fff', fontSize: 12, fontWeight: 700, display: 'flex',
              alignItems: 'center', justifyContent: 'center', flexShrink: 0,
            }}>
              {i + 1}
            </span>
            <span style={{ fontSize: 14, color: '#78350F', lineHeight: 1.6 }}>{item}</span>
          </div>
        ))}
      </div>

      {}
      <div style={{
        padding: '10px 14px', background: '#FFFBEB', borderRadius: 8,
        fontSize: 12, color: '#92400E', marginBottom: 16, lineHeight: 1.6,
      }}>
        💡 {missingInfo.guidance}
      </div>

      {}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        {RETAKE_POSITIONS.map(p => (
          <button
            key={p.key}
            type="button"
            onClick={() => setPosition(p.key)}
            style={{
              padding: '4px 10px', fontSize: 12, borderRadius: 14, cursor: 'pointer',
              border: position === p.key ? '1.5px solid #D97706' : '1px solid #FDE68A',
              background: position === p.key ? '#FEF3C7' : '#fff',
              color: '#92400E', fontWeight: position === p.key ? 700 : 400,
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      {}
      <input
        ref={fileRef} type="file" accept="image/*,application/pdf" multiple
        style={{ display: 'none' }}
        onChange={e => e.target.files && handleFiles(e.target.files)}
      />
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          style={{
            padding: '10px 20px', fontSize: 13, fontWeight: 600,
            background: colors.bgCard, color: '#92400E',
            border: '1.5px dashed #FBBF24', borderRadius: 8, cursor: 'pointer',
          }}
        >
          {uploading ? '⏳ 上传中...' : '📎 补充文件'}
        </button>

        {newImages.length > 0 && (
          <>
            <span style={{ fontSize: 13, color: '#059669', fontWeight: 600 }}>
              ✅ 已上传 {newImages.length} 张
              （{newImages.map(i => RETAKE_POSITIONS.find(p => p.key === i.position)?.label || i.position).join('、')}）
            </span>
            <button
              onClick={handleResume}
              style={{
                padding: '10px 24px', fontSize: 13, fontWeight: 700,
                background: '#FBBF24', color: '#78350F', border: 'none',
                borderRadius: 8, cursor: 'pointer',
              }}
            >
              继续分析 →
            </button>
          </>
        )}

        {onCancel && (
          <button
            onClick={onCancel}
            style={{
              padding: '10px 16px', fontSize: 13, background: 'transparent',
              color: '#A16207', border: 'none', cursor: 'pointer',
            }}
          >
            取消
          </button>
        )}
      </div>
    </div>
  );
}

function MemoryConfirmPanel({ proposals, onResume }: {
  proposals: MemoryProposalItem[];
  onResume: Props['onResume'];
}) {
  const [decisions, setDecisions] = useState<Record<string, boolean>>({});

  const toggleDecision = (candidateId: string, accepted: boolean) => {
    setDecisions(prev => ({ ...prev, [candidateId]: accepted }));
  };

  const handleConfirm = () => {
    const decisionList = proposals.map(p => ({
      candidate_id: p.candidateId,
      accepted: decisions[p.candidateId] ?? false,
    }));
    onResume({ action: 'confirm_memory', decisions: decisionList });
  };

  const allDecided = proposals.every(p => decisions[p.candidateId] !== undefined);

  return (
    <div style={{
      background: colors.bgCard, borderRadius: 12, padding: 24,
      border: `1.5px solid ${colors.primary}`, boxShadow: shadows.elevated, marginBottom: 24,
    }}>
      {}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ fontSize: 28 }}>🧠</span>
        <div>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: colors.text }}>
            记忆候选确认
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: 13, color: colors.textSecondary }}>
            AI 从本次咨询中提取了以下记忆候选项，请确认是否保存到健康档案
          </p>
        </div>
      </div>

      {}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
        {proposals.map((p) => {
          const kind = KIND_LABELS[p.kind] || KIND_LABELS.basic;
          const decided = decisions[p.candidateId] !== undefined;
          const accepted = decisions[p.candidateId] === true;

          return (
            <div
              key={p.candidateId}
              style={{
                padding: '14px 18px', borderRadius: 10,
                border: `1px solid ${decided ? (accepted ? '#059669' : '#E5E7EB') : colors.border}`,
                background: decided ? (accepted ? '#F0FDF4' : '#F9FAFB') : colors.bgCard,
                opacity: decided && !accepted ? 0.5 : 1,
                transition: 'all 0.2s',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 4 }}>
                    <span style={{
                      padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                      background: kind.bg, color: kind.color,
                    }}>
                      {kind.label}
                    </span>
                    <span style={{ fontWeight: 700, fontSize: 15, color: colors.text }}>
                      {p.label}
                    </span>
                    <span style={{
                      fontSize: 11, color: colors.textSecondary,
                      background: colors.bg, padding: '1px 6px', borderRadius: 4,
                    }}>
                      {Math.round(p.confidence * 100)}% 置信
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: colors.textSecondary, lineHeight: 1.5 }}>
                    {p.detail}
                  </p>
                </div>

                {}
                <div style={{ display: 'flex', gap: 6, flexShrink: 0, marginLeft: 16 }}>
                  <button
                    onClick={() => toggleDecision(p.candidateId, true)}
                    style={{
                      padding: '6px 14px', fontSize: 12, fontWeight: 600, borderRadius: 6,
                      border: accepted ? 'none' : `1.5px solid #059669`,
                      background: accepted ? '#059669' : 'transparent',
                      color: accepted ? '#fff' : '#059669',
                      cursor: 'pointer', transition: 'all 0.15s',
                    }}
                  >
                    {accepted ? '✓ 已确认' : '确认'}
                  </button>
                  <button
                    onClick={() => toggleDecision(p.candidateId, false)}
                    style={{
                      padding: '6px 14px', fontSize: 12, fontWeight: 600, borderRadius: 6,
                      border: !accepted && decided ? `1.5px solid #DC2626` : `1px solid ${colors.border}`,
                      background: !accepted && decided ? '#FEF2F2' : 'transparent',
                      color: !accepted && decided ? '#DC2626' : colors.textSecondary,
                      cursor: 'pointer', transition: 'all 0.15s',
                    }}
                  >
                    {!accepted && decided ? '✗ 已拒绝' : '拒绝'}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={handleConfirm}
          disabled={!allDecided}
          style={{
            padding: '10px 28px', fontSize: 14, fontWeight: 700, borderRadius: 8,
            border: 'none', cursor: allDecided ? 'pointer' : 'not-allowed',
            background: allDecided ? colors.primary : '#E2E8F0',
            color: allDecided ? '#fff' : '#94A3B8',
            transition: 'all 0.2s',
          }}
        >
          提交确认 ({proposals.filter(p => decisions[p.candidateId] !== undefined).length}/{proposals.length})
        </button>
      </div>
    </div>
  );
}

function PublishConfirmPanel({ publishSummary, onResume }: {
  publishSummary: PublishSummary;
  onResume: Props['onResume'];
}) {
  return (
    <div style={{
      background: colors.bgCard, borderRadius: 12, padding: 24,
      border: `1.5px solid #059669`, boxShadow: shadows.elevated, marginBottom: 24,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span style={{ fontSize: 28 }}>✅</span>
        <div>
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: colors.text }}>
            报告生成完成
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: 13, color: colors.textSecondary }}>
            版本: {publishSummary.reportVersion}
          </p>
        </div>
      </div>

      {}
      <div style={{
        display: 'flex', gap: 16, marginBottom: 20,
        padding: '12px 16px', background: colors.bg, borderRadius: 8,
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: colors.primary }}>
            {publishSummary.abnormalMetricCount}
          </div>
          <div style={{ fontSize: 11, color: colors.textSecondary }}>项异常指标</div>
        </div>
        <div style={{ width: 1, background: colors.border }} />
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#059669' }}>
            {publishSummary.evidenceCount}
          </div>
          <div style={{ fontSize: 11, color: colors.textSecondary }}>条证据</div>
        </div>
        <div style={{ width: 1, background: colors.border }} />
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#D97706' }}>
            {publishSummary.sections.length}
          </div>
          <div style={{ fontSize: 11, color: colors.textSecondary }}>个章节</div>
        </div>
      </div>

      {}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <button
          onClick={() => onResume({ action: 'cancel_publish' })}
          style={{
            padding: '10px 20px', fontSize: 14, fontWeight: 600, borderRadius: 8,
            background: colors.bgCard, color: colors.textSecondary,
            border: `1px solid ${colors.border}`, cursor: 'pointer',
          }}
        >
          取消
        </button>
        <button
          onClick={() => onResume({ action: 'confirm_publish' })}
          style={{
            padding: '10px 28px', fontSize: 14, fontWeight: 700, borderRadius: 8,
            background: '#059669', color: '#fff', border: 'none', cursor: 'pointer',
            boxShadow: '0 2px 8px rgba(5,150,105,0.3)',
          }}
        >
          确认发布
        </button>
      </div>
    </div>
  );
}

export default function HITLResume({
  action, taskId, missingInfo, proposals, publishSummary, onResume, onCancel,
}: Props) {
  if (action === 'awaiting_images' && missingInfo) {
    return (
      <MissingImagesPrompt
        missingInfo={missingInfo}
        taskId={taskId}
        onResume={onResume}
        onCancel={onCancel}
      />
    );
  }

  if (action === 'awaiting_memory_confirm' && proposals && proposals.length > 0) {
    return (
      <MemoryConfirmPanel
        proposals={proposals}
        onResume={onResume}
      />
    );
  }

  if (action === 'awaiting_publish_confirm' && publishSummary) {
    return (
      <PublishConfirmPanel
        publishSummary={publishSummary}
        onResume={onResume}
      />
    );
  }

  return null;
}
