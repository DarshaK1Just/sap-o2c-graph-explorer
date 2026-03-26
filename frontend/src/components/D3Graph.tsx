import * as d3 from 'd3'
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'

export type NodeKey = { type: string; id: string }

export type GraphNode = {
  key: string
  type: string
  id: string
  label: string
  group: string
  metadata: Record<string, unknown>
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number | null
  fy?: number | null
}

export type GraphEdge = {
  key: string
  source: string
  target: string
  rel: string
  isCore: boolean
}

type Props = {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedKey: string | null
  showGranular: boolean
  onSelectNode: (key: string | null) => void
  onExpandNode: (key: string) => void
  onHoverNode: (key: string | null, clientX: number, clientY: number) => void
}

function colorForGroup(group: string) {
  switch (group) {
    case 'finance':
      return '#ef4444'
    case 'billing':
      return '#38bdf8'
    case 'delivery':
      return '#0ea5e9'
    case 'order':
      return '#2563eb'
    case 'customer':
      return '#3b82f6'
    case 'product':
      return '#1d4ed8'
    case 'plant':
      return '#0f766e'
    default:
      return '#60a5fa'
  }
}

export type D3GraphHandle = {
  zoomIn: () => void
  zoomOut: () => void
  fit: () => void
}

export const D3Graph = forwardRef<D3GraphHandle, Props>((props, ref) => {
  const { nodes, edges, selectedKey, showGranular, onSelectNode, onExpandNode, onHoverNode } = props
  const [hoveredKey, setHoveredKey] = useState<string | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const gRef = useRef<SVGGElement | null>(null)
  const simRef = useRef<d3.Simulation<GraphNode, GraphEdge> | null>(null)
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const currentTransform = useRef<d3.ZoomTransform>(d3.zoomIdentity)

  const filteredEdges = useMemo(() => {
    if (showGranular) return edges
    return edges.filter((e) => e.isCore)
  }, [edges, showGranular])

  const neighborsMap = useMemo(() => {
    const map = new Map<string, Set<string>>()
    for (const edge of filteredEdges) {
      if (!map.has(edge.source)) map.set(edge.source, new Set())
      if (!map.has(edge.target)) map.set(edge.target, new Set())
      map.get(edge.source)?.add(edge.target)
      map.get(edge.target)?.add(edge.source)
    }
    return map
  }, [filteredEdges])

  useEffect(() => {
    if (!svgRef.current) return
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()

    const g = svg.append('g').attr('class', 'viewport')
    gRef.current = g.node()

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 3])
      .on('zoom', (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        currentTransform.current = event.transform
        g.attr('transform', event.transform.toString())
      })
    zoomBehaviorRef.current = zoom
    svg.call(zoom as any)

    // Click on blank background to clear selection (hide inspector), double-click background to center/fit.
    svg.on('click', (event: any) => {
      const target = event.target as HTMLElement
      if (target.closest('.node') == null) {
        onSelectNode(null)
      }
    })

    svg.on('dblclick', () => {
      const { width, height } = svgRef.current!.getBoundingClientRect()
      svg.transition().duration(250).call(zoom.transform as any, d3.zoomIdentity.translate(width / 2, height / 2).scale(1))
    })
  }, [])

  useEffect(() => {
    if (!svgRef.current || !gRef.current) return
    const svg = d3.select(svgRef.current)
    const g = d3.select(gRef.current)

    // Join edges
    const linkSel = g
      .selectAll<SVGLineElement, GraphEdge>('line.link')
      .data(filteredEdges, (d: any) => d.key)
      .join('line')
      .attr('class', 'link')
      .attr('stroke', '#93c5fd')
      .attr('stroke-opacity', 0.55)
      .attr('stroke-width', (d) => (d.isCore ? 1.4 : 1))
      .classed('highlighted', (d: any) => Boolean(hoveredKey && (d.source === hoveredKey || d.target === hoveredKey)))
      .classed('faded', (d: any) => Boolean(hoveredKey && !(d.source === hoveredKey || d.target === hoveredKey)))

    // Join nodes
    const nodeSel = g
      .selectAll<SVGCircleElement, GraphNode>('circle.node')
      .data(nodes, (d: any) => d.key)
      .join('circle')
      .attr('class', 'node')
      .attr('r', (d) => (d.key === selectedKey ? 8 : d.key === hoveredKey ? 7 : 4.5))
      .attr('fill', (d) => colorForGroup(d.group))
      .attr('stroke', '#ffffff')
      .attr('stroke-width', (d) => (d.key === hoveredKey ? 2.2 : 1.2))
      .style('cursor', 'pointer')
      .classed('dimmed', (d) =>
        Boolean(
          hoveredKey &&
            d.key !== hoveredKey &&
            !neighborsMap.get(hoveredKey)?.has(d.key) &&
            !neighborsMap.get(d.key)?.has(hoveredKey),
        ),
      )
      .on('mouseenter', (event: MouseEvent, d: GraphNode) => {
        setHoveredKey(d.key)
        onHoverNode(d.key, event.clientX, event.clientY)
      })
      .on('mousemove', (event: MouseEvent, d: GraphNode) => onHoverNode(d.key, event.clientX, event.clientY))
      .on('mouseleave', (event: MouseEvent) => {
        setHoveredKey(null)
        onHoverNode(null, event.clientX, event.clientY)
      })
      .on('click', (event: MouseEvent, d: GraphNode) => {
        event.stopPropagation()
        onSelectNode(d.key)
      })
      .on('dblclick', (event: MouseEvent, d: GraphNode) => {
        event.stopPropagation()
        onExpandNode(d.key)
      })

    // Labels: only for selected node + hovered node is handled by tooltip outside.
    const labelData = nodes.filter((n) => n.key === selectedKey)
    const labelSel = g
      .selectAll<SVGTextElement, GraphNode>('text.label')
      .data(labelData, (d: any) => d.key)
      .join('text')
      .attr('class', 'label')
      .text((d) => d.label)
      .attr('font-size', 11)
      .attr('font-weight', 700)
      .attr('fill', '#0f172a')
      .attr('paint-order', 'stroke')
      .attr('stroke', '#ffffff')
      .attr('stroke-width', 4)

    // Simulation
    const sim =
      simRef.current ??
      d3
        .forceSimulation<GraphNode>(nodes)
        .force(
          'link',
          d3
            .forceLink<GraphNode, any>(filteredEdges as any)
            .id((d: any) => d.key)
            .distance((d: any) => (d.isCore ? 70 : 50))
            .strength((d: any) => (d.isCore ? 0.6 : 0.4)),
        )
        .force('charge', d3.forceManyBody().strength(-95))
        .force('center', d3.forceCenter(0, 0))
        .force('x', d3.forceX(0).strength(0.05))
        .force('y', d3.forceY(0).strength(0.05))
        .force('collide', d3.forceCollide<GraphNode>().radius(14))
        .alpha(1)

    simRef.current = sim
    sim.nodes(nodes)
    ;(sim.force('link') as any)?.links(filteredEdges)

    const dragHandler = d3
      .drag<SVGCircleElement, GraphNode>()
      .on('start', (event, d) => {
        if (!event.active) sim.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) sim.alphaTarget(0)
        d.fx = null
        d.fy = null
      })

    nodeSel.call(dragHandler)

    const nodePosition = (p: any) => {
      if (!p) return { x: 0, y: 0 }
      return typeof p === 'string' ? { x: 0, y: 0 } : { x: p.x ?? 0, y: p.y ?? 0 }
    }

    sim.on('tick', () => {
      linkSel
        .attr('x1', (d: any) => nodePosition(d.source).x)
        .attr('y1', (d: any) => nodePosition(d.source).y)
        .attr('x2', (d: any) => nodePosition(d.target).x)
        .attr('y2', (d: any) => nodePosition(d.target).y)

      nodeSel.attr('cx', (d) => d.x ?? 0).attr('cy', (d) => d.y ?? 0)

      labelSel.attr('x', (d) => (d.x ?? 0) + 10).attr('y', (d) => (d.y ?? 0) - 10)
    })

    // Initial framing: keep graph centered in viewport.
    const bbox = (gRef.current as SVGGElement).getBBox()
    const { width, height } = svgRef.current.getBoundingClientRect()
    if (bbox.width > 0 && bbox.height > 0) {
      const scale = Math.min(1.2, Math.max(0.2, 0.9 * Math.min(width / bbox.width, height / bbox.height)))
      const tx = width / 2 - scale * (bbox.x + bbox.width / 2)
      const ty = height / 2 - scale * (bbox.y + bbox.height / 2)
      const t = d3.zoomIdentity.translate(tx, ty).scale(scale)
      svg
        .transition()
        .duration(250)
        .call((zoomBehaviorRef.current as any).transform, t)
      currentTransform.current = t
    }

    // Restart a bit on data change.
    sim.alpha(0.8).restart()

    return () => {
      // keep sim for reuse, but remove tick handler
      sim.on('tick', null)
    }
  }, [nodes, filteredEdges, selectedKey, onSelectNode, onExpandNode, onHoverNode])

  useImperativeHandle(ref, () => ({
    zoomIn: () => {
      if (!svgRef.current || !zoomBehaviorRef.current) return
      d3.select(svgRef.current).transition().duration(250).call((zoomBehaviorRef.current as any).scaleBy, 1.08)
    },
    zoomOut: () => {
      if (!svgRef.current || !zoomBehaviorRef.current) return
      d3.select(svgRef.current).transition().duration(250).call((zoomBehaviorRef.current as any).scaleBy, 0.92)
    },
    fit: () => {
      if (!svgRef.current || !gRef.current || !zoomBehaviorRef.current) return
      const bbox = (gRef.current as SVGGElement).getBBox()
      const { width, height } = svgRef.current.getBoundingClientRect()
      if (bbox.width <= 0 || bbox.height <= 0) return
      const scale = Math.min(2, Math.max(0.15, 0.9 * Math.min(width / bbox.width, height / bbox.height)))
      const tx = width / 2 - scale * (bbox.x + bbox.width / 2)
      const ty = height / 2 - scale * (bbox.y + bbox.height / 2)
      const t = d3.zoomIdentity.translate(tx, ty).scale(scale)
      d3.select(svgRef.current).transition().duration(250).call((zoomBehaviorRef.current as any).transform, t)
    },
  }))

  return (
    <svg ref={svgRef} className="d3Graph" role="img" aria-label="Order to Cash graph">
      <rect x="0" y="0" width="100%" height="100%" fill="transparent" />
    </svg>
  )
})

