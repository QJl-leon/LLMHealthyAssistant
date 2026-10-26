
import { forwardRef, useImperativeHandle, useRef, useState, type DragEvent } from 'react';
import { colors, fonts } from './styles';
import { getToken, requireLogin } from '../api/auth';

export interface UploadAttachment {
  key: string;
  position: string;
  url?: string;
  name?: string;
  size?: number;
  type?: string;
}

interface UploadTask {
  id: string;
  name: string;
  size: number;
  type: string;
  progress: number;
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

interface DragUploadProps {
  variant: 'full' | 'compact';
  onUploaded: (attachments: UploadAttachment[]) => void;
  disabled?: boolean;
}

export interface DragUploadHandle {
  openPicker: () => void;
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const v = bytes / Math.pow(1024, i);
  return `${i === 0 ? v.toFixed(0) : v.toFixed(1)} ${units[i]}`;
}

function uploadFile(
  file: File,
  onProgress: (p: number) => void,
): { promise: Promise<UploadAttachment>; abort: () => void } {
  const xhr = new XMLHttpRequest();
  const fd = new FormData();
  fd.append('file', file);
  fd.append('position', 'exam_report');

  xhr.open('POST', '/api/v1/uploads');
  const token = getToken();
  if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);

  const promise = new Promise<UploadAttachment>((resolve, reject) => {
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const json = JSON.parse(xhr.responseText);
          if (json.code === 0) {
            resolve({
              key: json.data.image_key,
              position: json.data.position || 'exam_report',
              url: json.data.url,
              name: file.name,
              size: file.size,
              type: file.type,
            });
          } else {
            reject(new Error(json.error?.message || '上传失败'));
          }
        } catch {
          reject(new Error('服务器响应异常'));
        }
      } else if (xhr.status === 401) {
        requireLogin(token);
        reject(new Error('登录已失效，请重新登录后上传'));
      } else {
        reject(new Error(`上传失败（HTTP ${xhr.status}）`));
      }
    };
    xhr.onerror = () => reject(new Error('网络错误，请重试'));
    xhr.onabort = () => reject(new DOMException('已取消', 'AbortError'));
  });

  xhr.send(fd);

  return { promise, abort: () => xhr.abort() };
}

const DragUpload = forwardRef<DragUploadHandle, DragUploadProps>(function DragUpload(
  { variant, onUploaded, disabled },
  ref,
) {
  const [tasks, setTasks] = useState<UploadTask[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortMap = useRef<Map<string, () => void>>(new Map());
  const idSeq = useRef(0);
  const dragCounter = useRef(0);

  const openPicker = () => inputRef.current?.click();
  useImperativeHandle(ref, () => ({ openPicker }));

  const updateTask = (id: string, patch: Partial<UploadTask>) => {
    setTasks(prev => prev.map(t => (t.id === id ? { ...t, ...patch } : t)));
  };

  const removeTask = (id: string) => {
    setTasks(prev => prev.filter(t => t.id !== id));
  };

  const startUpload = (files: FileList | File[]) => {
    if (disabled) return;
    const list = Array.from(files);
    if (list.length === 0) return;
    if (!getToken()) {
      requireLogin();
      if (inputRef.current) inputRef.current.value = '';
      return;
    }

    // Allow selecting the same file again after logging in or retrying.
    if (inputRef.current) inputRef.current.value = '';

    for (const file of list) {
      const id = `up-${Date.now().toString(36)}-${idSeq.current++}`;
      setTasks(prev => [...prev, {
        id, name: file.name, size: file.size, type: file.type,
        progress: 0, status: 'uploading',
      }]);

      const { promise, abort } = uploadFile(file, (p) => updateTask(id, { progress: p }));
      abortMap.current.set(id, abort);

      promise
        .then((att) => {
          abortMap.current.delete(id);
          updateTask(id, { status: 'done', progress: 1 });
          onUploaded([att]);

          setTimeout(() => removeTask(id), 1800);
        })
        .catch((err: unknown) => {
          abortMap.current.delete(id);
          if (err instanceof DOMException && err.name === 'AbortError') {
            removeTask(id);
          } else {
            updateTask(id, {
              status: 'error',
              error: err instanceof Error ? err.message : '上传失败',
            });
          }
        });
    }
  };

  const onDragEnter = (e: DragEvent) => {
    e.preventDefault();
    dragCounter.current += 1;
    setDragging(true);
  };
  const onDragOver = (e: DragEvent) => { e.preventDefault(); };
  const onDragLeave = (e: DragEvent) => {
    e.preventDefault();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setDragging(false);
    }
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    dragCounter.current = 0;
    setDragging(false);
    if (!disabled && e.dataTransfer.files.length > 0) {
      startUpload(e.dataTransfer.files);
    }
  };

  const cancel = (id: string) => {
    const abort = abortMap.current.get(id);
    if (abort) abort();
  };

  const visibleTasks = tasks;

  if (variant === 'compact') {
    return (
      <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
        <input
          ref={inputRef}
          type="file"
          accept="image/*,application/pdf"
          multiple
          style={{ display: 'none' }}
          onChange={e => e.target.files && startUpload(e.target.files)}
        />
        <button
          type="button"
          onClick={openPicker}
          disabled={disabled}
          title="上传体检报告（也可拖拽到输入区）"
          style={{
            width: 34, height: 34, borderRadius: 8,
            border: `1px solid ${colors.border}`, background: colors.bg,
            cursor: disabled ? 'not-allowed' : 'pointer', fontSize: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          📎
        </button>
        {}
        {visibleTasks.length > 0 && (
          <div style={{
            position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, width: 320,
            display: 'flex', flexDirection: 'column', gap: 8, zIndex: 30,
          }}>
            {visibleTasks.map(t => <TaskRow key={t.id} task={t} onCancel={cancel} />)}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ fontFamily: fonts.sans }}>
      <input
        ref={inputRef}
        type="file"
        accept="image/*,application/pdf"
        multiple
        style={{ display: 'none' }}
        onChange={e => e.target.files && startUpload(e.target.files)}
      />

      {}
      <div
        onClick={() => !disabled && openPicker()}
        onDragEnter={onDragEnter}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        style={{
          padding: '36px 24px',
          borderRadius: 16,
          border: `2px dashed ${dragging ? colors.primary : colors.border}`,
          background: dragging ? colors.primaryLight : colors.bgCard,
          cursor: disabled ? 'not-allowed' : 'pointer',
          textAlign: 'center',
          transition: 'all 0.2s',
          boxShadow: dragging ? `0 0 0 4px rgba(37,99,235,0.12)` : 'none',
        }}
      >
        <div style={{ fontSize: 40, marginBottom: 12 }}>{dragging ? '📥' : '📄'}</div>
        <div style={{ fontSize: 15, fontWeight: 600, color: colors.text }}>
          {dragging ? '松开以添加文件' : '拖拽体检报告到这里'}
        </div>
        <div style={{ fontSize: 13, color: colors.textSecondary, marginTop: 6, lineHeight: 1.6 }}>
          或 <span style={{ color: colors.primary, fontWeight: 600 }}>点击选择文件</span>（备用方式）
        </div>
        <div style={{ fontSize: 12, color: '#94A3B8', marginTop: 8 }}>
          支持 JPG / PNG / WebP / GIF / PDF，可一次选择多份
        </div>
      </div>

      {}
      {visibleTasks.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
          {visibleTasks.map(t => <TaskRow key={t.id} task={t} onCancel={cancel} />)}
        </div>
      )}
    </div>
  );
});

function TaskRow({ task, onCancel }: { task: UploadTask; onCancel: (id: string) => void }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px', borderRadius: 10,
      background: colors.bgCard, border: `1px solid ${colors.border}`,
      fontSize: 13,
    }}>
      {}
      <span style={{ fontSize: 18, flexShrink: 0, width: 22, textAlign: 'center' }}>
        {task.status === 'uploading' ? '⏳' : task.status === 'done' ? '✅' : '❌'}
      </span>

      {}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontWeight: 600, color: colors.text, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {task.name}
        </div>
        <div style={{ fontSize: 11, color: colors.textSecondary, marginTop: 2 }}>
          {formatBytes(task.size)} · {task.type ? formatTypeLabel(task.type) : '文件'}
          {task.status === 'error' && task.error ? (
            <span style={{ color: colors.danger, marginLeft: 8 }}>{task.error}</span>
          ) : null}
        </div>
        {}
        {task.status === 'uploading' && (
          <div style={{
            marginTop: 6, height: 4, borderRadius: 2, background: colors.border, overflow: 'hidden',
          }}>
            <div style={{
              width: `${Math.round(task.progress * 100)}%`, height: '100%',
              background: 'linear-gradient(90deg, #14C8B8, #0E9F8F)',
              transition: 'width 0.15s',
            }} />
          </div>
        )}
      </div>

      {}
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
        {task.status === 'uploading' && (
          <>
            <span style={{ fontSize: 12, color: colors.textSecondary, minWidth: 38, textAlign: 'right' }}>
              {Math.round(task.progress * 100)}%
            </span>
            <button
              type="button"
              onClick={() => onCancel(task.id)}
              title="取消上传"
              style={{
                padding: '4px 10px', fontSize: 12, borderRadius: 6, cursor: 'pointer',
                border: `1px solid ${colors.border}`, background: '#fff', color: colors.danger,
              }}
            >
              取消
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function formatTypeLabel(mime: string): string {
  if (mime === 'application/pdf') return 'PDF';
  if (mime.startsWith('image/')) return mime.replace('image/', '').toUpperCase();
  return mime || '文件';
}

export default DragUpload;
