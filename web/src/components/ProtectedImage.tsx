import { useEffect, useState, type CSSProperties } from 'react';
import { apiFetch } from '../api/auth';

// img tags cannot attach a Bearer header. Fetch privately and release the Blob
// URL whenever the file changes or the preview is removed.
export default function ProtectedImage({ imageKey, style }: { imageKey: string; style?: CSSProperties }) {
  const [preview, setPreview] = useState<{ key: string; url: string } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    let objectURL = '';
    void (async () => {
      try {
        const response = await apiFetch(`/uploads/${encodeURIComponent(imageKey)}`, {
          signal: controller.signal, cache: 'no-store',
        });
        if (!response.ok) return;
        const blob = await response.blob();
        if (controller.signal.aborted) return;
        objectURL = URL.createObjectURL(blob);
        setPreview({ key: imageKey, url: objectURL });
      } catch {
        // An unavailable or unauthorized image has no preview.
      }
    })();
    return () => {
      controller.abort();
      if (objectURL) URL.revokeObjectURL(objectURL);
    };
  }, [imageKey]);
  return preview?.key === imageKey
    ? <img src={preview.url} alt="" style={style} />
    : <span role="img" aria-label="图片预览不可用" style={style}>图片预览不可用</span>;
}
