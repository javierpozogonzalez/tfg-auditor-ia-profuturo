"use client"

import { useState, FormEvent } from "react"
import { useAuth } from "@/lib/auth-context"

export function LoginPage() {
  const { login } = useAuth()
  const [user, setUser] = useState("")
  const [pass, setPass] = useState("")
  const [error, setError] = useState(false)

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    const ok = login(user, pass)
    if (!ok) setError(true)
  }

  return (
    <div className="flex h-screen w-full items-center justify-center bg-background">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8 shadow-lg">
        <div className="mb-8 text-center">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">
            Auditor IA ProFuturo
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Panel de administración
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="user" className="text-xs font-medium text-foreground/70 uppercase tracking-wider">
              Usuario
            </label>
            <input
              id="user"
              type="text"
              autoComplete="username"
              value={user}
              onChange={(e) => { setUser(e.target.value); setError(false) }}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="usuario"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="pass" className="text-xs font-medium text-foreground/70 uppercase tracking-wider">
              Contraseña
            </label>
            <input
              id="pass"
              type="password"
              autoComplete="current-password"
              value={pass}
              onChange={(e) => { setPass(e.target.value); setError(false) }}
              className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="text-xs text-destructive">
              Credenciales incorrectas.
            </p>
          )}

          <button
            type="submit"
            className="mt-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            Entrar
          </button>
        </form>
      </div>
    </div>
  )
}
