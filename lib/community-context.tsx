"use client"

import { createContext, useContext, useState, ReactNode } from "react"

interface CommunityContextType {
  selectedCommunity: string
  setSelectedCommunity: (community: string) => void
}

const CommunityContext = createContext<CommunityContextType | undefined>(undefined)

export function CommunityProvider({ children }: { children: ReactNode }) {
  const [selectedCommunity, setSelectedCommunity] = useState("todas")

  return (
    <CommunityContext.Provider value={{ selectedCommunity, setSelectedCommunity }}>
      {children}
    </CommunityContext.Provider>
  )
}

export function useCommunity() {
  const context = useContext(CommunityContext)
  if (!context) {
    throw new Error("useCommunity must be used within CommunityProvider")
  }
  return context
}
