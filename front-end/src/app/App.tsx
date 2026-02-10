import React, { useState } from 'react';
import { Sidebar } from '@/app/components/Sidebar';
import { Navbar } from '@/app/components/Navbar';
import { TenderCard, Tender } from '@/app/components/TenderCard';
import { AIAgentSpace } from '@/app/components/AIAgentSpace';
import { NotificationsPanel } from '@/app/components/NotificationsPanel';
import { 
  TrendingUp, 
  Users, 
  Briefcase, 
  Clock, 
  Plus, 
  Filter,
  ArrowUpRight,
  ChevronRight,
  Sparkles
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const mockTenders: Tender[] = [
  {
    id: '1',
    title: 'Rénovation du Musée d\'Art Moderne',
    owner: 'Ministère de la Culture',
    status: 'New',
    budget: '12 400 000 $',
    deadline: '24 oct. 2026',
    location: 'Paris, France',
    image: 'https://images.unsplash.com/photo-1727777265265-b41e52787d4c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  },
  {
    id: '2',
    title: 'Infrastructure Smart City - Phase 4',
    owner: 'Autorité du Dév. Urbain',
    status: 'Ongoing',
    budget: '45 000 000 $',
    deadline: '12 déc. 2026',
    location: 'Berlin, Allemagne',
    image: 'https://images.unsplash.com/photo-1633360821222-7e8df83639fb?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  },
  {
    id: '3',
    title: 'Maintenance de Parc Éolien Côtier',
    owner: 'Green Energy Corp',
    status: 'Draft',
    budget: '3 200 000 $',
    deadline: '05 nov. 2026',
    location: 'Oslo, Norvège',
    image: 'https://images.unsplash.com/photo-1764336312138-14a5368a6cd3?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  },
  {
    id: '4',
    title: 'Réseau Fibre Optique IT Hub',
    owner: 'Telco Connect',
    status: 'Closed',
    budget: '8 500 000 $',
    deadline: '01 fév. 2026',
    location: 'Londres, Royaume-Uni',
    image: 'https://images.unsplash.com/photo-1727777265265-b41e52787d4c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  }
];

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');

  const renderDashboard = () => (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          { label: 'Offres Actives', value: '24', icon: Briefcase, color: 'blue', trend: '+12%' },
          { label: 'Total des Offres', value: '142', icon: Users, color: 'emerald', trend: '+5%' },
          { label: 'Budget Moyen', value: '4.2M$', icon: TrendingUp, color: 'indigo', trend: '+8%' },
          { label: 'Temps Gagné (IA)', value: '320h', icon: Clock, color: 'amber', trend: '+24%' },
        ].map((stat, i) => (
          <div key={i} className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow group">
            <div className="flex items-center justify-between mb-4">
              <div className={`p-3 rounded-2xl bg-${stat.color}-50 text-${stat.color}-600 group-hover:bg-${stat.color}-600 group-hover:text-white transition-colors`}>
                <stat.icon className="w-6 h-6" />
              </div>
              <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full flex items-center gap-1">
                <ArrowUpRight className="w-3 h-3" />
                {stat.trend}
              </span>
            </div>
            <p className="text-slate-500 text-sm font-medium mb-1">{stat.label}</p>
            <h3 className="text-3xl font-bold text-slate-900">{stat.value}</h3>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-3 bg-slate-900 p-8 rounded-3xl shadow-xl text-white relative overflow-hidden group">
          <div className="absolute top-0 right-0 p-12 opacity-10 group-hover:scale-110 transition-transform duration-700">
            <Plus className="w-48 h-48" />
          </div>
          <div className="relative z-10 h-full flex flex-col md:flex-row md:items-center gap-8">
            <div className="flex-1">
              <h3 className="text-3xl font-bold mb-4">Prêt à remporter plus d'offres ?<br /><span className="text-blue-400">Essayez l'Assistant IA</span></h3>
              <p className="text-slate-400 text-lg mb-8 leading-relaxed max-w-2xl">Laissez notre agent IA scanner vos documents d'appels d'offres. Il identifie les risques et rédige des stratégies gagnantes en quelques secondes.</p>
              <button 
                onClick={() => setActiveTab('ai-agent')}
                className="inline-flex bg-blue-600 hover:bg-blue-500 text-white font-bold py-4 px-8 rounded-2xl items-center justify-center gap-2 transition-all group/btn"
              >
                Aller à l'espace de travail IA
                <ChevronRight className="w-5 h-5 group-hover/btn:translate-x-1 transition-transform" />
              </button>
            </div>
            <div className="hidden lg:block w-1/3 aspect-video bg-blue-500/20 rounded-2xl border border-blue-500/30 flex items-center justify-center">
              <Sparkles className="w-20 h-20 text-blue-400 animate-pulse" />
            </div>
          </div>
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-slate-900">Appels d'offres récents</h3>
          <button onClick={() => setActiveTab('tenders')} className="text-sm font-bold text-blue-600 hover:text-blue-700">Voir tout</button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {mockTenders.slice(0, 4).map((tender) => (
            <TenderCard key={tender.id} tender={tender} />
          ))}
        </div>
      </div>
    </div>
  );

  const renderTenders = () => (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Annuaire des appels d'offres</h2>
          <p className="text-slate-500">Gérez et explorez toutes les opportunités disponibles</p>
        </div>
        <div className="flex gap-3">
          <button className="flex items-center gap-2 px-4 py-2.5 bg-white border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50 transition-colors shadow-sm">
            <Filter className="w-4 h-4" />
            Filtrer
          </button>
          <button className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-bold hover:bg-blue-700 transition-colors shadow-lg shadow-blue-500/20">
            <Plus className="w-4 h-4" />
            Créer une offre
          </button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {mockTenders.map((tender) => (
          <TenderCard key={tender.id} tender={tender} />
        ))}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <main className="pl-64 flex flex-col min-h-screen">
        <Navbar />
        
        <div className="flex-1 p-8 max-w-7xl mx-auto w-full">
          {activeTab === 'dashboard' && renderDashboard()}
          {activeTab === 'tenders' && renderTenders()}
          {activeTab === 'ai-agent' && <AIAgentSpace />}
          {activeTab === 'notifications' && <NotificationsPanel />}
        </div>
      </main>
    </div>
  );
};

export default App;
