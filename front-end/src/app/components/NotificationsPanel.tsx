import React from 'react';
import { Bell, Clock, FileText, CheckCircle2, AlertCircle, Trash2 } from 'lucide-react';
import { motion } from 'motion/react';

interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning';
  title: string;
  description: string;
  time: string;
  isRead: boolean;
}

const notifications: Notification[] = [
  {
    id: '1',
    type: 'success',
    title: 'Proposition Acceptée',
    description: 'L\'appel d\'offres pour le "Parc Ville Verte" a été déplacé vers la phase en cours.',
    time: 'il y a 2 heures',
    isRead: false
  },
  {
    id: '2',
    type: 'info',
    title: 'Nouvel Appel d\'Offres Publié',
    description: 'Un nouvel appel d\'offres "Rénovation du Musée d\'Art Moderne" correspond à votre profil.',
    time: 'il y a 5 heures',
    isRead: false
  },
  {
    id: '3',
    type: 'warning',
    title: 'Date Limite Approchante',
    description: 'La date limite pour "Reconstruction du Pont Phase 2" est dans moins de 24 heures.',
    time: 'hier',
    isRead: true
  },
  {
    id: '4',
    type: 'info',
    title: 'Analyse IA Terminée',
    description: 'Votre document téléchargé "Specification_v2.pdf" a été traité.',
    time: 'il y a 2 jours',
    isRead: true
  }
];

export const NotificationsPanel: React.FC = () => {
  const getIcon = (type: string) => {
    switch (type) {
      case 'success': return <CheckCircle2 className="w-5 h-5 text-emerald-500" />;
      case 'warning': return <AlertCircle className="w-5 h-5 text-amber-500" />;
      default: return <FileText className="w-5 h-5 text-blue-500" />;
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Notifications</h2>
          <p className="text-slate-500">Restez informé de vos dernières activités d'appels d'offres</p>
        </div>
        <button className="flex items-center gap-2 text-sm font-bold text-slate-400 hover:text-red-500 transition-colors">
          <Trash2 className="w-4 h-4" />
          Tout effacer
        </button>
      </div>

      <div className="space-y-4">
        {notifications.map((notif, index) => (
          <motion.div
            key={notif.id}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1 }}
            className={`p-5 rounded-2xl border transition-all cursor-pointer group ${
              notif.isRead 
                ? 'bg-white border-slate-100' 
                : 'bg-blue-50/50 border-blue-100 shadow-sm shadow-blue-100/50'
            }`}
          >
            <div className="flex gap-4">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${
                notif.isRead ? 'bg-slate-100' : 'bg-white'
              }`}>
                {getIcon(notif.type)}
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-1">
                  <h3 className={`font-bold ${notif.isRead ? 'text-slate-700' : 'text-slate-900'}`}>
                    {notif.title}
                  </h3>
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
                    <Clock className="w-3 h-3" />
                    {notif.time}
                  </div>
                </div>
                <p className="text-sm text-slate-500 leading-relaxed mb-3">
                  {notif.description}
                </p>
                {!notif.isRead && (
                  <div className="flex gap-3">
                    <button className="text-xs font-bold text-blue-600 hover:underline">Marquer comme lu</button>
                    <button className="text-xs font-bold text-slate-400 hover:text-slate-600">Ignorer</button>
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
};
