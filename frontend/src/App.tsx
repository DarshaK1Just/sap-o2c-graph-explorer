import './App.css'

import axios from 'axios'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { D3Graph, type D3GraphHandle, type GraphEdge as D3Edge, type GraphNode as D3Node } from './components/D3Graph'

type NodeKey = { type: string; id: string }
type GraphNode = { type: string; id: string; label: string; metadata: Record<string, unknown> }
type GraphEdge = { src: NodeKey; rel: string; dst: NodeKey }
type NeighborsResponse = { center: NodeKey; nodes: GraphNode[]; edges: GraphEdge[] }

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

function nodeKeyToCyId(n: NodeKey) {
  return `${n.type}:${n.id}`
}

function typeToGroup(t: string) {
  const tl = t.toLowerCase()
  if (tl.includes('salesorder')) return 'order'
  if (tl.includes('delivery')) return 'delivery'
  if (tl.includes('billing')) return 'billing'
  if (tl.includes('journal') || tl.includes('accounting')) return 'finance'
  if (tl.includes('payment') || tl.includes('clearing')) return 'finance'
  if (tl.includes('customer') || tl.includes('address')) return 'customer'
  if (tl.includes('product')) return 'product'
  if (tl.includes('plant')) return 'plant'
  return 'other'
}

function App() {
  const [status, setStatus] = useState<string>('Not initialized')
  const [search, setSearch] = useState<string>('')
  const [searchResults, setSearchResults] = useState<Array<{ type: string; id: string; label: string }>>([])
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [showOverlay, setShowOverlay] = useState<boolean>(true)
  const [searchResultOpen, setSearchResultOpen] = useState<boolean>(false)
  const graphRef = useRef<D3GraphHandle | null>(null)

  const [graphNodes, setGraphNodes] = useState<Record<string, D3Node>>({})
  const [graphEdges, setGraphEdges] = useState<Record<string, D3Edge>>({})
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [hoverKey, setHoverKey] = useState<string | null>(null)

  const nodeArray = useMemo(() => Object.values(graphNodes), [graphNodes])
  const edgeArray = useMemo(() => Object.values(graphEdges), [graphEdges])
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 })

  const [chatInput, setChatInput] = useState<string>('')
  const [chatLog, setChatLog] = useState<Array<{ role: 'user' | 'assistant'; text: string; sql?: string; rows?: unknown }>>([
    { role: 'assistant', text: 'Ask about Sales Orders, Deliveries, Billing Documents, Journal Entries, Payments, Customers, Products, or Plants.' },
  ])

  const CORE_RELS = useMemo(
    () =>
      new Set([
        'PLACED',
        'HAS_ITEM',
        'FULFILLS',
        'BILLS_DELIVERY',
        'POSTED_AS',
        'REFERS_TO_BILLING',
        'MADE_PAYMENT',
        'CLEARED_BY',
        'CLEARS',
      ]),
    [],
  )

  async function initialize() {
    setStatus('Initializing (ingest + graph build)...')
    try {
      const res = await axios.post(`${API_BASE}/admin/rebuild`)
      setStatus(`Ready. nodes=${res.data.nodes} edges=${res.data.edges}`)

      // Auto-load a good starting neighborhood so the canvas isn't blank.
      const seed = await axios.get<{ type: string; id: string }>(`${API_BASE}/graph/seed`)
      const payload = await fetchNeighbors({ type: seed.data.type, id: seed.data.id })
      upsertGraph(payload)

      // Expand a few top direct neighbors for a richer initial layout
      const neighborKeys = new Set<string>()
      for (const edge of payload.edges) {
        const sourceKey = nodeKeyToCyId(edge.src)
        const targetKey = nodeKeyToCyId(edge.dst)
        if (sourceKey !== nodeKeyToCyId({ type: seed.data.type, id: seed.data.id })) neighborKeys.add(sourceKey)
        if (targetKey !== nodeKeyToCyId({ type: seed.data.type, id: seed.data.id })) neighborKeys.add(targetKey)
      }
      let count = 0
      for (const nk of neighborKeys) {
        if (count >= 3) break
        const [type, id] = nk.split(':', 2)
        if (!type || !id) continue
        const neighborPayload = await fetchNeighbors({ type, id })
        upsertGraph(neighborPayload)
        count += 1
      }
    } catch (e: any) {
      setStatus(`Init failed: ${e?.message ?? String(e)}`)
    }
  }

  async function fetchNeighbors(n: NodeKey) {
    const res = await axios.get<NeighborsResponse>(`${API_BASE}/graph/neighbors`, { params: { node_type: n.type, node_id: n.id, limit: 400 } })
    return res.data
  }

  function upsertGraph(payload: NeighborsResponse) {
    setGraphNodes((prev) => {
      const next = { ...prev }
      for (const n of payload.nodes) {
        const key = nodeKeyToCyId({ type: n.type, id: n.id })
        if (!next[key]) {
          next[key] = {
            key,
            type: n.type,
            id: n.id,
            label: n.label,
            group: typeToGroup(n.type),
            metadata: n.metadata,
          }
        } else {
          // keep any simulation positions (x/y) and just update metadata/label
          next[key] = { ...next[key], label: n.label, metadata: n.metadata, group: typeToGroup(n.type) }
        }
      }
      return next
    })

    setGraphEdges((prev) => {
      const next = { ...prev }
      for (const e of payload.edges) {
        const source = nodeKeyToCyId(e.src)
        const target = nodeKeyToCyId(e.dst)
        const key = `${source}--${e.rel}-->${target}`
        if (!next[key]) {
          next[key] = { key, source, target, rel: e.rel, isCore: CORE_RELS.has(e.rel) }
        }
      }
      return next
    })
  }

  // Auto-initialize on first load (so you immediately see the graph like the reference).
  useEffect(() => {
    // only if we haven't initialized yet
    if (status !== 'Not initialized') return
    void initialize()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function doSearch() {
    if (!search.trim()) {
      setSearchResultOpen(false)
      return
    }
    const res = await axios.get(`${API_BASE}/graph/search`, { params: { q: search.trim(), limit: 25 } })
    setSearchResults(res.data)
    setSearchResultOpen(true)
  }

  async function focusResult(r: { type: string; id: string; label: string }) {
    const payload = await fetchNeighbors({ type: r.type, id: r.id })
    upsertGraph(payload)
    setSelected({ type: r.type, id: r.id, label: r.label, metadata: {} })
    setSelectedKey(nodeKeyToCyId({ type: r.type, id: r.id }))
  }

  // D3 has native zoom wired via graphRef.
  async function sendChat() {
    const msg = chatInput.trim()
    if (!msg) return
    setChatInput('')
    setChatLog((l) => [...l, { role: 'user', text: msg }])
    try {
      const res = await axios.post(`${API_BASE}/chat`, { message: msg })
      setChatLog((l) => [...l, { role: 'assistant', text: res.data.answer, sql: res.data.sql ?? undefined, rows: res.data.rows ?? undefined }])
    } catch (e: any) {
      setChatLog((l) => [...l, { role: 'assistant', text: `Error: ${e?.message ?? String(e)}` }])
    }
  }

  return (
    <div className="refShell">
      <header className="refHeader">
        <div className="crumbs">
          <span className="crumbMuted">Mapping</span>
          <span className="crumbSep">/</span>
          <span className="crumbStrong">Order to Cash</span>
        </div>
        <div className="headerRight">
          <button className="refBtnPrimary" onClick={initialize}>
            Initialize
          </button>
          <div className="headerStatus">{status}</div>
        </div>
      </header>

      <div className="refBody">
        <section className="canvasWrap">
          <div className="refCanvas">
            <div className="graph">
              <div className="graphTopControls">
                <div className="graphSearchGroup">
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search nodes (e.g., 90504248, Sales Order 740506)"
                  />
                  <button className="refBtnPrimary" onClick={doSearch}>
                    Search
                  </button>
                  <button className="refBtnDark" onClick={() => setShowOverlay((v) => !v)}>
                    {showOverlay ? 'Hide Granular Overlay' : 'Show Granular Overlay'}
                  </button>
                </div>
                <div className="graphZoomGroup">
                  <button className="refBtnGhost" onClick={() => graphRef.current?.zoomOut()}>
                    -
                  </button>
                  <button className="refBtnGhost" onClick={() => graphRef.current?.zoomIn()}>
                    +
                  </button>
                  <button className="refBtnGhost" onClick={() => graphRef.current?.fit()}>
                    Fit
                  </button>
                </div>
              </div>

              {searchResultOpen && (
                <div className="overlayResultsPanel">
                  <div className="overlayTitle">
                    Search Results
                    <button className="dismissSearchResults" onClick={() => setSearchResultOpen(false)}>
                      ×
                    </button>
                  </div>
                  {searchResults.length === 0 ? (
                    <div className="muted">No results. Try a keyword and click Search.</div>
                  ) : (
                    <div className="overlayResults">
                      {searchResults.map((r) => (
                        <button key={nodeKeyToCyId(r)} className="overlayResult" onClick={() => focusResult(r)}>
                          <div className="overlayResultTitle">{r.label}</div>
                          <div className="overlayResultMeta">
                            {r.type} · {r.id}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <D3Graph
                ref={graphRef}
                nodes={nodeArray}
                edges={edgeArray}
                selectedKey={selectedKey}
                showGranular={showOverlay}
                onSelectNode={useCallback((key: string | null) => {
                  if (key) {
                    setSelectedKey(key)
                    const n = graphNodes[key]
                    if (n) setSelected({ type: n.type, id: n.id, label: n.label, metadata: n.metadata })
                  } else {
                    setSelectedKey(null)
                    setSelected(null)
                  }
                }, [graphNodes])}
                onExpandNode={useCallback(async (key: string) => {
                  const n = graphNodes[key]
                  if (!n) return
                  const payload = await fetchNeighbors({ type: n.type, id: n.id })
                  upsertGraph(payload)
                }, [graphNodes])}
                onHoverNode={useCallback((key: string | null, x: number, y: number) => {
                  setHoverKey(key)
                  setHoverPos({ x, y })
                }, [])}
              />

              {hoverKey && graphNodes[hoverKey] ? (
                <div className="nodeTooltip" style={{ left: hoverPos.x + 14, top: hoverPos.y + 14 }}>
                  <div className="tipTitle">{graphNodes[hoverKey].label}</div>
                  <div className="tipSub">
                    Entity: {graphNodes[hoverKey].type} · ID: {graphNodes[hoverKey].id}
                  </div>
                  <div className="tipMeta">
                    {Object.entries(graphNodes[hoverKey].metadata)
                      .slice(0, 10)
                      .map(([k, v]) => (
                        <div key={k} className="tipRow">
                          <span className="tipK">{k}</span>
                          <span className="tipV">{String(v)}</span>
                        </div>
                      ))}
                  </div>
                  <div className="tipHint">Double-click to expand</div>
                </div>
              ) : null}

              {selected ? (
                <div className="graphInspector">
                  <div className="inspectorHeader">
                    <div className="inspectorTitle">Inspector</div>
                    <button className="dismissInspector" onClick={() => {
                      setSelectedKey(null)
                      setSelected(null)
                    }}>
                      ×
                    </button>
                  </div>
                  <div className="inspectorBody">
                    <div className="insLine">
                      <span className="insK">Entity</span>
                      <span className="insV">{selected.type}</span>
                    </div>
                    <div className="insLine">
                      <span className="insK">ID</span>
                      <span className="insV">{selected.id}</span>
                    </div>
                    <pre className="insJson">{JSON.stringify(selected.metadata, null, 2)}</pre>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </section>

        <aside className="sidebar">
          <div className="sideTitle">Chat with Graph</div>
          <div className="sideSubtitle">Order to Cash</div>

          <div className="agentCard">
            <div className="agentAvatar">D</div>
            <div className="agentMeta">
              <div className="agentName">Dodge AI</div>
              <div className="agentRole">Graph Agent</div>
            </div>
          </div>

          <div className="agentIntro">Hi! I can help you analyze the <b>Order to Cash</b> process.</div>

          <div className="chatLog refChatLog">
            {chatLog.map((m, idx) => (
              <div key={idx} className={`msg ${m.role}`}>
                <div className="bubble">
                  <div className="msgText">{m.text}</div>
                  {m.sql && (
                    <>
                      <div className="sqlLabel">SQL</div>
                      <pre className="sql">{m.sql}</pre>
                    </>
                  )}
                  {!!m.rows && (
                    <>
                      <div className="sqlLabel">Rows</div>
                      <pre className="sql">{JSON.stringify(m.rows, null, 2)}</pre>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="awaiting">
            <span className="dot" />
            Dodge AI is awaiting instructions
          </div>

          <div className="chatInput refChatInput">
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder="Analyze anything"
              onKeyDown={(e) => (e.key === 'Enter' ? sendChat() : null)}
            />
            <button className="refSend" onClick={sendChat}>
              Send
            </button>
          </div>

          <div className="inspector">
            <div className="inspectorTitle">Graph inspector is now on graph panel</div>
            <div className="muted">Use node click on the graph to view node details.</div>
          </div>
        </aside>
      </div>
    </div>
  )
}

export default App
