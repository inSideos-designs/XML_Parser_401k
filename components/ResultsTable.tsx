import React from 'react';
import type { ResultRow } from '../types';

interface ResultsTableProps {
  results: ResultRow[];
  fileNames: string[];
}

export const ResultsTable: React.FC<ResultsTableProps> = ({ results, fileNames }) => {
  return (
    <div className="overflow-x-auto border border-slate-200 rounded-lg">
      <table className="min-w-full divide-y divide-slate-200">
        <thead className="bg-slate-100">
          <tr>
            <th scope="col" className="sticky left-0 bg-slate-100 px-6 py-3 text-left text-xs font-medium text-slate-600 uppercase tracking-wider z-10">
              Prompt
            </th>
            {fileNames.map(fileName => (
              <th key={fileName} scope="col" className="px-6 py-3 text-left text-xs font-medium text-slate-600 uppercase tracking-wider">
                {fileName}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-slate-200">
          {results.map((row) => (
            <tr key={row.promptKey} className="hover:bg-slate-50">
              <td className="sticky left-0 bg-white hover:bg-slate-50 px-6 py-4 whitespace-nowrap text-sm font-medium text-slate-900 z-10">
                {row.promptText}
              </td>
              {fileNames.map(fileName => (
                <td key={`${row.promptKey}-${fileName}`} className="px-6 py-4 whitespace-normal text-sm text-slate-600">
                  {row.values[fileName]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
