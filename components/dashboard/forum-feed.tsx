"use client"

import { useState, useEffect } from "react"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { MessageSquare } from "lucide-react"
import { useCommunity } from "@/lib/community-context"

interface ForumMessage {
  id: string
  author: string
  topic: string
  community: string
  excerpt: string
  time: string
  replies: number
  communityColor: string
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export function ForumFeed() {
  const { selectedCommunity } = useCommunity()
  const [messages, setMessages] = useState<ForumMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 300000)

    const fetchFeed = async () => {
      try {
        setLoading(true)
        setError(null)

        const response = await fetch(
          `${API_URL}/api/feed?community=${encodeURIComponent(selectedCommunity)}`,
          {
            method: "GET",
            headers: {
              "Content-Type": "application/json"
            },
            signal: controller.signal
          }
        )

        if (!response.ok) {
          throw new Error("Error al obtener el feed del foro")
        }

        const data = await response.json()

        if (data.success) {
          setMessages(data.messages)
        } else {
          setError(data.error || "Error desconocido")
          setMessages([])
        }
      } catch (err: any) {
        if (err.name === 'AbortError') {
          setError("La petición superó el tiempo máximo (300s). Por favor, reintenta.")
        } else {
          setError(err instanceof Error ? err.message : "Error desconocido")
        }
        setMessages([])
      } finally {
        setLoading(false)
        clearTimeout(timeoutId)
      }
    }

    fetchFeed()
    return () => {
      controller.abort()
      clearTimeout(timeoutId)
    }
  }, [selectedCommunity])

  if (loading) {
    return (
      <ScrollArea className="h-[calc(100vh-13rem)]">
        <div className="flex flex-col gap-3 pr-3 p-4">
          <div className="text-sm text-muted-foreground">Cargando feed...</div>
        </div>
      </ScrollArea>
    )
  }

  if (error) {
    return (
      <ScrollArea className="h-[calc(100vh-13rem)]">
        <div className="flex flex-col gap-3 pr-3 p-4">
          <div className="text-sm text-red-500">Error: {error}</div>
          <div className="text-xs text-muted-foreground">
            Asegurate de que el servidor backend esté ejecutándose en {API_URL}
          </div>
        </div>
      </ScrollArea>
    )
  }

  if (messages.length === 0) {
    return (
      <ScrollArea className="h-[calc(100vh-13rem)]">
        <div className="flex flex-col gap-3 pr-3 p-4">
          <div className="text-sm text-muted-foreground">
            No hay mensajes en esta comunidad
          </div>
        </div>
      </ScrollArea>
    )
  }

  return (
    <ScrollArea className="h-[calc(100vh-13rem)]">
      <div className="flex flex-col gap-3 pr-3">
        {messages.map((message) => (
          <Card
            key={message.id}
            className="gap-3 border-border bg-card p-4 transition-shadow hover:shadow-md"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-primary">
                    {message.author}
                  </span>
                  <Badge className={message.communityColor + " text-[10px]"}>
                    {message.community}
                  </Badge>
                </div>
                <h4 className="mb-1.5 text-sm font-bold text-foreground">
                  {message.topic}
                </h4>
                <p className="text-xs leading-relaxed text-muted-foreground">
                  {message.excerpt}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4 border-t border-border pt-2">
              <span className="text-[11px] text-muted-foreground">
                {message.time}
              </span>
              <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <MessageSquare className="size-3" />
                {message.replies} respuestas
              </div>
            </div>
          </Card>
        ))}
      </div>
    </ScrollArea>
  )
}
