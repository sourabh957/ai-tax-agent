'use client';

import { useApp } from '@/hooks/use-app';
import { apiClient, ApiError } from '@/lib/api/client';
import { cn, formatFileSize } from '@/lib/utils';
import { FileText, Upload, X } from 'lucide-react';
import { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { Button } from '@/components/ui/button';
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
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<UploadState>('idle');
  const [error, setError] = useState('');
  const [result, setResult] = useState<Document | null>(null);

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
      <div className="absolute inset-0 bg-black/30 backdrop-blur-sm" onClick={handleClose} />
      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-xl border border-slate-200">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-100">
          <div>
            <h2 className="font-semibold text-slate-900">Upload tax document</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              {selectedYear?.label} • Form 16, AIS, broker statements
            </p>
          </div>
          <button
            onClick={handleClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4">
          {state === 'success' && result ? (
            <div className="text-center py-6">
              <div className="w-12 h-12 bg-emerald-50 rounded-full flex items-center justify-center mx-auto mb-3">
                <FileText size={22} className="text-emerald-600" />
              </div>
              <p className="font-medium text-slate-900">{result.filename}</p>
              <p className="text-sm text-emerald-600 mt-1">Uploaded successfully</p>
              <p className="text-xs text-slate-400 mt-1">
                {result.extracted_chars > 0
                  ? `${result.extracted_chars.toLocaleString()} characters extracted`
                  : 'Processing...'}
              </p>
              <Button className="mt-5" onClick={handleClose}>
                Done
              </Button>
            </div>
          ) : (
            <>
              {/* Dropzone */}
              <div
                {...getRootProps()}
                className={cn(
                  'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors',
                  isDragActive
                    ? 'border-slate-400 bg-slate-50'
                    : file
                    ? 'border-slate-300 bg-slate-50'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                )}
              >
                <input {...getInputProps()} />
                {file ? (
                  <div className="flex items-center justify-center gap-3">
                    <FileText size={20} className="text-slate-500" />
                    <div className="text-left">
                      <p className="text-sm font-medium text-slate-700">{file.name}</p>
                      <p className="text-xs text-slate-400">{formatFileSize(file.size)}</p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                        setState('idle');
                      }}
                      className="ml-2 text-slate-400 hover:text-slate-600"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <>
                    <Upload size={24} className="mx-auto text-slate-300 mb-3" />
                    <p className="text-sm font-medium text-slate-700">
                      {isDragActive ? 'Drop your file here' : 'Drag & drop or click to browse'}
                    </p>
                    <p className="text-xs text-slate-400 mt-1">PDF, JPG, PNG, CSV · Max 20MB</p>
                  </>
                )}
              </div>

              {error && (
                <p className="text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
              )}

              {/* Actions */}
              <div className="flex gap-2 pt-1">
                <Button variant="outline" className="flex-1" onClick={handleClose}>
                  Cancel
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleUpload}
                  disabled={!file || state === 'uploading'}
                >
                  {state === 'uploading' ? (
                    <span className="flex items-center gap-2">
                      <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      Uploading...
                    </span>
                  ) : (
                    'Upload'
                  )}
                </Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
