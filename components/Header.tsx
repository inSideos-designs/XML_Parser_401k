import React from 'react';
// import { LogoIcon } from './Icons';

export const Header: React.FC = () => {
  return (
    <header className="bg-white shadow-md border-b border-slate-200">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          <div className="flex items-center">
            <img
              src="/nppg-logo"
              alt="NPPG"
              className="h-10 w-auto"
            />
            <h1 className="ml-3 text-2xl font-bold text-slate-800">
              XML Prompt Filler
            </h1>
          </div>
        </div>
      </div>
    </header>
  );
};
