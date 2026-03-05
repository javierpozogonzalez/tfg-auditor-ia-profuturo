"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { Card, CardHeader, CardTitle, CardAction, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Download, Share2 } from "lucide-react"
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
  const W = 560
  const H = 360
  const cx = W / 2
  const cy = H / 2

  edges.forEach(({ author, discussion, community, post_count }) => {
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
    const authorNode = nodeMap.get(author)!
    authorNode.weight += post_count

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
        const dist = Math.sqrt(dx * dx + dy * dy) || 1

        const spring = 0.02 * weight
        fx += dx * spring
        fy += dy * spring
      })

      
      const toCx = cx - n.x
      const toCy = cy - n.y
      fx += toCx * 0.003
      fy += toCy * 0.003

      n.x = Math.max(30, Math.min(W - 30, n.x + fx * 0.1))
      n.y = Math.max(20, Math.min(H - 20, n.y + fy * 0.1))
    })
  }

  return { nodes, links }
}

function downloadSVG(svgRef: React.RefObject<SVGSVGElement | null>) {
  if (!svgRef.current) return
  const serializer = new XMLSerializer()
  const source = serializer.serializeToString(svgRef.current)
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

export function InteractionGraph() {
  const { selectedCommunity } = useCommunity()
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [links, setLinks] = useState<LayoutEdge[]>([])
  const [rawEdges, setRawEdges] = useState<GraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
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

  const nodeMap = new Map(nodes.map((n) => [n.id, n]))
  const maxWeight = Math.max(...nodes.map((n) => n.weight), 1)

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
        <CardAction>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-xs text-muted-foreground hover:text-primary"
            onClick={() => downloadSVG(svgRef)}
            disabled={loading || nodes.length === 0}
          >
            <Download className="size-3.5" />
            Descargar
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
            viewBox="0 0 560 360"
            className="w-full flex-1"
            style={{ overflow: "visible" }}
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
              const color = COMMUNITY_COLORS[community] ?? "#94a3b8"
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
              const baseR = node.type === "discussion" ? 6 : 5
              const r = baseR + (node.weight / maxWeight) * 10
              const color = getNodeColor(node.type, community)
              return (
                <g key={node.id}>
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={r}
                    fill={color}
                    stroke={node.type === "discussion" ? "#94a3b8" : "white"}
                    strokeWidth={1}
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
                  >
                    {node.label}
                  </text>
                </g>
              )
            })}
          </svg>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-border pt-2">
          {Object.entries(COMMUNITY_COLORS).map(([name, color]) => (
            <span key={name} className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <span
                className="inline-block size-2.5 rounded-full"
                style={{ backgroundColor: color }}
              />
              {name.split(":")[0].trim()}
            </span>
          ))}
          <span className="ml-auto flex items-center gap-1 text-[10px] text-muted-foreground">
            <span className="inline-block size-2.5 rounded-full border border-slate-300 bg-slate-100" />
            Hilo de discusion
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
