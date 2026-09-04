'use client';

import { useApp } from '@/hooks/use-app';
import { useAuth } from '@/hooks/use-auth';
import { apiClient, ApiError } from '@/lib/api/client';
import { cn, formatFileSize } from '@/lib/utils';
import { FileText, Upload, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import type { Document } from '@/types';

interface UploadDocumentModalProps {
  open: boolean;
  onClose: () => void;
}

type UploadState = 'idle' | 'uploading' | 'success' | 'error';

const ACCEPTED_TYPES = {
  'application/pdf': ['.pdf'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/tiff': ['.tiff', '.tif'],
  'text/plain': ['.txt'],
  'text/csv': ['.csv'],
};

export function UploadDocumentModal({ open, onClose }: UploadDocumentModalProps) {
  const { selectedYear, addDocument } = useApp();
  const { token } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>('idle');
  const [error, setError] = useState('');
  const [result, setResult] = useState<Document | null>(null);

  // Sync token to api client when it changes
  useEffect(() => {
    apiClient.setToken(token);
  }, [token]);

  const onDrop = useCallback((accepted: File[], rejected: import('react-dropzone').FileRejection[]) => {
    if (rejected.length > 0) {
      setError(rejected[0].errors[0]?.message || 'Invalid file');
      return;
    }
    if (accepted[0]) {
      setFile(accepted[0]);
      setError('');
      setState('idle');
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: 20 * 1024 * 1024,
    maxFiles: 1,
  });

  async function handleUpload() {
    if (!file || !selectedYear) return;
    setState('uploading');
    setError('');
    try {
      const doc = await apiClient.uploadDocument(file, selectedYear.id);
      setResult(doc);
      addDocument(doc);
      setState('success');
    } catch (err) {
      setState('error');
      setError(err instanceof ApiError ? err.detail : 'Upload failed. Please try again.');
    }
  }

  function handleClose() {
    setFile(null);
    setState('idle');
    setError('');
    setResult(null);
    onClose();
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0"
        style={{ background: 'rgba(0,0,0,0.7)' }}
        onClick={handleClose}
      />
      <div
        className="relative w-full max-w-md rounded-2xl shadow-2xl"
        style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between p-5"
          style={{ borderBottom: '1px solid var(--border)' }}
        >
          <div>
            <h2 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
              Upload tax document
            </h2>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {selectedYear?.label} · Form 16, AIS, broker statements
            </p>
          </div>
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg transition-colors"
            style={{ color: 'var(--text-secondary)' }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          {state === 'success' && result ? (
            <div className="text-center py-6">
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center mx-auto mb-3"
                style={{ background: 'rgba(52,211,153,0.15)' }}
              >
                <FileText size={22} style={{ color: 'var(--success)' }} />
              </div>
              <p className="font-medium" style={{ color: 'var(--text-primary)' }}>{result.filename}</p>
              <p className="text-sm mt-1" style={{ color: 'var(--success)' }}>Uploaded successfully</p>
              {result.extracted_chars > 0 && (
                <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                  {result.extracted_chars.toLocaleString()} characters extracted
                </p>
              )}
              <button
                className="mt-5 px-6 py-2 rounded-xl text-sm font-medium text-white"
                style={{ background: 'var(--accent)' }}
                onClick={handleClose}
              >
                Done
              </button>
            </div>
          ) : (
            <>
              <div
                {...getRootProps()}
                className="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors"
                style={{
                  borderColor: isDragActive ? 'var(--accent)' : file ? 'var(--border-strong)' : 'var(--border)',
                  background: isDragActive ? 'var(--bg-hover)' : file ? 'var(--bg-surface)' : 'transparent',
                }}
              >
                <input {...getInputProps()} />
                {file ? (
                  <div className="flex items-center justify-center gap-3">
                    <FileText size={20} style={{ color: 'var(--text-secondary)' }} />
                    <div className="text-left">
                      <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{file.name}</p>
                      <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{formatFileSize(file.size)}</p>
                    </div>
                    <button
                      onClick={e => { e.stopPropagation(); setFile(null); setState('idle'); }}
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <>
                    <Upload size={24} className="mx-auto mb-3" style={{ color: 'var(--text-placeholder)' }} />
                    <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
                      {isDragActive ? 'Drop your file here' : 'Drag & drop or click to browse'}
                    </p>
                    <p className="text-xs mt-1" style={{ color: 'var(--text-placeholder)' }}>
                      PDF, JPG, PNG, CSV · Max 20MB
                    </p>
                  </>
                )}
              </div>

              {error && (
                <p
                  className="text-xs rounded-lg px-3 py-2"
                  style={{ background: 'rgba(248,113,113,0.1)', color: 'var(--error)', border: '1px solid rgba(248,113,113,0.2)' }}
                >
                  {error}
                </p>
              )}

              <div className="flex gap-2 pt-1">
                <button
                  onClick={handleClose}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-colors"
                  style={{ border: '1px solid var(--border)', color: 'var(--text-secondary)', background: 'transparent' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  Cancel
                </button>
                <button
                  onClick={handleUpload}
                  disabled={!file || state === 'uploading'}
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold text-white flex items-center justify-center gap-2"
                  style={{ background: 'var(--accent)', opacity: (!file || state === 'uploading') ? 0.5 : 1 }}
                >
                  {state === 'uploading' ? (
                    <>
                      <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      Uploading...
                    </>
                  ) : 'Upload'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
