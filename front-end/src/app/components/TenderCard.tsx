import React from 'react';
import { Calendar, User, Clock, MoreVertical, ExternalLink } from 'lucide-react';
import { ImageWithFallback } from '@/app/components/figma/ImageWithFallback';

export interface Tender {
  id: string;
  title: string;
  owner: string;
  status: 'New' | 'Ongoing' | 'Closed' | 'Draft';
  budget: string;
  deadline: string;
  location: string;
  image: string;
}

interface TenderCardProps {
  tender: Tender;
}

export const TenderCard: React.FC<TenderCardProps> = ({ tender }) => {
  const statusColors = {
    New: 'bg-emerald-100 text-emerald-700',
    Ongoing: 'bg-blue-100 text-blue-700',
    Closed: 'bg-slate-100 text-slate-700',
    Draft: 'bg-amber-100 text-amber-700',
  };

  const statusLabels = {
    New: 'Nouveau',
    Ongoing: 'En cours',
    Closed: 'Clôturé',
    Draft: 'Brouillon',
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden hover:shadow-xl hover:shadow-slate-200/50 transition-all duration-300 group">
      <div className="h-40 relative">
        <ImageWithFallback
          src={tender.image}
          alt={tender.title}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
        />
        <div className="absolute top-4 left-4">
          <span className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider shadow-sm ${statusColors[tender.status]}`}>
            {statusLabels[tender.status]}
          </span>
        </div>
        <button className="absolute top-4 right-4 p-2 bg-white/20 backdrop-blur-md rounded-lg text-white hover:bg-white/40 transition-colors">
          <MoreVertical className="w-4 h-4" />
        </button>
      </div>

      <div className="p-5">
        <h3 className="font-bold text-slate-900 text-lg mb-2 line-clamp-1 group-hover:text-blue-600 transition-colors">
          {tender.title}
        </h3>
        
        <div className="space-y-3 mb-6">
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <User className="w-4 h-4 text-slate-400" />
            <span>{tender.owner}</span>
          </div>
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <Clock className="w-4 h-4 text-slate-400" />
            <span>Date limite : <span className="font-semibold text-slate-700">{tender.deadline}</span></span>
          </div>
          <div className="flex items-center gap-2 text-slate-500 text-sm">
            <Calendar className="w-4 h-4 text-slate-400" />
            <span>Lieu : {tender.location}</span>
          </div>
        </div>

        <div className="flex items-center justify-between pt-4 border-t border-slate-100">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold mb-0.5">Budget</p>
            <p className="text-lg font-bold text-slate-900">{tender.budget}</p>
          </div>
          <button className="p-2.5 bg-slate-50 hover:bg-blue-50 text-slate-400 hover:text-blue-600 rounded-xl transition-all border border-transparent hover:border-blue-100">
            <ExternalLink className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
};
