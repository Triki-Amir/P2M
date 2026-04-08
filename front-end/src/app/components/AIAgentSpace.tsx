import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { Bot, Upload, FileText, CheckCircle2, Loader2, Sparkles, MessageSquare, Send } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

export const AIAgentSpace: React.FC = () => {
  const uploadApiBase = import.meta.env.VITE_UPLOAD_API_URL ?? 'http://localhost:8000';
  const [isProcessing, setIsProcessing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [chatMessages, setChatMessages] = useState<{ role: 'ai' | 'user'; content: string }[]>([
    { role: 'ai', content: "Bonjour ! Je suis votre assistant IA spécialisé dans les appels d'offres. Déposez un document d'appel d'offres ici (PDF), et je l'enregistrerai dans votre base de données PostgreSQL locale, le stockerai dans MinIO et l'analyserai pour vous." }
  ]);
  const [inputValue, setInputValue] = useState('');

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const droppedFile = acceptedFiles[0];
      setFile(droppedFile);
      setIsProcessing(true);
      
      try {
        // Upload to backend
        const formData = new FormData();
        formData.append("file", droppedFile);

        const response = await fetch(`${uploadApiBase}/upload`, {
          method: "POST",
          body: formData
        });

        const result = await response.json();
        const documentId = result.documentId ?? result.id;
        const storagePath = result.storagePath ?? result.storage_path;
        
        setIsProcessing(false);
        
        if (response.ok) {
          setChatMessages(prev => [
            ...prev,
            { role: 'user', content: `Document téléchargé : ${droppedFile.name}` },
            { role: 'ai', content: `J'ai analysé "${droppedFile.name}". Le document a été enregistré avec succès dans la base de données.\n\nID du document : ${documentId}\nChemin de stockage : ${storagePath}\n\nJe peux maintenant vous aider à analyser ce document. Que souhaitez-vous savoir ?` }
          ]);
        } else {
          setChatMessages(prev => [
            ...prev,
            { role: 'user', content: `Tentative de téléchargement : ${droppedFile.name}` },
            { role: 'ai', content: `Erreur lors du téléchargement : ${result.error || "Erreur inconnue"}. Veuillez réessayer.` }
          ]);
          setFile(null);
        }
      } catch (error) {
        setIsProcessing(false);
        setChatMessages(prev => [
          ...prev,
          { role: 'user', content: `Tentative de téléchargement : ${droppedFile.name}` },
          { role: 'ai', content: `Erreur de connexion au serveur. Assurez-vous que le backend est en cours d'exécution sur ${uploadApiBase}` }
        ]);
        setFile(null);
      }
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx']
    },
    multiple: false
  });

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim()) return;

    setChatMessages(prev => [...prev, { role: 'user', content: inputValue }]);
    setInputValue('');

    // Simulate AI response
    setTimeout(() => {
      setChatMessages(prev => [...prev, { role: 'ai', content: "Je m'en occupe. Compte tenu des exigences, je suggère de mettre en avant notre récente certification ISO et le système de refroidissement écologique que nous avons mis en œuvre pour le projet de Zurich." }]);
    }, 1500);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-[calc(100vh-140px)]">
      {/* Upload Zone */}
      <div className="flex flex-col gap-6">
        <div className="bg-white p-8 rounded-3xl border border-slate-200 shadow-sm flex-1 flex flex-col">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 bg-blue-100 rounded-2xl flex items-center justify-center text-blue-600">
              <Sparkles className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">Analyse de documents IA</h2>
              <p className="text-sm text-slate-500">Obtenez des insights instantanés sur vos appels d'offres</p>
            </div>
          </div>

          <div 
            {...getRootProps()} 
            className={`flex-1 border-2 border-dashed rounded-3xl flex flex-col items-center justify-center p-12 transition-all cursor-pointer ${
              isDragActive 
                ? 'border-blue-500 bg-blue-50/50' 
                : 'border-slate-200 hover:border-blue-400 hover:bg-slate-50'
            }`}
          >
            <input {...getInputProps()} />
            
            <AnimatePresence mode="wait">
              {isProcessing ? (
                <motion.div 
                  key="processing"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className="flex flex-col items-center text-center"
                >
                  <Loader2 className="w-16 h-16 text-blue-500 animate-spin mb-4" />
                  <h3 className="text-lg font-bold text-slate-900 mb-2">Analyse du document en cours...</h3>
                  <p className="text-slate-500 text-sm max-w-xs">Recherche des exigences de conformité, des délais et de la portée du projet.</p>
                </motion.div>
              ) : file ? (
                <motion.div 
                  key="file"
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex flex-col items-center text-center"
                >
                  <motion.div 
                    className="w-20 h-20 bg-emerald-100 rounded-2xl flex items-center justify-center text-emerald-600 mb-4"
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ 
                      type: "spring",
                      stiffness: 260,
                      damping: 20,
                      delay: 0.1 
                    }}
                  >
                    <CheckCircle2 className="w-10 h-10" />
                  </motion.div>
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2 }}
                    className="bg-emerald-50 border border-emerald-200 rounded-xl px-6 py-2 mb-3"
                  >
                    <p className="text-emerald-700 font-bold text-sm">✓ TÉLÉCHARGEMENT RÉUSSI</p>
                  </motion.div>
                  <h3 className="text-lg font-bold text-slate-900 mb-2">{file.name}</h3>
                  <p className="text-slate-500 text-sm mb-6">Traité et indexé avec succès dans PostgreSQL.</p>
                  <button 
                    onClick={(e) => { e.stopPropagation(); setFile(null); }}
                    className="text-sm font-bold text-red-500 hover:text-red-600 px-4 py-2"
                  >
                    Supprimer et télécharger un autre
                  </button>
                </motion.div>
              ) : (
                <motion.div 
                  key="empty"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex flex-col items-center text-center"
                >
                  <div className="w-20 h-20 bg-slate-100 rounded-3xl flex items-center justify-center text-slate-400 mb-6 group-hover:bg-blue-100 group-hover:text-blue-500 transition-colors">
                    <Upload className="w-10 h-10" />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900 mb-2">Déposez votre offre ici</h3>
                  <p className="text-slate-500 text-sm max-w-xs mb-8">Supporte les fichiers PDF, DOCX et DOC jusqu'à 25 Mo.</p>
                  <button className="bg-slate-900 text-white px-8 py-3 rounded-xl font-bold hover:bg-slate-800 transition-colors">
                    Sélectionner un fichier
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* AI Chat / Agent Space */}
      <div className="flex flex-col bg-slate-900 rounded-3xl shadow-2xl overflow-hidden border border-slate-800">
        <div className="p-6 bg-slate-800/50 border-b border-slate-800 flex items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 bg-blue-600 rounded-2xl flex items-center justify-center text-white">
              <Bot className="w-7 h-7" />
            </div>
            <span className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 border-2 border-slate-900 rounded-full"></span>
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Bot d'Intelligence d'Offres</h3>
            <p className="text-xs text-slate-400 font-medium">En ligne • Réponse instantanée</p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
          {chatMessages.map((msg, i) => (
            <motion.div 
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[85%] p-4 rounded-2xl text-sm ${
                msg.role === 'user' 
                  ? 'bg-blue-600 text-white rounded-tr-none' 
                  : 'bg-slate-800 text-slate-200 rounded-tl-none border border-slate-700'
              }`}>
                {msg.content.split('\n').map((line, index) => (
                  <p key={index} className={index > 0 ? 'mt-2' : ''}>{line}</p>
                ))}
              </div>
            </motion.div>
          ))}
        </div>

        <div className="p-6 border-t border-slate-800">
          <form onSubmit={handleSendMessage} className="relative">
            <input 
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Posez une question sur l'offre ou rédigez une réponse..."
              className="w-full bg-slate-800 border border-slate-700 rounded-2xl py-4 pl-6 pr-14 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all"
            />
            <button 
              type="submit"
              className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-blue-600 text-white rounded-xl hover:bg-blue-500 transition-colors disabled:opacity-50"
              disabled={!inputValue.trim()}
            >
              <Send className="w-5 h-5" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
