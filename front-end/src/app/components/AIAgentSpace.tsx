import React, { useState, useCallback, useRef, useEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Bot, Upload, CheckCircle2, Loader2, Sparkles, Send, FileSearch, Zap, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

// ── Types ─────────────────────────────────────────────────────────────────────

type ChatMessage = {
  role: 'ai' | 'user';
  content: string;
  sources?: SourceChunk[];
  streaming?: boolean;
};

type SourceChunk = {
  chunk_id: string;
  content: string;
  score: number;
  metadata: { page_index?: number; block_type?: string };
};

type WSEvent = {
  type: 'ready' | 'retrieving' | 'sources' | 'generating' | 'token' | 'done' | 'error';
  data: any;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const RAG_WS_URL = import.meta.env.VITE_RAG_WS_URL ?? 'ws://localhost:8001/rag/ws';
const UPLOAD_API = import.meta.env.VITE_UPLOAD_API_URL ?? 'http://localhost:8000';

// ── Component ─────────────────────────────────────────────────────────────────

export const AIAgentSpace: React.FC = () => {
  const [isProcessing, setIsProcessing]     = useState(false);
  const [file, setFile]                     = useState<File | null>(null);
  const [documentId, setDocumentId]         = useState<string | null>(null);
  const [isConnected, setIsConnected]       = useState(false);
  const [isGenerating, setIsGenerating]     = useState(false);
  const [inputValue, setInputValue]         = useState('');
  const [chatMessages, setChatMessages]     = useState<ChatMessage[]>([
    {
      role: 'ai',
      content: "Bonjour ! Déposez un document PDF ci-dessous pour commencer. Une fois indexé, posez-moi n'importe quelle question à son sujet."
    }
  ]);

  const wsRef           = useRef<WebSocket | null>(null);
  const chatBottomRef   = useRef<HTMLDivElement>(null);
  const streamingIdx    = useRef<number>(-1);
  const pendingSources  = useRef<SourceChunk[]>([]);

  // ── Auto-scroll ────────────────────────────────────────────────────────────

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages]);

  // ── WebSocket ──────────────────────────────────────────────────────────────

  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(RAG_WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    ws.onmessage = (event) => {
      const msg: WSEvent = JSON.parse(event.data);

      switch (msg.type) {

        case 'retrieving':
          setIsGenerating(true);
          // Add a placeholder AI message for streaming
          setChatMessages(prev => {
            streamingIdx.current = prev.length;
            return [...prev, { role: 'ai', content: '', streaming: true }];
          });
          break;

        case 'sources':
          pendingSources.current = msg.data as SourceChunk[];
          break;

        case 'token':
          // Append token to the streaming message
          setChatMessages(prev => {
            const updated = [...prev];
            if (streamingIdx.current >= 0 && updated[streamingIdx.current]) {
              updated[streamingIdx.current] = {
                ...updated[streamingIdx.current],
                content: updated[streamingIdx.current].content + msg.data.text,
              };
            }
            return updated;
          });
          break;

        case 'done':
          // Finalise the streaming message — attach sources
          setChatMessages(prev => {
            const updated = [...prev];
            if (streamingIdx.current >= 0 && updated[streamingIdx.current]) {
              updated[streamingIdx.current] = {
                ...updated[streamingIdx.current],
                streaming: false,
                sources: pendingSources.current,
              };
            }
            return updated;
          });
          pendingSources.current = [];
          streamingIdx.current = -1;
          setIsGenerating(false);
          break;

        case 'error':
          setChatMessages(prev => {
            const updated = [...prev];
            // Replace streaming placeholder with error message
            if (streamingIdx.current >= 0 && updated[streamingIdx.current]) {
              updated[streamingIdx.current] = {
                role: 'ai',
                content: `⚠️ ${msg.data.message}`,
                streaming: false,
              };
            } else {
              updated.push({ role: 'ai', content: `⚠️ ${msg.data.message}` });
            }
            return updated;
          });
          streamingIdx.current = -1;
          pendingSources.current = [];
          setIsGenerating(false);
          break;
      }
    };
  }, []);

  // ── Upload ─────────────────────────────────────────────────────────────────

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (!acceptedFiles.length) return;
    const droppedFile = acceptedFiles[0];
    setFile(droppedFile);
    setIsProcessing(true);

    try {
      const formData = new FormData();
      formData.append('file', droppedFile);

      const response = await fetch(`${UPLOAD_API}/upload`, {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      const docId  = result.documentId ?? result.id ?? result.document_id;

      setIsProcessing(false);

      if (response.ok && docId) {
        setDocumentId(docId);
        connectWS();
        setChatMessages(prev => [
          ...prev,
          { role: 'user', content: `📎 ${droppedFile.name}` },
          {
            role: 'ai',
            content: `Document reçu et en cours d'indexation ✅\n\n**ID :** ${docId}\n\nPosez maintenant votre question sur ce document.`
          }
        ]);
      } else {
        setFile(null);
        setChatMessages(prev => [
          ...prev,
          { role: 'user', content: `📎 ${droppedFile.name}` },
          { role: 'ai', content: `❌ Erreur : ${result.error ?? 'Réponse inattendue du serveur.'}` }
        ]);
      }
    } catch {
      setIsProcessing(false);
      setFile(null);
      setChatMessages(prev => [
        ...prev,
        { role: 'ai', content: `❌ Impossible de joindre le serveur sur ${UPLOAD_API}.` }
      ]);
    }
  }, [connectWS]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: false,
    disabled: isProcessing,
  });

  // ── Send message ───────────────────────────────────────────────────────────

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isGenerating) return;

    const query = inputValue.trim();
    setInputValue('');

    // Add user message
    setChatMessages(prev => [...prev, { role: 'user', content: query }]);

    // Guard: must have a document and an open WS
    if (!documentId) {
      setChatMessages(prev => [...prev, {
        role: 'ai',
        content: '⚠️ Veuillez d\'abord déposer un document.'
      }]);
      return;
    }

    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      connectWS();
      setTimeout(() => sendQuery(query), 800);
      return;
    }

    sendQuery(query);
  };

  const sendQuery = (query: string) => {
    wsRef.current?.send(JSON.stringify({
      document_id: documentId,
      query,
      session_id: documentId,
      conversation_history: [],
    }));
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 h-[calc(100vh-140px)]">

      {/* ── Upload Zone ── */}
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
                <motion.div key="processing" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center text-center">
                  <Loader2 className="w-16 h-16 text-blue-500 animate-spin mb-4" />
                  <h3 className="text-lg font-bold text-slate-900 mb-2">Envoi en cours...</h3>
                  <p className="text-slate-500 text-sm">Le document est transmis au pipeline.</p>
                </motion.div>

              ) : file ? (
                <motion.div key="file" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col items-center text-center">
                  <motion.div className="w-20 h-20 bg-emerald-100 rounded-2xl flex items-center justify-center text-emerald-600 mb-4" initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 260, damping: 20 }}>
                    <CheckCircle2 className="w-10 h-10" />
                  </motion.div>
                  <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-6 py-2 mb-3">
                    <p className="text-emerald-700 font-bold text-sm">✓ TÉLÉCHARGEMENT RÉUSSI</p>
                  </div>
                  <h3 className="text-lg font-bold text-slate-900 mb-1">{file.name}</h3>
                  {documentId && (
                    <p className="text-xs text-slate-400 font-mono mb-4 break-all px-4">{documentId}</p>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); setFile(null); setDocumentId(null); wsRef.current?.close(); }}
                    className="text-sm font-bold text-red-500 hover:text-red-600 px-4 py-2"
                  >
                    Supprimer et télécharger un autre
                  </button>
                </motion.div>

              ) : (
                <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center text-center">
                  <div className="w-20 h-20 bg-slate-100 rounded-3xl flex items-center justify-center text-slate-400 mb-6">
                    <Upload className="w-10 h-10" />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900 mb-2">Déposez votre offre ici</h3>
                  <p className="text-slate-500 text-sm max-w-xs mb-8">Fichiers PDF uniquement — jusqu'à 25 Mo.</p>
                  <button className="bg-slate-900 text-white px-8 py-3 rounded-xl font-bold hover:bg-slate-800 transition-colors">
                    Sélectionner un fichier
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* ── Chat ── */}
      <div className="flex flex-col bg-slate-900 rounded-3xl shadow-2xl overflow-hidden border border-slate-800">

        {/* Header */}
        <div className="p-6 bg-slate-800/50 border-b border-slate-800 flex items-center gap-4">
          <div className="relative">
            <div className="w-12 h-12 bg-blue-600 rounded-2xl flex items-center justify-center text-white">
              <Bot className="w-7 h-7" />
            </div>
            <span className={`absolute bottom-0 right-0 w-3 h-3 border-2 border-slate-900 rounded-full transition-colors ${isConnected ? 'bg-emerald-500' : documentId ? 'bg-yellow-400' : 'bg-slate-600'}`} />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-white">Bot d'Intelligence d'Offres</h3>
            <p className="text-xs text-slate-400 font-medium">
              {isConnected ? '🟢 Connecté au RAG' : documentId ? '🟡 Connexion...' : '⚪ En attente d\'un document'}
            </p>
          </div>
          {isGenerating && (
            <div className="flex items-center gap-2 text-blue-400 text-xs font-medium">
              <Zap className="w-3 h-3 animate-pulse" />
              Génération...
            </div>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
          {chatMessages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              <div className={`max-w-[85%] p-4 rounded-2xl text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-none'
                  : 'bg-slate-800 text-slate-200 rounded-tl-none border border-slate-700'
              }`}>
                {msg.content.split('\n').map((line, j) => (
                  <p key={j} className={j > 0 ? 'mt-2' : ''}>{line}</p>
                ))}
                {/* Streaming cursor */}
                {msg.streaming && (
                  <span className="inline-block w-2 h-4 bg-blue-400 ml-1 animate-pulse rounded-sm align-middle" />
                )}
              </div>

              {/* Source citations */}
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-2 max-w-[85%] space-y-1">
                  <p className="text-xs text-slate-500 flex items-center gap-1 px-1">
                    <FileSearch className="w-3 h-3" /> {msg.sources.length} source(s) utilisée(s)
                  </p>
                  {msg.sources.map((src, si) => (
                    <div key={si} className="bg-slate-800/60 border border-slate-700 rounded-xl px-3 py-2 text-xs text-slate-400">
                      <span className="text-blue-400 font-bold mr-2">[{si + 1}]</span>
                      {src.metadata.page_index !== undefined && (
                        <span className="text-slate-500 mr-2">p.{src.metadata.page_index + 1}</span>
                      )}
                      <span className="line-clamp-2">{src.content.slice(0, 120)}…</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          ))}
          <div ref={chatBottomRef} />
        </div>

        {/* Input */}
        <div className="p-6 border-t border-slate-800">
          {!documentId && (
            <div className="flex items-center gap-2 text-xs text-yellow-400 mb-3 px-1">
              <AlertCircle className="w-3 h-3" />
              Déposez d'abord un document pour activer le chat.
            </div>
          )}
          <form onSubmit={handleSend} className="relative">
            <input
              type="text"
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              placeholder={documentId ? "Posez une question sur le document..." : "En attente d'un document..."}
              disabled={!documentId || isGenerating}
              className="w-full bg-slate-800 border border-slate-700 rounded-2xl py-4 pl-6 pr-14 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || !documentId || isGenerating}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-blue-600 text-white rounded-xl hover:bg-blue-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isGenerating
                ? <Loader2 className="w-5 h-5 animate-spin" />
                : <Send className="w-5 h-5" />
              }
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
