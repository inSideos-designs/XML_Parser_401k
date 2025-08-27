import React, { useCallback, useState } from 'react';
import type { Prompt } from '../types';
import { UploadIcon, FileCsvIcon } from './Icons';

interface PromptUploadProps {
  onPromptsChange: (prompts: Prompt[]) => void;
  disabled: boolean;
}

// Helper to parse a single CSV line, handling quoted fields.
const parseCsvLine = (line: string): string[] => {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
        const char = line[i];
        if (char === '"') {
            if (inQuotes && line[i + 1] === '"') {
                // Escaped quote
                current += '"';
                i++;
            } else {
                inQuotes = !inQuotes;
            }
        } else if (char === ',' && !inQuotes) {
            result.push(current.trim());
            current = '';
        } else {
            current += char;
        }
    }
    result.push(current.trim());
    return result;
};

const parseCsv = (csvText: string): { prompts: Prompt[], error: string | null } => {
    const lines = csvText.trim().split(/\r?\n/);
    if (lines.length < 2) {
        return { prompts: [], error: 'CSV file must have a header and at least one data row.' };
    }

    const header = parseCsvLine(lines[0]).map(h => h.trim().toLowerCase().replace(/^"|"$/g, ''));
    const promptIndex = header.indexOf('prompt');
    const keyIndex = header.indexOf('proposed linkname');
    const quickIndex = header.indexOf('quick text data point');

    if (promptIndex === -1) {
        return { prompts: [], error: "CSV header must contain a 'Prompt' column." };
    }
    if (keyIndex === -1) {
        return { prompts: [], error: "CSV header must contain a 'Proposed LinkName' column." };
    }

    const prompts: Prompt[] = [];
    const keyCounts = new Map<string, number>();

    for (let i = 1; i < lines.length; i++) {
        const line = lines[i].trim();
        if (!line) continue;
        
        const values = parseCsvLine(lines[i]);
        const promptText = values[promptIndex]?.replace(/^"|"$/g, '') || '';
        const rawLinknames = values[keyIndex]?.replace(/^"|"$/g, '') || '';
        const quick = (quickIndex >= 0 ? values[quickIndex] : '')?.replace(/^"|"$/g, '') || '';
        let baseKey = rawLinknames;

        if (!promptText) {
          continue; // Skip rows with no prompt text
        }

        if (!baseKey) {
            // If linkname is empty, create a unique key based on row number
            baseKey = `prompt_row_${i}`;
        }
        
        // Sanitize baseKey to be a valid JSON property name.
        baseKey = baseKey.replace(/[^a-zA-Z0-9_]/g, '_');
        if (/^[0-9]/.test(baseKey)) {
            baseKey = '_' + baseKey;
        }
        
        // Ensure the key is unique by appending a counter if it's a duplicate
        const count = keyCounts.get(baseKey) || 0;
        const finalKey = count > 0 ? `${baseKey}_${count + 1}` : baseKey;
        keyCounts.set(baseKey, count + 1);

        prompts.push({ key: finalKey, prompt: promptText, linknames: rawLinknames, quick });
    }
    
    return { prompts, error: null };
};


export const PromptUpload: React.FC<PromptUploadProps> = ({ onPromptsChange, disabled }) => {
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(async (file: File | null) => {
    if (!file) return;

    if (!file.name.endsWith('.csv')) {
      setError('Please upload a valid CSV file.');
      setFileName(null);
      onPromptsChange([]);
      return;
    }

    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      if (content) {
        try {
          const { prompts: parsedPrompts, error: parseError } = parseCsv(content);
          if (parseError) {
            setError(parseError);
            setFileName(null);
            onPromptsChange([]);
          } else if (parsedPrompts.length === 0) {
            setError('CSV file does not contain any valid prompt rows.');
            setFileName(null);
            onPromptsChange([]);
          } else {
            setFileName(file.name);
            onPromptsChange(parsedPrompts);
          }
        } catch (err) {
          console.error("Error parsing CSV:", err);
          setError('Failed to parse CSV file.');
          setFileName(null);
          onPromptsChange([]);
        }
      } else {
        setError(`Could not read file: ${file.name}`);
        setFileName(null);
        onPromptsChange([]);
      }
    };
    reader.onerror = () => {
      setError(`Error reading file: ${file.name}`);
      setFileName(null);
      onPromptsChange([]);
    };
    reader.readAsText(file);
  }, [onPromptsChange]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  return (
    <div className="mt-4">
      <label
        htmlFor="prompt-file-upload"
        className={`relative flex items-center justify-center w-full max-w-md px-4 py-3 border-2 border-dashed rounded-lg cursor-pointer bg-slate-50 transition-colors ${
          disabled ? 'cursor-not-allowed bg-slate-200' : 'hover:bg-slate-100'
        } ${error ? 'border-red-500' : 'border-slate-300'}`}
      >
        <UploadIcon className="w-6 h-6 mr-3 text-slate-400" />
        <span className="text-sm text-slate-500">
          <span className="font-semibold text-indigo-600">Upload prompt map</span> (CSV file)
        </span>
        <input
          id="prompt-file-upload"
          type="file"
          className="hidden"
          accept=".csv,text/csv"
          onChange={handleChange}
          disabled={disabled}
        />
      </label>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

      {fileName && !error && (
        <div className="mt-4">
          <div className="flex items-center bg-slate-100 text-slate-800 text-sm font-medium p-2 rounded-md max-w-md">
            <FileCsvIcon className="w-5 h-5 mr-2 text-emerald-500 flex-shrink-0" />
            <span className="truncate">{fileName}</span>
          </div>
        </div>
      )}
    </div>
  );
};
