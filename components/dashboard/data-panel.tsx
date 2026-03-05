"use client"

import { useState } from "react"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ForumFeed } from "./forum-feed"
import { InteractionGraph } from "./interaction-graph"
import { MessageSquare, Share2 } from "lucide-react"

export function DataPanel() {
  const [activeTab, setActiveTab] = useState("feed")

  return (
    <Tabs value={activeTab} onValueChange={setActiveTab} className="flex h-full flex-col">
      <TabsList className="w-fit bg-muted">
        <TabsTrigger value="feed" className="gap-1.5 text-xs">
          <MessageSquare className="size-3.5" />
          Feed del Foro
        </TabsTrigger>
        <TabsTrigger value="grafo" className="gap-1.5 text-xs">
          <Share2 className="size-3.5" />
          Grafo de Interacciones
        </TabsTrigger>
      </TabsList>
      <div className="mt-3 flex-1 overflow-hidden">
        <div className={activeTab === "feed" ? "block h-full" : "hidden"}>
          <ForumFeed />
        </div>
        <div className={activeTab === "grafo" ? "block h-full" : "hidden"}>
          <InteractionGraph />
        </div>
      </div>
    </Tabs>
  )
}
