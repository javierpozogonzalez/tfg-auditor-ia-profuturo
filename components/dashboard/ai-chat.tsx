"use client"

import { useState, useEffect, useRef } from "react"
import ReactMarkdown from "react-markdown"
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
import { Bot, Send, FileDown, Sparkles, CircleDot, Paperclip, X } from "lucide-react"
import { useCommunity } from "@/lib/community-context"

interface Message {
  id: number
  role: "ai" | "user"
  content: string
  loading?: boolean
  pdf?: { base64: string; filename: string }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const CHAT_TIMEOUT_MS = 600_000

function triggerPDFDownload(pdf: { base64: string; filename: string }) {
  const binary = atob(pdf.base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const blob = new Blob([bytes], { type: "application/pdf" })
  const link = document.createElement("a")
  link.href = URL.createObjectURL(blob)
  link.download = pdf.filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(link.href)
}

export function AiChat() {
  const [inputValue, setInputValue] = useState("")
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: "ai",
      content:
        "Hola, soy el Auditor IA de ProFuturo. Puedo ayudarte a analizar datos de las comunidades educativas, generar reportes y responder preguntas sobre la actividad en los foros. En que puedo asistirte?",
    },
  ])
  const [isLoading, setIsLoading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const { selectedCommunity } = useCommunity()
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (bottomRef.current && messages && messages.length > 0) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [messages])

  useEffect(() => {
    setMessages([{
      id: Date.now(),
      role: "ai",
      content: `Hola, soy el Auditor IA de ProFuturo. Ahora estamos analizando la comunidad: ${selectedCommunity}. ¿En qué puedo ayudarte?`,
    }])
    setSelectedFile(null)
  }, [selectedCommunity])

  useEffect(() => {
    const handleQuickAction = (event: Event) => {
      const action = (event as CustomEvent).detail
      const prompts: Record<string, string> = {
        auditoria:
          "Genera una auditoria de clima completa de la comunidad seleccionada analizando sentimientos y engagement",
        reporte:
          "Genera un reporte directivo mensual en PDF incluyendo metricas de participacion y KPIs principales",
        ranking:
          "Muestra el ranking de participacion de los usuarios mas activos con sus estadisticas",
      }
      if (prompts[action]) handleSendMessage(prompts[action])
    }
    window.addEventListener("quickAction", handleQuickAction)
    return () => window.removeEventListener("quickAction", handleQuickAction)
  }, [selectedCommunity])

  const appendAIMessage = (content: string, pdf?: Message["pdf"]) => {
    setMessages((prev) =>
      prev
        .filter((m) => !m.loading)
        .concat({ id: Date.now() + 2, role: "ai", content, pdf })
    )
  }

  const handleSendMessage = async (customMessage?: string) => {
    const text = customMessage || inputValue.trim()
    if (!text) return

    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "user", content: text },
      { id: Date.now() + 1, role: "ai", content: "Procesando tu consulta...", loading: true },
    ])
    setInputValue("")
    const fileToSend = selectedFile
    setSelectedFile(null)
    setIsLoading(true)

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS)

    try {
      let response: Response

      if (fileToSend) {
        const formData = new FormData()
        formData.append("message", text)
        formData.append("community", selectedCommunity)
        formData.append("file", fileToSend)

        response = await fetch(`${API_URL}/api/chat-with-file`, {
          method: "POST",
          body: formData,
          signal: controller.signal,
        })
      } else {
        response = await fetch(`${API_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, community: selectedCommunity }),
          signal: controller.signal,
        })
      }

      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()

      const pdf =
        data.pdf?.base64 && data.pdf?.filename
          ? { base64: data.pdf.base64, filename: data.pdf.filename }
          : undefined

      appendAIMessage(data.response || "Sin respuesta del servidor.", pdf)
      if (pdf) triggerPDFDownload(pdf)
    } catch (error: unknown) {
      const isAbort = error instanceof Error && error.name === "AbortError"
      appendAIMessage(
        isAbort
          ? "La consulta supero el tiempo maximo (600s). Reintenta."
          : `Error al conectar con el servidor en ${API_URL}. Asegurate de que el backend este en ejecucion.`
      )
    } finally {
      clearTimeout(timeout)
      setIsLoading(false)
    }
  }

  return (
    <Card className="flex h-[calc(100vh-5rem)] flex-col border-border bg-card">
      <CardHeader className="border-b border-border pb-4">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <div className="flex size-6 items-center justify-center rounded-md bg-primary">
            <Bot className="size-3.5 text-primary-foreground" />
          </div>
          Auditor IA Activo
          <span className="ml-auto flex items-center gap-1.5 text-xs font-normal text-[#22c55e]">
            <CircleDot className="size-3" />
            En linea
          </span>
        </CardTitle>
      </CardHeader>

      <CardContent className="flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full px-4 py-4">
          <div className="flex flex-col gap-4">
            {messages?.map((msg) => (
              <div key={msg.id} className="flex flex-col gap-2">
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
                    className={`max-w-[85%] rounded-xl px-3.5 py-2.5 ${msg.role === "ai"
                        ? "bg-muted text-foreground"
                        : "bg-primary text-primary-foreground"
                      } ${msg.loading ? "animate-pulse" : ""}`}
                  >
                    {msg.loading || msg.role === "user" ? (
                      <p className="text-sm leading-relaxed">{msg.content}</p>
                    ) : (
                      <div className="prose prose-sm max-w-none text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-p:leading-relaxed prose-ul:my-1 prose-li:my-0">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                </div>
                {msg?.pdf && (
                  <div className={`flex ${msg.role === "user" ? "flex-row-reverse" : "flex-row"} gap-3`}>
                    <div className="size-7" />
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-2 text-xs"
                      onClick={() => msg.pdf && triggerPDFDownload(msg.pdf)}
                    >
                      <FileDown className="size-3.5" />
                      Descargar {msg.pdf.filename}
                    </Button>
                  </div>
                )}
              </div>
            )) || []}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      </CardContent>

      <CardFooter className="border-t border-border p-3">
        <div className="flex w-full flex-col gap-2">
          {selectedFile && (
            <div className="flex items-center gap-2 rounded-md bg-muted px-3 py-2 text-xs">
              <Paperclip className="size-3.5" />
              <span className="flex-1 truncate text-muted-foreground">{selectedFile.name}</span>
              <Button
                size="icon"
                variant="ghost"
                className="size-5 shrink-0"
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
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) setSelectedFile(file)
              }}
            />
            <Button
              size="icon"
              variant="outline"
              className="shrink-0 border-border"
              onClick={() => fileInputRef.current?.click()}
              disabled={isLoading}
            >
              <Paperclip className="size-4" />
            </Button>
            <Input
              placeholder="Escribe una consulta al Auditor IA..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
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
