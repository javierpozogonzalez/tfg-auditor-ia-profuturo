"use client"

import { createContext, useContext, useState, useEffect, ReactNode } from "react"

interface AuthContextType {
  isAuthenticated: boolean
  login: (user: string, pass: string) => boolean
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const VALID_USERS: Record<string, string> = {
  admin:      "adminProFuturo",
  aonia:      "aonia1234",
  formacion:  "formacion1234",
}
const STORAGE_KEY = "profuturo_auth"

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false)

  useEffect(() => {
    if (localStorage.getItem(STORAGE_KEY) === "1") {
      setIsAuthenticated(true)
    }
  }, [])

  const login = (user: string, pass: string): boolean => {
    if (VALID_USERS[user] === pass) {
      localStorage.setItem(STORAGE_KEY, "1")
      setIsAuthenticated(true)
      return true
    }
    return false
  }

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY)
    setIsAuthenticated(false)
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within AuthProvider")
  return context
}
