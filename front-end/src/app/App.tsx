import React, { useState, useEffect } from 'react';
import { Sidebar } from '@/app/components/Sidebar';
import { Navbar } from '@/app/components/Navbar';
import { TenderCard, Tender } from '@/app/components/TenderCard';
import { AIAgentSpace } from '@/app/components/AIAgentSpace';
import { NotificationsPanel } from '@/app/components/NotificationsPanel';
import { TenantProfileForm } from '@/app/components/TenantProfileForm';
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
    organizationName: 'Ministère de la Culture',
    isCompliant: true,
    chiffreAffaireMinimal: '12 400 000 $',
    deadline: '24 oct. 2026',
    certificat: 'ISO 9001',
    image: 'https://images.unsplash.com/photo-1727777265265-b41e52787d4c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  },
  {
    id: '2',
    title: 'Infrastructure Smart City - Phase 4',
    organizationName: 'Autorité du Dév. Urbain',
    isCompliant: false,
    chiffreAffaireMinimal: '45 000 000 $',
    deadline: '12 déc. 2026',
    certificat: 'ISO 14001',
    image: 'https://images.unsplash.com/photo-1633360821222-7e8df83639fb?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  },
  {
    id: '3',
    title: 'Maintenance de Parc Éolien Côtier',
    organizationName: 'Green Energy Corp',
    isCompliant: true,
    chiffreAffaireMinimal: '3 200 000 $',
    deadline: '05 nov. 2026',
    certificat: 'ISO 45001',
    image: 'https://images.unsplash.com/photo-1764336312138-14a5368a6cd3?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  },
  {
    id: '4',
    title: 'Réseau Fibre Optique IT Hub',
    organizationName: 'Telco Connect',
    isCompliant: false,
    chiffreAffaireMinimal: '8 500 000 $',
    deadline: '01 fév. 2026',
    certificat: 'ISO 27001',
    image: 'https://images.unsplash.com/photo-1727777265265-b41e52787d4c?crop=entropy&cs=tinysrgb&fit=max&fm=jpg&q=80&w=1080'
  }
];

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem('user'));
  const [authMode, setAuthMode] = useState<'login' | 'signup'>('login');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authError, setAuthError] = useState('');
  const [authMessage, setAuthMessage] = useState('');

  const [tenders, setTenders] = useState<Tender[]>([]);
  const [isLoadingTenders, setIsLoadingTenders] = useState(false);

  const [tenantEmail, setTenantEmail] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const [signupTenantName, setSignupTenantName] = useState('');
  const [signupTenantEmail, setSignupTenantEmail] = useState('');
  const [signupFullName, setSignupFullName] = useState('');
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');

  const API_BASE_URL = (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    if (isAuthenticated) {
      fetchTenders();
    }
  }, [isAuthenticated]);

  const fetchTenders = async () => {
    try {
      setIsLoadingTenders(true);
      const tenantStr = localStorage.getItem('tenant');
      if (!tenantStr) return;
      const tenant = JSON.parse(tenantStr);
      
      const response = await fetch(`${API_BASE_URL}/ao/tenders/${tenant.id}`);
      if (response.ok) {
        const data = await response.json();
        setTenders(data);
      }
    } catch (error) {
      console.error('Error fetching tenders:', error);
    } finally {
      setIsLoadingTenders(false);
    }
  };

  const handleLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setAuthError('');
    setAuthMessage('');
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tenant_email: tenantEmail, email, password }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || 'Login failed');
      }

      setIsAuthenticated(true);
      localStorage.setItem('user', JSON.stringify(data.user));
      localStorage.setItem('tenant', JSON.stringify(data.tenant));
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Login failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSignup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setAuthError('');
    setAuthMessage('');
    try {
      const response = await fetch(`${API_BASE_URL}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_name: signupTenantName,
          tenant_email: signupTenantEmail,
          full_name: signupFullName,
          email: signupEmail,
          password: signupPassword,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || 'Sign-up failed');
      }

      setAuthMessage('Compte créé. Connectez-vous maintenant.');
      setAuthMode('login');
      setTenantEmail(signupTenantEmail);
      setEmail(signupEmail);
      setPassword('');
      setSignupPassword('');
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Sign-up failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderAuthScreen = () => (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-2xl shadow-sm p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Espace Employeur</h1>
          <p className="text-slate-500 text-sm mt-1">
            {authMode === 'login' ? 'Connectez-vous à votre plateforme.' : 'Créez votre compte employeur.'}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2 bg-slate-100 rounded-xl p-1">
          <button
            type="button"
            onClick={() => { setAuthMode('login'); setAuthError(''); }}
            className={`py-2 rounded-lg text-sm font-semibold ${authMode === 'login' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
          >
            Login
          </button>
          <button
            type="button"
            onClick={() => { setAuthMode('signup'); setAuthError(''); }}
            className={`py-2 rounded-lg text-sm font-semibold ${authMode === 'signup' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-600'}`}
          >
            Sign up
          </button>
        </div>

        {authMode === 'login' ? (
          <form className="space-y-3" onSubmit={handleLogin}>
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Email entreprise (tenant)"
              type="email"
              value={tenantEmail}
              onChange={(e) => setTenantEmail(e.target.value)}
              required
            />
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Email utilisateur"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Mot de passe"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={12}
              required
            />
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white rounded-xl py-2.5 text-sm font-bold"
            >
              {isSubmitting ? 'Connexion...' : 'Se connecter'}
            </button>
          </form>
        ) : (
          <form className="space-y-3" onSubmit={handleSignup}>
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Nom de l’entreprise"
              value={signupTenantName}
              onChange={(e) => setSignupTenantName(e.target.value)}
              required
            />
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Email entreprise (tenant)"
              type="email"
              value={signupTenantEmail}
              onChange={(e) => setSignupTenantEmail(e.target.value)}
              required
            />
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Nom complet"
              value={signupFullName}
              onChange={(e) => setSignupFullName(e.target.value)}
              required
            />
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Email utilisateur"
              type="email"
              value={signupEmail}
              onChange={(e) => setSignupEmail(e.target.value)}
              required
            />
            <input
              className="w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
              placeholder="Mot de passe"
              type="password"
              value={signupPassword}
              onChange={(e) => setSignupPassword(e.target.value)}
              minLength={12}
              required
            />
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white rounded-xl py-2.5 text-sm font-bold"
            >
              {isSubmitting ? 'Création...' : 'Créer un compte'}
            </button>
          </form>
        )}

        {authError && <p className="text-sm text-red-600">{authError}</p>}
        {authMessage && <p className="text-sm text-emerald-600">{authMessage}</p>}
      </div>
    </div>
  );

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
        {isLoadingTenders ? (
          <div className="text-center py-10 text-slate-500">Chargement des données...</div>
        ) : tenders.length === 0 ? (
          <div className="text-center py-10 text-slate-500">Aucun appel d'offre trouvé</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {tenders.slice(0, 4).map((tender) => (
              <TenderCard key={tender.id} tender={tender} />
            ))}
          </div>
        )}
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
        {isLoadingTenders ? (
          <div className="col-span-full text-center py-10 text-slate-500">Chargement des données...</div>
        ) : tenders.length === 0 ? (
          <div className="col-span-full text-center py-10 text-slate-500">Aucun appel d'offre trouvé</div>
        ) : (
          tenders.map((tender) => (
            <TenderCard key={tender.id} tender={tender} />
          ))
        )}
      </div>
    </div>
  );

  if (!isAuthenticated) {
    return renderAuthScreen();
  }

  return (
    <div className="min-h-screen bg-slate-50 font-sans text-slate-900">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <main className="pl-64 flex flex-col min-h-screen">
        <Navbar onProfileClick={() => setActiveTab('profile')} />
        
        <div className="flex-1 p-8 max-w-7xl mx-auto w-full">
          {activeTab === 'dashboard' && renderDashboard()}
          {activeTab === 'tenders' && renderTenders()}
          {activeTab === 'ai-agent' && <AIAgentSpace />}
          {activeTab === 'notifications' && <NotificationsPanel />}
          {activeTab === 'profile' && <TenantProfileForm />}
        </div>
      </main>
    </div>
  );
};

export default App;
