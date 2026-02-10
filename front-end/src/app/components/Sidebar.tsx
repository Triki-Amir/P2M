import React from 'react';
import { 
  LayoutDashboard, 
  FileText, 
  Bell, 
  Bot, 
  Settings, 
  HelpCircle,
  Menu,
  ChevronRight
} from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  const menuItems = [
    { id: 'dashboard', icon: LayoutDashboard, label: 'Tableau de bord' },
    { id: 'tenders', icon: FileText, label: 'Appels d\'offres' },
    { id: 'notifications', icon: Bell, label: 'Notifications' },
    { id: 'ai-agent', icon: Bot, label: 'Agent IA' },
  ];

  return (
    <div className="w-64 h-screen bg-slate-900 text-white flex flex-col fixed left-0 top-0 z-50 transition-all duration-300">
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center">
          <FileText className="text-white w-5 h-5" />
        </div>
        <span className="font-bold text-xl tracking-tight">TenderHub</span>
      </div>

      <nav className="flex-1 px-4 py-6 space-y-2">
        {menuItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 group ${
              activeTab === item.id 
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' 
                : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`}
          >
            <item.icon className={`w-5 h-5 ${activeTab === item.id ? 'text-white' : 'group-hover:text-blue-400'}`} />
            <span className="font-medium">{item.label}</span>
            {activeTab === item.id && (
              <ChevronRight className="w-4 h-4 ml-auto" />
            )}
          </button>
        ))}
      </nav>

      <div className="p-4 mt-auto border-t border-slate-800">
        <button className="w-full flex items-center gap-3 px-4 py-3 text-slate-400 hover:text-white transition-colors">
          <Settings className="w-5 h-5" />
          <span className="font-medium">Paramètres</span>
        </button>
        <button className="w-full flex items-center gap-3 px-4 py-3 text-slate-400 hover:text-white transition-colors">
          <HelpCircle className="w-5 h-5" />
          <span className="font-medium">Support</span>
        </button>
      </div>
    </div>
  );
};
