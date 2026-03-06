"use client"

import { useState, useEffect } from "react"
import { ShieldCheck, FileBarChart, Trophy } from "lucide-react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { useCommunity } from "@/lib/community-context"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export function DashboardSidebar() {
  const { selectedCommunity, setSelectedCommunity } = useCommunity()
  const [communities, setCommunities] = useState<string[]>([])

  useEffect(() => {
    fetch(`${API_URL}/api/communities`)
      .then((res) => res.json())
      .then((data) => {
        if (Array.isArray(data.communities)) {
          setCommunities(data.communities)
        }
      })
      .catch(() => setCommunities([]))
  }, [])

  const handleQuickAction = (action: string) => {
    window.dispatchEvent(new CustomEvent("quickAction", { detail: action }))
  }

  return (
    <aside className="flex h-screen w-72 flex-col bg-sidebar text-sidebar-foreground">
      <Separator className="bg-sidebar-border" />

      <div className="px-5 py-5">
        <label className="mb-2 block text-xs font-medium uppercase tracking-wider text-sidebar-foreground/70">
          Filtrar por Comunidad
        </label>
        <Select value={selectedCommunity} onValueChange={setSelectedCommunity}>
          <SelectTrigger className="w-full border-sidebar-border bg-sidebar-accent text-sidebar-foreground hover:bg-sidebar-accent/80">
            <SelectValue placeholder="Seleccionar comunidad" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todas">Todas las Comunidades</SelectItem>
            {communities.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Separator className="bg-sidebar-border" />

      <div className="flex flex-1 flex-col gap-2 px-5 py-5">
        <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-sidebar-foreground/70">
          Acciones Rapidas
        </label>
        <Button
          variant="ghost"
          className="justify-start gap-3 text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground"
          onClick={() => handleQuickAction("auditoria")}
        >
          <ShieldCheck className="size-4" />
          <span className="text-sm">Auditoria de Clima</span>
        </Button>
        <Button
          variant="ghost"
          className="justify-start gap-3 text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground"
          onClick={() => handleQuickAction("reporte")}
        >
          <FileBarChart className="size-4" />
          <span className="text-sm">Reporte Directivo Mensual</span>
        </Button>
        <Button
          variant="ghost"
          className="justify-start gap-3 text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground"
          onClick={() => handleQuickAction("ranking")}
        >
          <Trophy className="size-4" />
          <span className="text-sm">Ranking de Participacion</span>
        </Button>
      </div>

      <Separator className="bg-sidebar-border" />
    </aside>
  )
}
