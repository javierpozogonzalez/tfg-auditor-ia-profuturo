"use client"

import { useState, useEffect, useRef } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  Bot, Send, FileDown, Sparkles, Paperclip, X, Table2,
  Clock, Plus, MessageSquare, Pencil, Trash2, Check,
} from "lucide-react"
import { useCommunity } from "@/lib/community-context"

interface Message {
  id: number
  role: "ai" | "user"
  content: string
  loading?: boolean
  pdf?: { base64: string; filename: string }
  excel?: { base64: string; filename: string }
  files?: Array<{ name: string; type: string; size: number }>
}

interface ConversationItem {
  id: string
  community: string
  title: string
  created_at: string
  updated_at: string
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const CHAT_TIMEOUT_MS = 600_000

function triggerBinaryDownload(b64: string, filename: string, mimeType: string) {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const blob = new Blob([bytes], { type: mimeType })
  const link = document.createElement("a")
  link.href = URL.createObjectURL(blob)
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(link.href)
}

function triggerPDFDownload(pdf: { base64: string; filename: string }) {
  triggerBinaryDownload(pdf.base64, pdf.filename, "application/pdf")
}

function triggerExcelDownload(excel: { base64: string; filename: string }) {
  triggerBinaryDownload(
    excel.base64,
    excel.filename,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  )
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatConvDate(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    const diffH = (Date.now() - date.getTime()) / 3_600_000
    if (diffH < 24) return date.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })
    if (diffH < 168) return date.toLocaleDateString("es-ES", { weekday: "short" })
    return date.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "2-digit" })
  } catch { return "" }
}

function makeWelcome(community: string): Message {
  return {
    id: 1,
    role: "ai",
    content: `Hola, soy el Auditor IA de ProFuturo. Ahora estamos analizando la comunidad: **${community}**. ¿En qué puedo ayudarte?`,
  }
}

export function AiChat() {
  const [inputValue, setInputValue] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [currentConversationId, setCurrentConversationId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState("")

  const { selectedCommunity } = useCommunity()
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (bottomRef.current && messages.length > 0) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages])

  useEffect(() => {
    setMessages([makeWelcome(selectedCommunity)])
    setCurrentConversationId(null)
    setSelectedFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ""
    fetchConversations(selectedCommunity)
  }, [selectedCommunity])

  useEffect(() => {
    const handleQuickAction = (event: Event) => {
      const action = (event as CustomEvent).detail
      const prompts: Record<string, string> = {
        auditoria: "Genera una auditoria de clima completa de la comunidad seleccionada analizando sentimientos y engagement",
        reporte: "Genera un reporte directivo mensual en PDF incluyendo metricas de participacion y KPIs principales",
        ranking: "Muestra el ranking de participacion de los usuarios mas activos con sus estadisticas",
      }
      if (prompts[action]) handleSendMessage(prompts[action])
    }
    window.addEventListener("quickAction", handleQuickAction)
    return () => window.removeEventListener("quickAction", handleQuickAction)
  }, [selectedCommunity])

  const fetchConversations = async (community: string) => {
    try {
      const res = await fetch(`${API_URL}/api/conversations/${encodeURIComponent(community)}`)
      if (res.ok) {
        const data = await res.json()
        setConversations(data.conversations || [])
      }
    } catch { /* conversations optional */ }
  }

  const handleLoadConversation = async (convId: string) => {
    try {
      const res = await fetch(`${API_URL}/api/conversations/${convId}/messages`)
      if (!res.ok) return
      const data = await res.json()
      const loaded: Message[] = (data.messages || []).map(
        (m: { role: string; content: string; files?: Array<{ name: string; type: string; size: number }> }, i: number) => ({
          id: i + 1,
          role: (m.role === "user" ? "user" : "ai") as "user" | "ai",
          content: m.content,
          files: m.files || undefined,
        })
      )
      setMessages(loaded.length > 0 ? loaded : [makeWelcome(selectedCommunity)])
      setCurrentConversationId(convId)
      setSidebarOpen(false)
    } catch { /* silent */ }
  }

  const handleNewConversation = () => {
    setCurrentConversationId(null)
    setMessages([makeWelcome(selectedCommunity)])
    setSelectedFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ""
    setSidebarOpen(false)
  }

  const handleDeleteConversation = async (id: string) => {
    if (!confirm("¿Eliminar esta conversación?")) return
    try {
      await fetch(`${API_URL}/api/conversations/${id}`, { method: "DELETE" })
      setConversations(prev => prev.filter(c => c.id !== id))
      if (currentConversationId === id) handleNewConversation()
    } catch { /* silent */ }
  }

  const handleRenameConversation = async (id: string, title: string) => {
    const trimmed = title.trim()
    if (!trimmed) return
    try {
      await fetch(`${API_URL}/api/conversations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: trimmed }),
      })
      setConversations(prev => prev.map(c => c.id === id ? { ...c, title: trimmed } : c))
      setEditingId(null)
    } catch { /* silent */ }
  }

  const appendAIMessage = (content: string, pdf?: Message["pdf"], excel?: Message["excel"]) => {
    setMessages(prev =>
      prev.filter(m => !m.loading).concat({ id: Date.now() + 2, role: "ai", content, pdf, excel })
    )
  }

  const handleSendMessage = async (customMessage?: string) => {
    const text = customMessage || inputValue.trim()
    if (!text) return

    const fileInfo = selectedFile
      ? [{ name: selectedFile.name, type: selectedFile.type, size: selectedFile.size }]
      : undefined

    setMessages(prev => [
      ...prev,
      { id: Date.now(), role: "user", content: text, files: fileInfo },
      { id: Date.now() + 1, role: "ai", content: "Procesando tu consulta...", loading: true },
    ])
    setInputValue("")
    const fileToSend = selectedFile
    setSelectedFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ""
    setIsLoading(true)

    const recentHistory = messages
      .filter(m => !m.loading && m.content && m.content.length > 5)
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }))

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)

    try {
      let response: Response
      const convId = currentConversationId

      if (fileToSend) {
        const formData = new FormData()
        formData.append("message", text)
        formData.append("community", selectedCommunity)
        formData.append("history_json", JSON.stringify(recentHistory))
        formData.append("file", fileToSend)
        if (convId) formData.append("conversation_id", convId)
        response = await fetch(`${API_URL}/api/chat-with-file`, {
          method: "POST",
          body: formData,
          signal: controller.signal,
        })
      } else {
        response = await fetch(`${API_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            community: selectedCommunity,
            history: recentHistory,
            conversation_id: convId,
            files: fileInfo,
          }),
          signal: controller.signal,
        })
      }

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      if (data.conversation_id) {
        if (!currentConversationId) setCurrentConversationId(data.conversation_id)
        fetchConversations(selectedCommunity)
      }

      const pdf = data.pdf?.base64 && data.pdf?.filename
        ? { base64: data.pdf.base64, filename: data.pdf.filename }
        : undefined
      const excel = data.excel?.base64 && data.excel?.filename
        ? { base64: data.excel.base64, filename: data.excel.filename }
        : undefined

      appendAIMessage(data.response || "Sin respuesta del servidor.", pdf, excel)
      if (pdf) triggerPDFDownload(pdf)
      if (excel) triggerExcelDownload(excel)
    } catch (error: unknown) {
      const isAbort = error instanceof Error && error.name === "AbortError"
      appendAIMessage(
        isAbort
          ? "La consulta superó el tiempo máximo (600s). Reintenta."
          : `Error al conectar con el servidor en ${API_URL}. Asegúrate de que el backend esté en ejecución.`
      )
    } finally {
      clearTimeout(timeout)
      setIsLoading(false)
    }
  }

  return (
    <Card className="relative flex h-[calc(100vh-5rem)] flex-col overflow-hidden border-border bg-card">

      {/* ── Sidebar overlay ─────────────────────────────────────────── */}
      {sidebarOpen && (
        <div
          className="absolute inset-0 z-40 bg-black/20 backdrop-blur-[1px]"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ── Conversations sidebar ────────────────────────────────────── */}
      <div
        className={`absolute inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-card shadow-xl transition-transform duration-300 ease-in-out ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Sidebar header */}
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <span className="text-sm font-semibold text-foreground">Conversaciones</span>
          <Button size="icon" variant="ghost" className="size-7 hover:bg-muted hover:text-foreground" onClick={() => setSidebarOpen(false)}>
            <X className="size-4" />
          </Button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto py-1">
          {conversations.length === 0 ? (
            <p className="px-4 py-8 text-center text-xs text-muted-foreground">
              Sin conversaciones guardadas
            </p>
          ) : (
            conversations.map(conv => (
              <div
                key={conv.id}
                className={`group flex cursor-pointer items-start gap-2 px-3 py-2.5 transition-colors hover:bg-muted/50 ${
                  currentConversationId === conv.id ? "bg-primary/10" : ""
                }`}
                onClick={() => editingId !== conv.id && handleLoadConversation(conv.id)}
              >
                <MessageSquare className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  {editingId === conv.id ? (
                    <div className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                      <Input
                        value={editingTitle}
                        onChange={e => setEditingTitle(e.target.value)}
                        className="h-6 px-1.5 text-xs"
                        onKeyDown={e => {
                          if (e.key === "Enter") handleRenameConversation(conv.id, editingTitle)
                          if (e.key === "Escape") setEditingId(null)
                        }}
                        autoFocus
                      />
                      <Button size="icon" variant="ghost" className="size-5 shrink-0 hover:bg-muted"
                        onClick={() => handleRenameConversation(conv.id, editingTitle)}>
                        <Check className="size-3 text-green-600" />
                      </Button>
                      <Button size="icon" variant="ghost" className="size-5 shrink-0 hover:bg-muted hover:text-foreground"
                        onClick={() => setEditingId(null)}>
                        <X className="size-3" />
                      </Button>
                    </div>
                  ) : (
                    <>
                      <p className="truncate text-xs font-medium text-foreground leading-snug">{conv.title}</p>
                      <p className="text-[10px] text-muted-foreground">{formatConvDate(conv.updated_at)}</p>
                    </>
                  )}
                </div>
                {editingId !== conv.id && (
                  <div
                    className="flex shrink-0 gap-0.5 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={e => e.stopPropagation()}
                  >
                    <Button size="icon" variant="ghost" className="size-5 hover:bg-muted hover:text-foreground"
                      onClick={() => { setEditingId(conv.id); setEditingTitle(conv.title) }}>
                      <Pencil className="size-2.5" />
                    </Button>
                    <Button size="icon" variant="ghost" className="size-5 hover:bg-muted"
                      onClick={() => handleDeleteConversation(conv.id)}>
                      <Trash2 className="size-2.5 text-destructive" />
                    </Button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Sidebar footer */}
        <div className="border-t border-border p-3">
          <Button variant="outline" size="sm" className="w-full gap-2 text-xs hover:bg-muted hover:text-foreground" onClick={handleNewConversation}>
            <Plus className="size-3.5" />
            Nueva conversación
          </Button>
        </div>
      </div>

      {/* ── Header ───────────────────────────────────────────────────── */}
      <CardHeader className="border-b border-border pb-4">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <div className="flex size-6 items-center justify-center rounded-md bg-primary">
            <Bot className="size-3.5 text-primary-foreground" />
          </div>
          Auditor IA Activo
          <div className="ml-auto flex items-center gap-0.5">
            <Button
              size="icon"
              variant="ghost"
              className="size-7 shrink-0 text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => setSidebarOpen(true)}
              title="Historial de conversaciones"
            >
              <Clock className="size-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="size-7 shrink-0 text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={handleNewConversation}
              title="Nueva conversación"
            >
              <Plus className="size-4" />
            </Button>
          </div>
        </CardTitle>
      </CardHeader>

      {/* ── Messages ─────────────────────────────────────────────────── */}
      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full px-4 py-4">
          <div className="flex max-w-full flex-col gap-4 overflow-x-hidden">
            {messages?.map(msg => (
              <div key={msg.id} className="flex flex-col gap-1">
                <div className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                  <Avatar className="mt-0.5 size-7 shrink-0">
                    <AvatarFallback
                      className={
                        msg.role === "ai"
                          ? "bg-primary text-[10px] font-bold text-primary-foreground"
                          : "bg-muted text-[10px] font-bold text-muted-foreground"
                      }
                    >
                      {msg.role === "ai" ? <Sparkles className="size-3.5" /> : "AD"}
                    </AvatarFallback>
                  </Avatar>
                  <div
                    className={`min-w-0 max-w-[85%] overflow-hidden rounded-xl px-3.5 py-2.5 ${
                      msg.role === "ai"
                        ? "bg-muted text-foreground"
                        : "bg-primary text-primary-foreground"
                    } ${msg.loading ? "animate-pulse" : ""}`}
                  >
                    {msg.loading || msg.role === "user" ? (
                      <p className="break-words text-sm leading-relaxed">{msg.content}</p>
                    ) : (
                      <div className="prose prose-sm w-full max-w-none break-words text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-p:my-1 prose-p:leading-normal prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-headings:mb-1 prose-headings:mt-3 prose-hr:my-3 prose-hr:border-foreground/30 prose-code:break-all prose-pre:text-xs prose-table:text-xs">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            table: ({ node: _n, ...props }) => (
                              <div className="my-2 overflow-x-auto rounded border border-border/40">
                                <table className="w-full text-xs" {...props} />
                              </div>
                            ),
                            pre: ({ node: _n, ...props }) => (
                              <pre className="max-w-full overflow-x-auto whitespace-pre-wrap text-xs" {...props} />
                            ),
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>

                {/* File attachment badges */}
                {msg.files && msg.files.length > 0 && (
                  <div className={`flex flex-wrap gap-1.5 ${msg.role === "user" ? "justify-end pr-10" : "pl-10"}`}>
                    {msg.files.map((f, i) => (
                      <span
                        key={i}
                        className="flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-[10px] text-muted-foreground"
                      >
                        <Paperclip className="size-2.5 shrink-0" />
                        <span className="max-w-[120px] truncate">{f.name}</span>
                        {f.size > 0 && (
                          <span className="text-muted-foreground/60">{formatFileSize(f.size)}</span>
                        )}
                      </span>
                    ))}
                  </div>
                )}

                {/* PDF / Excel download buttons */}
                {(msg?.pdf || msg?.excel) && (
                  <div className={`flex flex-wrap gap-2 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
                    <div className="size-7" />
                    {msg.pdf && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-2 text-xs"
                        onClick={() => msg.pdf && triggerPDFDownload(msg.pdf)}
                      >
                        <FileDown className="size-3.5" />
                        {msg.pdf.filename}
                      </Button>
                    )}
                    {msg.excel && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-2 text-xs text-green-700 border-green-300 hover:bg-muted"
                        onClick={() => msg.excel && triggerExcelDownload(msg.excel)}
                      >
                        <Table2 className="size-3.5" />
                        {msg.excel.filename}
                      </Button>
                    )}
                  </div>
                )}
              </div>
            )) || []}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      </CardContent>

      {/* ── Input ────────────────────────────────────────────────────── */}
      <CardFooter className="border-t border-border p-3">
        <div className="flex w-full flex-col gap-2">
          {selectedFile && (
            <div className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-xs">
              <Paperclip className="size-3.5 shrink-0" />
              <span className="flex-1 truncate text-muted-foreground">{selectedFile.name}</span>
              <Button
                size="icon"
                variant="ghost"
                className="size-5 shrink-0 hover:bg-muted hover:text-foreground"
                onClick={() => setSelectedFile(null)}
              >
                <X className="size-3" />
              </Button>
            </div>
          )}
          <div className="flex w-full items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.pdf"
              className="hidden"
              onChange={e => {
                const file = e.target.files?.[0]
                if (file) setSelectedFile(file)
              }}
            />
            <Button
              size="icon"
              variant="outline"
              className="shrink-0 border-border hover:bg-muted hover:text-foreground"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
            >
              <Paperclip className="size-4" />
            </Button>
            <Input
              placeholder="Escribe una consulta al Auditor IA..."
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  handleSendMessage()
                }
              }}
              disabled={isLoading}
              className="flex-1 border-border bg-secondary text-foreground placeholder:text-muted-foreground"
            />
            <Button
              size="icon"
              className="shrink-0 bg-primary text-primary-foreground hover:bg-primary/90"
              onClick={() => handleSendMessage()}
              disabled={isLoading || !inputValue.trim()}
            >
              <Send className="size-4" />
            </Button>
          </div>
        </div>
      </CardFooter>
    </Card>
  )
}
