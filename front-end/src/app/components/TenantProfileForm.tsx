import React, { useState, useEffect } from 'react';
import { Save, Building2, MapPin, ShieldCheck, TrendingUp, Users, Award, Loader2 } from 'lucide-react';

interface TenantMetadata {
  geo_zone?: string;
  guarantee?: string;
  annual_revenue?: number;
  certifications?: string[];
  staff_count?: {
    engineers: number;
    technicians: number;
    others: number;
  };
}

export const TenantProfileForm: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
  
  const [metadata, setMetadata] = useState<TenantMetadata>({
    geo_zone: '',
    guarantee: '',
    annual_revenue: 0,
    certifications: [],
    staff_count: { engineers: 0, technicians: 0, others: 0 }
  });

  const [certInput, setCertInput] = useState('');

  const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';

  useEffect(() => {
    const fetchTenantData = async () => {
      const storedTenant = localStorage.getItem('tenant');
      if (!storedTenant) return;
      
      const { id } = JSON.parse(storedTenant);
      try {
        const response = await fetch(`${API_BASE_URL}/tenants/${id}`);
        if (response.ok) {
          const data = await response.json();
          if (data.metadata) {
            setMetadata({
              geo_zone: data.metadata.geo_zone || '',
              guarantee: data.metadata.guarantee || '',
              annual_revenue: data.metadata.annual_revenue || 0,
              certifications: data.metadata.certifications || [],
              staff_count: data.metadata.staff_count || { engineers: 0, technicians: 0, others: 0 }
            });
          }
        }
      } catch (err) {
        console.error("Failed to fetch tenant data", err);
      } finally {
        setFetching(false);
      }
    };

    fetchTenantData();
  }, [API_BASE_URL]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage(null);

    const storedTenant = localStorage.getItem('tenant');
    if (!storedTenant) return;
    const { id } = JSON.parse(storedTenant);

    try {
      console.log("Sending metadata:", JSON.stringify(metadata, null, 2));
      const response = await fetch(`${API_BASE_URL}/tenants/${id}/metadata`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(metadata)
      });

      if (response.ok) {
        const result = await response.json();
        console.log("Save successful:", result);
        setMessage({ type: 'success', text: 'Profil mis à jour avec succès !' });
      } else {
        const errorData = await response.json();
        console.error("Save failed:", errorData);
        throw new Error(errorData.detail || 'Erreur lors de la mise à jour');
      }
    } catch (err: any) {
      console.error("Catch error:", err);
      setMessage({ type: 'error', text: `Impossible de sauvegarder : ${err.message}` });
    } finally {
      setLoading(false);
    }
  };

  const addCert = () => {
    if (certInput.trim() && !metadata.certifications?.includes(certInput.trim())) {
      setMetadata({
        ...metadata,
        certifications: [...(metadata.certifications || []), certInput.trim()]
      });
      setCertInput('');
    }
  };

  const removeCert = (cert: string) => {
    setMetadata({
      ...metadata,
      certifications: metadata.certifications?.filter(c => c !== cert)
    });
  };

  if (fetching) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 bg-white rounded-3xl border border-slate-200 shadow-sm animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center gap-4 mb-8 border-b border-slate-100 pb-6">
        <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl">
          <Building2 className="w-8 h-8" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Profil de l'Entreprise</h2>
          <p className="text-slate-500">Gérez les informations de votre structure pour optimiser les réponses IA</p>
        </div>
      </div>

      <form onSubmit={handleSave} className="space-y-8">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Zone Géo */}
          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <MapPin className="w-4 h-4" /> Zone Géographique
            </label>
            <input
              type="text"
              className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all outline-none"
              placeholder="ex: MENA, Afrique de l'Ouest, Europe..."
              value={metadata.geo_zone}
              onChange={e => setMetadata({...metadata, geo_zone: e.target.value})}
            />
          </div>

          {/* Garantie */}
          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" /> Garantie / Assurances
            </label>
            <input
              type="text"
              className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all outline-none"
              placeholder="ex: RC Professionnelle, Décennale..."
              value={metadata.guarantee}
              onChange={e => setMetadata({...metadata, guarantee: e.target.value})}
            />
          </div>

          {/* Chiffre d'affaire */}
          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" /> Chiffre d'affaire Annuel ($)
            </label>
            <input
              type="number"
              className="w-full px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all outline-none"
              value={metadata.annual_revenue}
              onChange={e => setMetadata({...metadata, annual_revenue: parseFloat(e.target.value)})}
            />
          </div>

          {/* Certifications */}
          <div className="space-y-2">
            <label className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <Award className="w-4 h-4" /> Certifications (ISO, QUALIBAT...)
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:bg-white transition-all outline-none"
                placeholder="Ajouter une certif..."
                value={certInput}
                onChange={e => setCertInput(e.target.value)}
                onKeyPress={e => e.key === 'Enter' && (e.preventDefault(), addCert())}
              />
              <button 
                type="button" 
                onClick={addCert}
                className="bg-slate-100 hover:bg-slate-200 p-2.5 rounded-xl transition-colors"
              >
                Ajouter
              </button>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {metadata.certifications?.map(c => (
                <span key={c} className="bg-blue-50 text-blue-700 text-xs font-bold px-3 py-1.5 rounded-full flex items-center gap-2">
                  {c}
                  <button onClick={() => removeCert(c)} className="hover:text-red-500">×</button>
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Staff Count */}
        <div className="bg-slate-50 p-6 rounded-2xl border border-slate-100">
          <label className="text-sm font-bold text-slate-900 flex items-center gap-2 mb-4">
            <Users className="w-4 h-4" /> Effectif global
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div className="space-y-1">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Ingénieurs</span>
              <input
                type="number"
                className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                value={metadata.staff_count?.engineers}
                onChange={e => setMetadata({
                  ...metadata, 
                  staff_count: { ...metadata.staff_count!, engineers: parseInt(e.target.value) }
                })}
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Techniciens</span>
              <input
                type="number"
                className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                value={metadata.staff_count?.technicians}
                onChange={e => setMetadata({
                  ...metadata, 
                  staff_count: { ...metadata.staff_count!, technicians: parseInt(e.target.value) }
                })}
              />
            </div>
            <div className="space-y-1">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Autres</span>
              <input
                type="number"
                className="w-full px-4 py-2 bg-white border border-slate-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                value={metadata.staff_count?.others}
                onChange={e => setMetadata({
                  ...metadata, 
                  staff_count: { ...metadata.staff_count!, others: parseInt(e.target.value) }
                })}
              />
            </div>
          </div>
        </div>

        {message && (
          <div className={`p-4 rounded-xl text-sm font-medium ${message.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' : 'bg-red-50 text-red-700 border border-red-100'}`}>
            {message.text}
          </div>
        )}

        <div className="flex justify-end gap-4 border-t border-slate-100 pt-6">
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold py-3 px-8 rounded-xl transition-all shadow-lg shadow-blue-200"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
            Enregistrer les modifications
          </button>
        </div>
      </form>
    </div>
  );
};