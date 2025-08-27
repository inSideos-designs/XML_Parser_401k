import React from 'react';
import type { ResultRow } from '../types';
import { DownloadIcon } from './Icons';

interface DownloadButtonProps {
  results: ResultRow[];
  fileNames: string[];
}

export const DownloadButton: React.FC<DownloadButtonProps> = ({ results, fileNames }) => {
  const downloadCSV = () => {
    const escapeCsvCell = (cell: string) => {
      if (cell.includes(',') || cell.includes('"') || cell.includes('\n')) {
        return `"${cell.replace(/"/g, '""')}"`;
      }
      return cell;
    };

    const headers = ['Prompt', ...fileNames];
    const csvRows = [headers.map(escapeCsvCell).join(',')];

    results.forEach(row => {
      const rowData = [row.promptText];
      fileNames.forEach(fileName => {
        rowData.push(row.values[fileName] || '');
      });
      csvRows.push(rowData.map(escapeCsvCell).join(','));
    });

    const csvString = csvRows.join('\n');
    const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    if (link.download !== undefined) {
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', 'xml_extraction_results.csv');
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  };

  return (
    <button
      onClick={downloadCSV}
      className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
    >
      <DownloadIcon className="-ml-1 mr-2 h-5 w-5" />
      Download CSV
    </button>
  );
};
