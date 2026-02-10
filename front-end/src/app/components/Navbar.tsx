import React from 'react';
import { Search, Bell, User, ChevronDown } from 'lucide-react';

export const Navbar: React.FC = () => {
  return (
    <header className="h-16 bg-white border-b border-slate-200 flex items-center justify-between px-8 sticky top-0 z-40">
      <div className="flex-1 max-w-xl">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
          <input
            type="text"
            placeholder="Rechercher des offres, documents ou agents..."
            className="w-full pl-10 pr-4 py-2 bg-slate-100 border-none rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all outline-none"
          />
        </div>
      </div>

      <div className="flex items-center gap-6">
        <div className="relative cursor-pointer group">
          <div className="p-2 text-slate-500 hover:bg-slate-100 rounded-full transition-colors relative">
            <Bell className="w-5 h-5" />
            <span className="absolute top-1 right-1 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
          </div>
        </div>

        <div className="h-8 w-px bg-slate-200"></div>

        <button className="flex items-center gap-3 hover:bg-slate-50 p-1.5 rounded-lg transition-colors">
          <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs">
            JD
          </div>
          <div className="text-left hidden sm:block">
            <p className="text-xs font-semibold text-slate-900 leading-tight">Jean Dupont</p>
            <p className="text-[10px] text-slate-500 font-medium">Chef de projet</p>
          </div>
          <ChevronDown className="w-4 h-4 text-slate-400" />
        </button>
      </div>
    </header>
  );
};
