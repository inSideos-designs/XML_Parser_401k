import React, { useState, useCallback } from 'react';
import type { OptionsByPrompt } from '../types';

type Props = {
  onLoaded: (map: OptionsByPrompt) => void;
  disabled?: boolean;
};

function parseCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = '';
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQ && line[i + 1] === '"') {
        cur += '"'; i++;
      } else { inQ = !inQ; }
    } else if (ch === ',' && !inQ) {
      out.push(cur); cur = '';
    } else { cur += ch; }
  }
  out.push(cur);
  return out;
}

export const DataPointsUpload: React.FC<Props> = ({ onLoaded, disabled }) => {
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback((file: File | null) => {
    if (!file) return;
    if (!file.name.endsWith('.csv')) {
      setError('Please upload the Data Points sheet exported as CSV.');
      setFileName(null);
      onLoaded({});
      return;
    }
    setError(null);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = (reader.result as string) || '';
        const lines = text.split(/\r?\n/).filter(Boolean);
        if (lines.length < 2) throw new Error('CSV missing rows');
        const header = parseCsvLine(lines[0]).map(h => h.trim());
        const iPrompt = header.findIndex(h => h.toLowerCase() === 'prompt' || h.toUpperCase() === 'PROMPT');
        const iOptions = header.findIndex(h => h.toLowerCase() === 'options allowed');
        if (iPrompt < 0 || iOptions < 0) throw new Error('CSV must have PROMPT and Options Allowed columns');
        const map: OptionsByPrompt = {};
        for (let i = 1; i < lines.length; i++) {
          const cols = parseCsvLine(lines[i]);
          const p = (cols[iPrompt] || '').trim().replace(/^"|"$/g, '');
          const oa = (cols[iOptions] || '').trim();
          if (!p) continue;
          map[p] = oa;
        }
        setFileName(file.name);
        onLoaded(map);
      } catch (e) {
        console.error(e);
        setError('Failed to parse Data Points CSV.');
        setFileName(null);
        onLoaded({});
      }
    };
    reader.onerror = () => {
      setError('Error reading file.');
      setFileName(null);
      onLoaded({});
    };
    reader.readAsText(file);
  }, [onLoaded]);

  return (
    <div className="mt-4">
      <label className={`relative flex items-center justify-between w-full max-w-2xl px-4 py-3 border-2 border-dashed rounded-lg bg-slate-50 ${disabled ? 'opacity-50' : 'hover:bg-slate-100'}`}>
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-indigo-600">Data Points (Plan Express) CSV</span>
          <span className="text-xs text-slate-500">Export the sheet as CSV with PROMPT and Options Allowed</span>
        </div>
        <input type="file" className="hidden" accept=".csv,text/csv" disabled={disabled}
          onChange={(e) => handleFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
        <span className="text-xs text-slate-600">{fileName ?? 'Choose file'}</span>
      </label>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
};

