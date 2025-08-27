import React from 'react';

type Props = {
  mapFile: File | null;
  setMapFile: (f: File | null) => void;
  datapointsFile: File | null;
  setDatapointsFile: (f: File | null) => void;
  disabled?: boolean;
};

export const AdvancedUploads: React.FC<Props> = ({ mapFile, setMapFile, datapointsFile, setDatapointsFile, disabled }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <label className={`flex items-center justify-between px-4 py-3 border-2 border-dashed rounded-lg bg-slate-50 ${disabled ? 'opacity-60' : 'hover:bg-slate-100'}`}>
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-indigo-600">Map Workbook</span>
          <span className="text-xs text-slate-500">XLSX or CSV</span>
        </div>
        <input type="file" className="hidden" accept=".xlsx,.csv,text/csv" disabled={disabled}
          onChange={(e) => setMapFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
        <span className="text-xs text-slate-600">{mapFile ? mapFile.name : 'Choose file'}</span>
      </label>
      <label className={`flex items-center justify-between px-4 py-3 border-2 border-dashed rounded-lg bg-slate-50 ${disabled ? 'opacity-60' : 'hover:bg-slate-100'}`}>
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-indigo-600">Data Points Workbook</span>
          <span className="text-xs text-slate-500">XLSX (sheet: Plan Express Data Points)</span>
        </div>
        <input type="file" className="hidden" accept=".xlsx" disabled={disabled}
          onChange={(e) => setDatapointsFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)} />
        <span className="text-xs text-slate-600">{datapointsFile ? datapointsFile.name : 'Choose file'}</span>
      </label>
    </div>
  );
};

