"use client"

import { DashboardSidebar } from "@/components/dashboard/sidebar"
import { DataPanel } from "@/components/dashboard/data-panel"
import { AiChat } from "@/components/dashboard/ai-chat"
import { CommunityProvider } from "@/lib/community-context"

export default function DashboardPage() {
  return (
    <CommunityProvider>
      <div className="flex h-screen w-full overflow-hidden bg-background">
        <DashboardSidebar />

        <main className="flex flex-1 gap-5 overflow-hidden p-5">
          <section className="flex-1 overflow-hidden" aria-label="Datos y Visualizacion">
            <DataPanel />
          </section>

          <section className="w-[420px] shrink-0" aria-label="Asistente IA">
            <AiChat />
          </section>
        </main>
      </div>
    </CommunityProvider>
  )
}
