import React, { useCallback, useState } from 'react';
import type { XmlFile } from '../types';
import { UploadIcon, FileXmlIcon } from './Icons';

interface FileUploadProps {
  onFilesChange: (files: XmlFile[]) => void;
}

export const FileUpload: React.FC<FileUploadProps> = ({ onFilesChange }) => {
  const [dragActive, setDragActive] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<string[]>([]);

  const handleFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const xmlFilePromises: Promise<XmlFile>[] = Array.from(files)
      .filter(file => file.type === 'text/xml' || file.name.endsWith('.xml'))
      .map(file => {
        return new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            const content = e.target?.result as string;
            if (content) {
              resolve({ name: file.name, content });
            } else {
              reject(new Error(`Could not read file: ${file.name}`));
            }
          };
          reader.onerror = (e) => reject(e);
          reader.readAsText(file);
        });
      });
    
    try {
        const loadedFiles = await Promise.all(xmlFilePromises);
        setUploadedFiles(loadedFiles.map(f => f.name));
        onFilesChange(loadedFiles);
    } catch (error) {
        console.error("Error reading files:", error);
    }
  }, [onFilesChange]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
    }
  }, [handleFiles]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    handleFiles(e.target.files);
  };

  return (
    <div className="w-full">
      <label
        htmlFor="dropzone-file"
        className={`relative flex flex-col items-center justify-center w-full h-64 border-2 border-dashed rounded-lg cursor-pointer bg-slate-50 hover:bg-slate-100 transition-colors ${dragActive ? 'border-indigo-500' : 'border-slate-300'}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
      >
        <div className="flex flex-col items-center justify-center pt-5 pb-6">
          <UploadIcon className="w-10 h-10 mb-3 text-slate-400" />
          <p className="mb-2 text-sm text-slate-500">
            <span className="font-semibold">Click to upload</span> or drag and drop
          </p>
          <p className="text-xs text-slate-500">XML files only</p>
        </div>
        <input id="dropzone-file" type="file" className="hidden" multiple accept=".xml,text/xml" onChange={handleChange} />
      </label>
      {uploadedFiles.length > 0 && (
        <div className="mt-4">
          <h4 className="font-semibold text-slate-700">Uploaded Files:</h4>
          <ul className="mt-2 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {uploadedFiles.map((fileName, index) => (
              <li key={index} className="flex items-center bg-slate-100 text-slate-800 text-sm font-medium p-2 rounded-md">
                <FileXmlIcon className="w-5 h-5 mr-2 text-indigo-500 flex-shrink-0" />
                <span className="truncate">{fileName}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
