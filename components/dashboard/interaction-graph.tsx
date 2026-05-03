"use client"

import { useState, useEffect, useRef, useCallback, useMemo } from "react"
import { Card, CardHeader, CardTitle, CardAction, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Download, Share2, FileDown } from "lucide-react"
import { useCommunity } from "@/lib/community-context"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

interface GraphEdge {
  author: string
  discussion: string
  community: string
  post_count: number
}

interface GraphNode {
  id: string
  label: string
  type: "author" | "discussion"
  weight: number
  x: number
  y: number
}

interface LayoutEdge {
  source: string
  target: string
  weight: number
}

const W = 560
const H = 360

const COMMUNITY_COLORS: Record<string, string> = {
  "ProFuturo Conecta: Coaches Plataforma Offline": "#3b82f6",
  "Red de Líderes Innovadores": "#a855f7",
  "Comunidad Pruebas TED": "#22c55e",
  "[VO] Creando Comunidades de Aprendizaje: Después del PLE ¿Qué? (Tutorizado)": "#f59e0b",
}

function getNodeColor(type: "author" | "discussion", community: string): string {
  if (type === "discussion") return "#e2e8f0"
  return COMMUNITY_COLORS[community] ?? "#6366f1"
}

function buildLayout(edges: GraphEdge[]): { nodes: GraphNode[]; links: LayoutEdge[] } {
  const nodeMap = new Map<string, GraphNode>()
  const links: LayoutEdge[] = []
  const cx = W / 2
  const cy = H / 2

  edges.forEach(({ author, discussion, post_count }) => {
    if (!nodeMap.has(author)) {
      nodeMap.set(author, {
        id: author,
        label: author.split(" ")[0],
        type: "author",
        weight: 0,
        x: cx + (Math.random() - 0.5) * W * 0.7,
        y: cy + (Math.random() - 0.5) * H * 0.7,
      })
    }
    nodeMap.get(author)!.weight += post_count

    const discKey = `disc:${discussion}`
    if (!nodeMap.has(discKey)) {
      nodeMap.set(discKey, {
        id: discKey,
        label: discussion.length > 20 ? discussion.slice(0, 18) + "…" : discussion,
        type: "discussion",
        weight: 0,
        x: cx + (Math.random() - 0.5) * W * 0.5,
        y: cy + (Math.random() - 0.5) * H * 0.5,
      })
    }
    nodeMap.get(discKey)!.weight += post_count
    links.push({ source: author, target: discKey, weight: post_count })
  })

  const nodes = Array.from(nodeMap.values())

  for (let iter = 0; iter < 200; iter++) {
    nodes.forEach((n) => {
      let fx = 0
      let fy = 0

      nodes.forEach((m) => {
        if (m.id === n.id) return
        const dx = n.x - m.x || 0.01
        const dy = n.y - m.y || 0.01
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const repulsion = 4500 / (dist * dist)
        fx += (dx / dist) * repulsion
        fy += (dy / dist) * repulsion
      })

      links.forEach(({ source, target, weight }) => {
        const other = source === n.id ? nodeMap.get(target) : target === n.id ? nodeMap.get(source) : null
        if (!other) return
        const dx = other.x - n.x
        const dy = other.y - n.y
        const spring = 0.02 * weight
        fx += dx * spring
        fy += dy * spring
      })

      fx += (cx - n.x) * 0.003
      fy += (cy - n.y) * 0.003

      n.x = Math.max(30, Math.min(W - 30, n.x + fx * 0.1))
      n.y = Math.max(20, Math.min(H - 20, n.y + fy * 0.1))
    })
  }

  return { nodes, links }
}

async function downloadSVG(svgRef: React.RefObject<SVGSVGElement | null>) {
  if (!svgRef.current) return

  let logoDataUrl: string | null = null
  try {
    const res = await fetch("/logo.png")
    const blob = await res.blob()
    logoDataUrl = await new Promise<string>((resolve) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.readAsDataURL(blob)
    })
  } catch { /* logo optional */ }

  const clone = svgRef.current.cloneNode(true) as SVGSVGElement

  if (logoDataUrl) {
    const ns = "http://www.w3.org/2000/svg"
    const logoImg = document.createElementNS(ns, "image")
    logoImg.setAttribute("href", logoDataUrl)
    logoImg.setAttribute("x", String(W - 95))
    logoImg.setAttribute("y", String(H - 28))
    logoImg.setAttribute("width", "82")
    logoImg.setAttribute("height", "25")
    logoImg.setAttribute("opacity", "0.14")
    logoImg.setAttribute("preserveAspectRatio", "xMidYMid meet")
    clone.appendChild(logoImg)
  }

  const serializer = new XMLSerializer()
  const source = serializer.serializeToString(clone)
  const blob = new Blob([source], { type: "image/svg+xml;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = "grafo_interacciones.svg"
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

async function exportGraphPDF(
  svgRef: React.RefObject<SVGSVGElement | null>,
  stats: { totalUsers: number; totalPosts: number; totalDiscussions: number; topConnectors: string[] },
  community: string
) {
  if (!svgRef.current) return
  const { jsPDF } = await import("jspdf")

  // Fetch ProFuturo logo for header
  let logoData: string | null = null
  try {
    const res = await fetch("/logo.png")
    const blob = await res.blob()
    logoData = await new Promise<string>((resolve) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.readAsDataURL(blob)
    })
  } catch { /* logo optional */ }

  const serializer = new XMLSerializer()
  const svgStr = serializer.serializeToString(svgRef.current)
  const svgBlob = new Blob([svgStr], { type: "image/svg+xml;charset=utf-8" })
  const url = URL.createObjectURL(svgBlob)

  await new Promise<void>((resolve) => {
    const img = new Image()
    img.onload = () => {
      const canvas = document.createElement("canvas")
      canvas.width  = 1680
      canvas.height = 1080
      const ctx = canvas.getContext("2d")!
      ctx.fillStyle = "#ffffff"
      ctx.fillRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
      const imgData = canvas.toDataURL("image/png")

      const pdf = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" })
      const PW = 297
      const PH = 210
      const BLUE = [0, 48, 135] as const
      const CYAN = [0, 174, 239] as const
      const DARK = [26, 26, 46] as const
      const GREY = [136, 136, 136] as const

      const now = new Date()
      const dateStr = now.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" })
      const timeStr = now.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" })

      const drawHeader = (subtitle: string) => {
        if (logoData) pdf.addImage(logoData, "PNG", 12, 2, 30, 12)
        pdf.setDrawColor(...BLUE)
        pdf.setLineWidth(1.5)
        pdf.line(12, 16, PW - 12, 16)
        pdf.setFontSize(8.5)
        pdf.setTextColor(...GREY)
        pdf.setFont("helvetica", "normal")
        pdf.text(subtitle, PW - 12, 9, { align: "right" })
      }

      const drawFooter = (pageNum: number) => {
        pdf.setDrawColor(208, 223, 240)
        pdf.setLineWidth(0.5)
        pdf.line(12, PH - 13, PW - 12, PH - 13)
        pdf.setFontSize(7.5)
        pdf.setTextColor(...GREY)
        pdf.setFont("helvetica", "normal")
        pdf.text(
          `Generado: ${dateStr} ${timeStr}  |  Confidencial — Solo uso interno`,
          12, PH - 8
        )
        pdf.text(`Pagina ${pageNum}`, PW - 12, PH - 8, { align: "right" })
      }

      // ── PAGE 1: graph ─────────────────────────────────────────────
      drawHeader(`Grafo de Interacciones  |  ${community}`)
      pdf.addImage(imgData, "PNG", 12, 20, PW - 24, PH - 38)
      drawFooter(1)

      // ── PAGE 2: stats ─────────────────────────────────────────────
      pdf.addPage()
      drawHeader(`Estadisticas  |  ${community}`)

      // Section title
      pdf.setFontSize(12)
      pdf.setTextColor(...BLUE)
      pdf.setFont("helvetica", "bold")
      pdf.text("Estadisticas del Grafo de Interacciones", 12, 24)
      pdf.setDrawColor(...CYAN)
      pdf.setLineWidth(0.4)
      pdf.line(12, 26, PW - 12, 26)

      // Description box
      pdf.setFillColor(235, 243, 255)
      pdf.setDrawColor(...CYAN)
      pdf.setLineWidth(0.4)
      pdf.roundedRect(12, 29, PW - 24, 17, 2, 2, "FD")
      pdf.setFontSize(8.5)
      pdf.setTextColor(...DARK)
      pdf.setFont("helvetica", "italic")
      const desc =
        `Este grafo representa las interacciones entre los miembros del foro y los hilos de discusion de la comunidad "${community}". ` +
        `Cada nodo de color identifica a un autor; los nodos grises representan hilos de debate. ` +
        `El grosor de las aristas refleja el numero de publicaciones por conexion.`
      const descLines = pdf.splitTextToSize(desc, PW - 32)
      pdf.text(descLines, 18, 35)

      // KPI cards
      const cards = [
        { label: "Usuarios unicos",     value: String(stats.totalUsers) },
        { label: "Publicaciones",       value: String(stats.totalPosts) },
        { label: "Hilos de discusion",  value: String(stats.totalDiscussions) },
        { label: "Media posts/usuario", value: stats.totalUsers > 0 ? (stats.totalPosts / stats.totalUsers).toFixed(1) : "0" },
      ]
      const cardW = (PW - 24 - 9) / 4
      cards.forEach((card, i) => {
        const cx = 12 + i * (cardW + 3)
        pdf.setFillColor(255, 255, 255)
        pdf.setDrawColor(210, 223, 240)
        pdf.setLineWidth(0.3)
        pdf.roundedRect(cx, 50, cardW, 22, 2, 2, "FD")
        pdf.setFontSize(17)
        pdf.setTextColor(...CYAN)
        pdf.setFont("helvetica", "bold")
        pdf.text(card.value, cx + cardW / 2, 63, { align: "center" })
        pdf.setFontSize(8)
        pdf.setTextColor(...GREY)
        pdf.setFont("helvetica", "normal")
        pdf.text(card.label, cx + cardW / 2, 69, { align: "center" })
      })

      // Top connectors table
      const tableTop = 82
      pdf.setFontSize(10)
      pdf.setTextColor(...BLUE)
      pdf.setFont("helvetica", "bold")
      pdf.text("Usuarios mas activos", 12, tableTop)
      pdf.setDrawColor(...CYAN)
      pdf.setLineWidth(0.4)
      pdf.line(12, tableTop + 2, 100, tableTop + 2)

      const tCols = [12, 60, 130, 190]
      const tableHeaders = ["Posicion", "Usuario", "Publicaciones (estimado)", "Rol detectado"]
      pdf.setFillColor(...BLUE)
      pdf.rect(12, tableTop + 5, PW - 24, 8, "F")
      pdf.setFontSize(8.5)
      pdf.setTextColor(255, 255, 255)
      pdf.setFont("helvetica", "bold")
      tableHeaders.forEach((h, i) => pdf.text(h, tCols[i] + 2, tableTop + 10))

      const medals = ["1ro", "2do", "3ro", "4to", "5to"]
      stats.topConnectors.forEach((name, idx) => {
        const rowY = tableTop + 14 + idx * 9
        pdf.setFillColor(idx % 2 === 0 ? 245 : 255, idx % 2 === 0 ? 248 : 255, idx % 2 === 0 ? 252 : 255)
        pdf.rect(12, rowY - 1, PW - 24, 9, "F")
        pdf.setFontSize(8.5)
        pdf.setTextColor(...DARK)
        pdf.setFont("helvetica", "normal")
        pdf.text(medals[idx] ?? `${idx + 1}`, tCols[0] + 2, rowY + 5)
        pdf.text(name, tCols[1] + 2, rowY + 5)
        pdf.text("—", tCols[2] + 2, rowY + 5)
        pdf.text(idx === 0 ? "Lider" : idx <= 2 ? "Experto" : "Conector", tCols[3] + 2, rowY + 5)
        pdf.setDrawColor(220, 230, 245)
        pdf.setLineWidth(0.2)
        pdf.line(12, rowY + 8, PW - 12, rowY + 8)
      })

      drawFooter(2)
      pdf.save("grafo_interacciones_profuturo.pdf")
      URL.revokeObjectURL(url)
      resolve()
    }
    img.src = url
  })
}

export function InteractionGraph() {
  const { selectedCommunity } = useCommunity()
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [links, setLinks] = useState<LayoutEdge[]>([])
  const [rawEdges, setRawEdges] = useState<GraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exportingPDF, setExportingPDF] = useState(false)
  const [dragId, setDragId] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const loadGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 15_000)
    try {
      const res = await fetch(
        `${API_URL}/api/graph?community=${encodeURIComponent(selectedCommunity)}`,
        { signal: controller.signal }
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const edges: GraphEdge[] = data.edges ?? []
      setRawEdges(edges)
      const layout = buildLayout(edges)
      setNodes(layout.nodes)
      setLinks(layout.links)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error desconocido")
    } finally {
      clearTimeout(timeout)
      setLoading(false)
    }
  }, [selectedCommunity])

  useEffect(() => { loadGraph() }, [loadGraph])

  // Stats computed from rawEdges (no extra API call needed)
  const stats = useMemo(() => {
    const authors     = new Set(rawEdges.map((e) => e.author))
    const discussions = new Set(rawEdges.map((e) => e.discussion))
    const totalPosts  = rawEdges.reduce((s, e) => s + e.post_count, 0)
    const authorPosts = new Map<string, number>()
    rawEdges.forEach((e) => authorPosts.set(e.author, (authorPosts.get(e.author) ?? 0) + e.post_count))
    const topConnectors = [...authorPosts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name]) => name.split(" ")[0])
    return {
      totalUsers: authors.size,
      totalDiscussions: discussions.size,
      totalPosts,
      topConnectors,
    }
  }, [rawEdges])

  // Drag handlers (SVG coordinate space)
  const getSVGCoords = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current!.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width)  * W,
      y: ((e.clientY - rect.top)  / rect.height) * H,
    }
  }

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!dragId) return
    const { x, y } = getSVGCoords(e)
    setNodes((prev) =>
      prev.map((n) =>
        n.id === dragId
          ? { ...n, x: Math.max(20, Math.min(W - 20, x)), y: Math.max(15, Math.min(H - 15, y)) }
          : n
      )
    )
  }

  const nodeMap    = new Map(nodes.map((n) => [n.id, n]))
  const maxWeight  = Math.max(...nodes.map((n) => n.weight), 1)

  const edgeCommunityMap = new Map<string, string>()
  rawEdges.forEach(({ author, discussion, community }) => {
    edgeCommunityMap.set(`${author}|disc:${discussion}`, community)
  })

  return (
    <Card className="flex h-[calc(100vh-13rem)] flex-col border-border bg-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Share2 className="size-4 text-primary" />
          Grafo de Interacciones
        </CardTitle>
        <CardAction className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-xs text-muted-foreground hover:text-primary"
            onClick={() => { downloadSVG(svgRef) }}
            disabled={loading || nodes.length === 0}
          >
            <Download className="size-3.5" />
            SVG
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-xs text-muted-foreground hover:text-primary"
            onClick={async () => {
              setExportingPDF(true)
              try { await exportGraphPDF(svgRef, stats, selectedCommunity) } finally { setExportingPDF(false) }
            }}
            disabled={loading || nodes.length === 0 || exportingPDF}
          >
            <FileDown className="size-3.5" />
            {exportingPDF ? "Generando…" : "PDF"}
          </Button>
        </CardAction>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col overflow-hidden p-3">
        {loading && (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            Cargando grafo...
          </div>
        )}
        {error && (
          <div className="flex flex-1 items-center justify-center text-sm text-red-500">
            Error: {error}
          </div>
        )}
        {!loading && !error && nodes.length === 0 && (
          <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
            Sin datos para esta comunidad.
          </div>
        )}
        {!loading && !error && nodes.length > 0 && (
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            className="w-full flex-1 cursor-grab active:cursor-grabbing"
            style={{ overflow: "visible" }}
            onPointerMove={handlePointerMove}
            onPointerUp={() => setDragId(null)}
            onPointerLeave={() => setDragId(null)}
          >
            <defs>
              <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6 Z" fill="#cbd5e1" />
              </marker>
            </defs>

            {links.map((link, i) => {
              const src = nodeMap.get(link.source)
              const tgt = nodeMap.get(link.target)
              if (!src || !tgt) return null
              const community = edgeCommunityMap.get(`${link.source}|${link.target}`) ?? ""
              const color   = COMMUNITY_COLORS[community] ?? "#94a3b8"
              const opacity = 0.15 + (link.weight / maxWeight) * 0.45
              return (
                <line
                  key={i}
                  x1={src.x} y1={src.y}
                  x2={tgt.x} y2={tgt.y}
                  stroke={color}
                  strokeWidth={1 + (link.weight / maxWeight) * 2}
                  opacity={opacity}
                />
              )
            })}

            {nodes.map((node) => {
              const community = rawEdges.find((e) => e.author === node.id)?.community ?? ""
              const baseR  = node.type === "discussion" ? 6 : 5
              const r      = baseR + (node.weight / maxWeight) * 10
              const color  = getNodeColor(node.type, community)
              const isDrag = dragId === node.id
              return (
                <g
                  key={node.id}
                  style={{ cursor: isDrag ? "grabbing" : "grab" }}
                  onPointerDown={(e) => {
                    e.currentTarget.setPointerCapture(e.pointerId)
                    setDragId(node.id)
                  }}
                >
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={r + (isDrag ? 2 : 0)}
                    fill={color}
                    stroke={isDrag ? "#003087" : node.type === "discussion" ? "#94a3b8" : "white"}
                    strokeWidth={isDrag ? 2 : 1}
                    opacity={node.type === "discussion" ? 0.7 : 0.9}
                  />
                  <text
                    x={node.x}
                    y={node.y - r - 3}
                    textAnchor="middle"
                    fill="#64748b"
                    fontSize={node.type === "discussion" ? 7 : 8}
                    fontFamily="sans-serif"
                    fontWeight={node.type === "author" ? "600" : "400"}
                    style={{ pointerEvents: "none", userSelect: "none" }}
                  >
                    {node.label}
                  </text>
                </g>
              )
            })}
          </svg>
        )}

        {/* Leyenda de colores */}
        <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-border pt-2">
          {Object.entries(COMMUNITY_COLORS).map(([name, color]) => (
            <span key={name} className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <span className="inline-block size-2.5 rounded-full" style={{ backgroundColor: color }} />
              {name.split(":")[0].trim()}
            </span>
          ))}
          <span className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground">
            <span className="inline-block size-2.5 rounded-full border border-slate-300 bg-slate-100" />
            Hilo de discusion
          </span>
        </div>

        {/* Panel de estadísticas */}
        {!loading && !error && stats.totalUsers > 0 && (
          <div className="mt-2 rounded-lg border border-border bg-muted/40 px-3 py-2">
            <p className="mb-1.5 text-[11px] font-semibold text-foreground">Estadisticas del grafo</p>
            <div className="grid grid-cols-4 gap-2 text-center">
              {[
                { label: "Usuarios", value: stats.totalUsers },
                { label: "Publicaciones", value: stats.totalPosts },
                { label: "Hilos", value: stats.totalDiscussions },
                { label: "Media posts/user", value: stats.totalUsers > 0 ? (stats.totalPosts / stats.totalUsers).toFixed(1) : 0 },
              ].map(({ label, value }) => (
                <div key={label} className="flex flex-col">
                  <span className="text-sm font-bold text-primary">{value}</span>
                  <span className="text-[9px] text-muted-foreground">{label}</span>
                </div>
              ))}
            </div>
            {stats.topConnectors.length > 0 && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                <span className="text-[9px] text-muted-foreground">Mas activos:</span>
                {stats.topConnectors.map((name, i) => (
                  <span key={`${name}-${i}`} className="rounded bg-primary/10 px-1.5 py-0.5 text-[9px] font-medium text-primary">
                    {name}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
