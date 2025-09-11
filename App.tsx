import React, { useState, useCallback } from 'react';
import { Header } from './components/Header';
import { FileUpload } from './components/FileUpload';
import { PromptUpload } from './components/PromptUpload';
import { ResultsTable } from './components/ResultsTable';
import { DownloadButton } from './components/DownloadButton';
import { fillDataFromXmls, fillDataFromXmlsEnhanced } from './services/xmlExtractionService';
// Backend Advanced mode removed
import { DataPointsUpload } from './components/DataPointsUpload';
import type { XmlFile, Prompt, ResultRow, OptionsByPrompt } from './types';
import { LoaderIcon, ProcessIcon } from './components/Icons';

const App: React.FC = () => {
  const [xmlFiles, setXmlFiles] = useState<XmlFile[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [results, setResults] = useState<ResultRow[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [processingProgress, setProcessingProgress] = useState(0);
  const [optionsByPrompt, setOptionsByPrompt] = useState<OptionsByPrompt>({});
  const [useLocalDirMaps, setUseLocalDirMaps] = useState(true);

  const handleFilesChange = useCallback((files: XmlFile[]) => {
    setXmlFiles(files);
    // Reset subsequent steps
    setPrompts([]);
    setResults([]);
    setError(null);
  }, []);

  const handlePromptsChange = useCallback((newPrompts: Prompt[]) => {
    setPrompts(newPrompts);
    setResults([]);
    setError(null);
  }, []);

  // Auto-load maps from local directory via Vite dev server middleware
  React.useEffect(() => {
    async function loadLocal() {
      try {
        // Fetch map first; enable Step 3 even if options fail
        const mapResp = await fetch('/local-map');
        if (!mapResp.ok) throw new Error(await mapResp.text());
        const mapData = await mapResp.json();
        // Build prompts with unique keys like PromptUpload does
        const keyCounts = new Map<string, number>();
        const built: Prompt[] = (mapData as any[]).map((e: any, idx: number) => {
          const promptText = String(e.prompt || '');
          let baseKey = String(e.linknames || '').trim() || `prompt_row_${idx+1}`;
          baseKey = baseKey.replace(/[^a-zA-Z0-9_]/g, '_');
          if (/^[0-9]/.test(baseKey)) baseKey = '_' + baseKey;
          const c = keyCounts.get(baseKey) || 0;
          const finalKey = c > 0 ? `${baseKey}_${c+1}` : baseKey;
          keyCounts.set(baseKey, c + 1);
          return { key: finalKey, prompt: promptText, linknames: String(e.linknames || ''), quick: String(e.quick || '') } as Prompt;
        });
        setPrompts(built);
        // Try to fetch options; if it fails, proceed without
        try {
          const optResp = await fetch('/local-options');
          if (optResp.ok) {
            const options = await optResp.json();
            setOptionsByPrompt(options as OptionsByPrompt);
          } else {
            console.warn('local-options unavailable:', await optResp.text());
            setOptionsByPrompt({});
          }
        } catch (e) {
          console.warn('Failed to load local options', e);
          setOptionsByPrompt({});
        }
      } catch (err) {
        console.error('Failed to auto-load local directory maps', err);
        setError('Could not auto-load map/options from local config. You can upload CSVs instead.');
      }
    }
    if (useLocalDirMaps) {
      loadLocal();
    }
  }, [useLocalDirMaps]);

  

  const handleProcessFiles = async () => {
    if (xmlFiles.length === 0) {
      setError('Please upload XML files before processing.');
      return;
    }
    setIsLoading(true);
    setError(null);
    setProcessingProgress(0);

    try {
      if (useLocalDirMaps) {
        // Use full Python logic via local Vite middleware for parity
        const payload = { xmlFiles: xmlFiles.map(f => ({ name: f.name, content: f.content })) };
        const resp = await fetch('/process-local', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        if (!resp.ok) {
          const text = await resp.text();
          throw new Error(text || `process-local failed with status ${resp.status}`);
        }
        const backend = await resp.json();
        const resultRows: ResultRow[] = backend.rows.map((r: any) => ({
          promptKey: r.promptText,
          promptText: r.promptText,
          values: r.values,
        }));
        setResults(resultRows);
      } else {
        const hasOptions = optionsByPrompt && Object.keys(optionsByPrompt).length > 0;
        const filledData = hasOptions
          ? await fillDataFromXmlsEnhanced(prompts, xmlFiles, optionsByPrompt, (progress) => setProcessingProgress(progress))
          : await fillDataFromXmls(prompts, xmlFiles, (progress) => setProcessingProgress(progress));
        const resultRows: ResultRow[] = prompts.map(prompt => ({
          promptKey: prompt.key,
          promptText: prompt.prompt,
          values: xmlFiles.reduce((acc, file) => {
            acc[file.name] = filledData[file.name]?.[prompt.key] || 'N/A';
            return acc;
          }, {} as { [fileName: string]: string }),
        }));
        setResults(resultRows);
      }
    } catch (e: any) {
      console.error(e);
      const msg = (e && (e.message || typeof e === 'string' ? String(e) : '')) || '';
      setError(msg || 'An error occurred during processing. Some files may not have been processed correctly. Please review the results.');
    } finally {
      setIsLoading(false);
    }
  };

  const isStep1Complete = xmlFiles.length > 0;
  const isStep2Complete = xmlFiles.length > 0;

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-800">
      <Header />
      <main className="container mx-auto p-4 md:p-8">
        <div className="space-y-8">
          
          <div className="bg-white p-6 rounded-2xl shadow-lg border border-slate-200">
            <h2 className="text-xl font-bold text-slate-700 mb-4">Step 1: Upload XML Files</h2>
            <FileUpload onFilesChange={handleFilesChange} />
          </div>

          {isStep1Complete && (
            <div className="bg-white p-6 rounded-2xl shadow-lg border border-slate-200">
              <h2 className="text-xl font-bold text-slate-700 mb-4">Step 2: Prompt Mapping</h2>
              <div className="mb-3">
                <label className="inline-flex items-center space-x-2">
                  <input type="checkbox" className="h-4 w-4" checked={useLocalDirMaps} onChange={(e) => setUseLocalDirMaps(e.target.checked)} />
                  <span className="text-sm text-slate-700">Auto-load local config (no uploads)</span>
                </label>
              </div>
              {!useLocalDirMaps && (
                <>
                  <div className="prose prose-sm prose-slate max-w-none">
                    <p>Upload your prompt map file. Please <strong>save your Excel map file as a CSV</strong> first.</p>
                    <p>The CSV must contain a header row with columns named <strong>`Prompt`</strong> and <strong>`Proposed LinkName`</strong>.</p>
                  </div>
                  <PromptUpload onPromptsChange={handlePromptsChange} disabled={isLoading} />
                  <div className="mt-4">
                    <DataPointsUpload onLoaded={setOptionsByPrompt} disabled={isLoading} />
                    <p className="text-xs text-slate-500 mt-1">Optional but recommended for better matching. Export the Plan Express sheet as CSV.</p>
                  </div>
                </>
              )}
              <div className="mt-4">
                <DataPointsUpload onLoaded={setOptionsByPrompt} disabled={isLoading} />
                <p className="text-xs text-slate-500 mt-1">Optional but recommended for better matching. Export the Plan Express sheet as CSV.</p>
              </div>
              {/* Advanced backend mode removed for local-only workflow */}
            </div>
          )}

          {isStep2Complete && (
            <div className="bg-white p-6 rounded-2xl shadow-lg border border-slate-200">
              <h2 className="text-xl font-bold text-slate-700 mb-4">Step 3: Process Files</h2>
              <p className="text-slate-600 mb-4">Everything is ready. Process the uploaded XML files using your custom prompts.</p>
               <div className="flex items-center space-x-4">
                 <button
                   onClick={handleProcessFiles}
                   disabled={isLoading}
                   className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md shadow-sm text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 disabled:bg-emerald-300 disabled:cursor-not-allowed transition-colors"
                 >
                   {isLoading ? (
                     <>
                       <LoaderIcon className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" />
                       Processing...
                     </>
                   ) : (
                     <>
                       <ProcessIcon className="-ml-1 mr-2 h-5 w-5" />
                       Process {xmlFiles.length} Files
                     </>
                   )}
                 </button>
                 {isLoading && (
                   <div className="w-full bg-gray-200 rounded-full h-2.5">
                     <div className="bg-emerald-600 h-2.5 rounded-full" style={{ width: `${processingProgress * 100}%` }}></div>
                   </div>
                 )}
               </div>
            </div>
          )}

          {error && (
            <div className="bg-red-100 border-l-4 border-red-500 text-red-700 p-4 rounded-md" role="alert">
              <p className="font-bold">Error</p>
              <p>{error}</p>
            </div>
          )}

          {results.length > 0 && !isLoading && (
            <div className="bg-white p-6 rounded-2xl shadow-lg border border-slate-200">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-2xl font-bold text-slate-800">Extracted Data</h2>
                <DownloadButton results={results} fileNames={xmlFiles.map(f => f.name)} />
              </div>
              <ResultsTable results={results} fileNames={xmlFiles.map(f => f.name)} />
            </div>
          )}

        </div>
      </main>
    </div>
  );
};

export default App;
