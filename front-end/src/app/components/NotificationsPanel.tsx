import React, { useEffect, useState, useCallback } from 'react';
import { Bell, Clock, FileText, CheckCircle2, AlertCircle, Trash2, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { formatDistanceToNow } from 'date-fns';
import { fr } from 'date-fns/locale';

interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning';
  category: string;
  title: string;
  description: string;
  is_read: boolean;
  created_at: string;
}

const API_BASE_URL =
  (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_API_URL ||
  'http://localhost:8000';

const formatTime = (createdAt: string) =>
  formatDistanceToNow(new Date(createdAt), { addSuffix: true, locale: fr });

export const NotificationsPanel: React.FC = () => {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const getTenantId = () => {
    try {
      const t = localStorage.getItem('tenant');
      return t ? (JSON.parse(t) as { id: string }).id : null;
    } catch {
      return null;
    }
  };

  const fetchNotifications = useCallback(async () => {
    const tenantId = getTenantId();
    if (!tenantId) return;
    setIsLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE_URL}/notifications/by-tenant/${tenantId}`);
      if (!res.ok) throw new Error('Impossible de charger les notifications');
      const data = await res.json();
      // Handle the { value: [...], Count: X } format from the API
      const notificationsList = Array.isArray(data) ? data : (data.value || []);
      setNotifications(notificationsList);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur inconnue');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 30_000);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  const markAsRead = async (id: string) => {
    const tenantId = getTenantId();
    if (!tenantId) return;
    try {
      await fetch(`${API_BASE_URL}/notifications/${id}/read`, { method: 'PATCH' });
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
    } catch {
      // silent
    }
  };

  const dismiss = async (id: string) => {
    const tenantId = getTenantId();
    if (!tenantId) return;
    try {
      await fetch(`${API_BASE_URL}/notifications/${id}`, { method: 'DELETE' });
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    } catch {
      // silent
    }
  };

  const clearAll = async () => {
    const tenantId = getTenantId();
    if (!tenantId) return;
    try {
      await fetch(`${API_BASE_URL}/notifications/by-tenant/${tenantId}`, { method: 'DELETE' });
      setNotifications([]);
    } catch {
      // silent
    }
  };

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
        <button
          onClick={clearAll}
          disabled={notifications.length === 0}
          className="flex items-center gap-2 text-sm font-bold text-slate-400 hover:text-red-500 transition-colors disabled:opacity-40 disabled:pointer-events-none"
        >
          <Trash2 className="w-4 h-4" />
          Tout effacer
        </button>
      </div>

      {isLoading && notifications.length === 0 && (
        <div className="flex justify-center py-16 text-slate-400">
          <Loader2 className="w-6 h-6 animate-spin" />
        </div>
      )}

      {error && (
        <div className="text-center py-10 text-red-500 text-sm">{error}</div>
      )}

      {!isLoading && !error && notifications.length === 0 && (
        <div className="text-center py-16 text-slate-400">
          <Bell className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="font-medium">Aucune notification pour le moment</p>
        </div>
      )}

      <div className="space-y-4">
        <AnimatePresence initial={false}>
          {notifications.map((notif, index) => (
            <motion.div
              key={notif.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ delay: index * 0.05 }}
              className={`p-5 rounded-2xl border transition-all cursor-pointer group ${
                notif.is_read
                  ? 'bg-white border-slate-100'
                  : 'bg-blue-50/50 border-blue-100 shadow-sm shadow-blue-100/50'
              }`}
            >
              <div className="flex gap-4">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${
                    notif.is_read ? 'bg-slate-100' : 'bg-white'
                  }`}
                >
                  {getIcon(notif.type)}
                </div>
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-1">
                    <h3 className={`font-bold ${notif.is_read ? 'text-slate-700' : 'text-slate-900'}`}>
                      {notif.title}
                    </h3>
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium">
                      <Clock className="w-3 h-3" />
                      {formatTime(notif.created_at)}
                    </div>
                  </div>
                  <p className="text-sm text-slate-500 leading-relaxed mb-3">
                    {notif.description}
                  </p>
                  {!notif.is_read && (
                    <div className="flex gap-3">
                      <button
                        onClick={() => markAsRead(notif.id)}
                        className="text-xs font-bold text-blue-600 hover:underline"
                      >
                        Marquer comme lu
                      </button>
                      <button
                        onClick={() => dismiss(notif.id)}
                        className="text-xs font-bold text-slate-400 hover:text-slate-600"
                      >
                        Ignorer
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
};
