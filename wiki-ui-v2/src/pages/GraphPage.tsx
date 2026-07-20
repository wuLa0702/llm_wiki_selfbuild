import { useEffect, useState, useRef, useCallback } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent } from '@/components/ui/card';
import { Network, ZoomIn, ZoomOut, RotateCcw, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Network as VisNetwork } from 'vis-network';
import { DataSet } from 'vis-data';
import { useNavigate } from 'react-router-dom';

/* ─── Types ─── */

interface GraphNode {
  id: string;
  label?: string;
  title?: string;
  group?: string;
  page_type?: string;
  degree?: number;
}

interface GraphEdge {
  id?: string;
  from: string;
  to: string;
  weight?: number;
  label?: string;
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/* ─── Design System Colors (from design-system.md) ─── */

const TYPE_COLORS: Record<string, string> = {
  entity: '#3b82f6',
  concept: '#8b5cf6',
  source: '#10b981',
  query: '#f59e0b',
  comparison: '#ec4899',
};

const TYPE_SHAPES: Record<string, string> = {
  entity: 'dot',
  concept: 'dot',
  source: 'square',
  query: 'diamond',
  comparison: 'star',
};

const TYPE_LABELS: Record<string, string> = {
  entity: '实体', concept: '概念', source: '引用源',
  query: '检索问句', comparison: '整合摘要',
};

/* ─── Helpers ─── */

function isLargeGraph(nodeCount: number): boolean {
  return nodeCount > 30;
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function buildNodeVisItem(n: GraphNode, deg: number) {
  const pt = n.page_type || 'entity';
  const color = TYPE_COLORS[pt] || TYPE_COLORS.entity;
  const size = Math.max(12, Math.min(42, 10 + deg * 1.8));

  return {
    id: n.id,
    label: n.label || n.id.split('/').pop() || n.id,
    title: `<div style="font-size:12px;padding:4px;line-height:1.5">
      <b>${n.label || n.id}</b><br/>
      <span style="color:${color}">${TYPE_LABELS[pt] || pt || '未知'}</span><br/>
      连接: ${deg}
    </div>`,
    _pageType: pt,                   // custom: used by hover highlight
    size,
    color: {
      background: color,
      border: '#ffffff',
      highlight: { background: color, border: '#ffffff' },
      hover: { background: color, border: '#ffffff' },
    },
    borderWidth: 2,
    borderWidthSelected: 3,
    shape: TYPE_SHAPES[pt] || 'dot',
    font: { size: 0 },            // hidden by default
  };
}

function buildEdgeVisItem(e: GraphEdge, i: number, large: boolean) {
  const weight = e.weight || 1;
  return {
    id: e.id || `e${i}`,
    from: e.from,
    to: e.to,
    width: large
      ? Math.max(0.2, Math.min(1.5, weight * 0.2))
      : Math.max(0.3, Math.min(2.5, weight * 0.3)),
    color: { color: '#d4d4d8', opacity: 0.3 },
    smooth: large
      ? false
      : { enabled: true, type: 'continuous', roundness: 0.5 },
    label: '',
    font: { size: 0 },
  };
}

/* ─── Component ─── */

export default function GraphPage() {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<VisNetwork | null>(null);
  const nodesRef = useRef<DataSet<any> | null>(null);
  const edgesRef = useRef<DataSet<any> | null>(null);

  // Refs for debounce / idle timers
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const blurTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const physicsTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [filterText, setFilterText] = useState('');
  const [showLegend, setShowLegend] = useState(true);

  const nodeCount = graphData?.nodes.length || 0;
  const edgeCount = graphData?.edges.length || 0;
  const large = isLargeGraph(nodeCount);

  /* ─── Data Fetching ─── */

  useEffect(() => {
    setLoading(true);
    setError('');
    fetch('/v1/graph')
      .then(r => r.json())
      .then(d => {
        const nodes: GraphNode[] = d.nodes || [];
        const rawEdges: any[] = d.edges || [];
        const edges: GraphEdge[] = rawEdges.map(e => ({
          from: e.source || e.from,
          to: e.target || e.to,
          weight: e.weight,
        })).filter(e => e.from && e.to);

        if (!nodes.length) {
          setGraphData(null);
          setLoading(false);
          return;
        }

        // Calculate degree
        const degreeMap: Record<string, number> = {};
        edges.forEach(e => {
          degreeMap[e.from!] = (degreeMap[e.from!] || 0) + 1;
          degreeMap[e.to!] = (degreeMap[e.to!] || 0) + 1;
        });

        setGraphData({
          nodes: nodes.map(n => {
            const deg = typeof n.degree === 'object' && n.degree !== null
              ? ((n.degree as any).in || 0) + ((n.degree as any).out || 0)
              : (n.degree || 0);
            return { ...n, degree: deg || degreeMap[n.id] || 0 };
          }),
          edges,
        });
        setLoading(false);
      })
      .catch(e => {
        setError(e.message || '无法加载图谱数据');
        setLoading(false);
      });
  }, []);

  /* ─── Render Network ─── */

  useEffect(() => {
    if (!graphData || !containerRef.current || networkRef.current) return;

    const nodes = new DataSet<any>(graphData.nodes.map(n => {
      const deg = n.degree || 0;
      return buildNodeVisItem(n, deg);
    }));

    const edges = new DataSet<any>(graphData.edges.map((e, i) =>
      buildEdgeVisItem(e, i, large)
    ));

    nodesRef.current = nodes;
    edgesRef.current = edges;

    const options: Record<string, any> = {
      nodes: {
        scaling: { min: 12, max: 42 },
        borderWidth: 2,
        borderWidthSelected: 3,
      },
      edges: {
        smooth: large ? false : { enabled: true, type: 'continuous', roundness: 0.5 },
      },
      physics: {
        solver: 'barnesHut',
        barnesHut: {
          gravitationalConstant: -3000,
          centralGravity: 0.2,
          springLength: 180,
          springConstant: 0.02,
          damping: 0.8,
        },
        maxVelocity: 20,
        minVelocity: 0.5,
        stabilization: {
          iterations: 500,
          updateInterval: 25,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        navigationButtons: false,
        keyboard: true,
        multiselect: false,
      },
      layout: {
        improvedLayout: true,
      },
      groups: Object.fromEntries(
        Object.entries(TYPE_COLORS).map(([key, color]) => [
          key,
          {
            color: { background: color, border: '#ffffff' },
            shape: TYPE_SHAPES[key],
          },
        ])
      ),
    };

    const network = new VisNetwork(containerRef.current, { nodes, edges }, options);
    networkRef.current = network;

    /* ── Stabilization complete: freeze physics ── */
    network.once('stabilizationIterationsDone', () => {
      network.setOptions({ physics: false });
      network.fit({ animation: { duration: 300, easingFunction: 'easeOutQuad' } as any });
    });

    /* ── Select node → show label ── */
    network.on('selectNode', (params) => {
      if (!params.nodes?.length) return;
      const selectedId = params.nodes[0];

      // Hide all labels first
      nodes.forEach((n: any) => {
        if (n.id === selectedId) {
          nodes.update({ id: n.id, font: { size: 11, color: '#a1a1aa' } });
        } else {
          nodes.update({ id: n.id, font: { size: 0 } });
        }
      });
    });

    network.on('deselectNode', () => {
      // Restore all labels to hidden
      nodes.forEach((n: any) => {
        nodes.update({ id: n.id, font: { size: 0 } });
      });
    });

    /* ── Click → navigate (after visual feedback) ── */
    network.on('click', (params) => {
      if (params.nodes?.length > 0) {
        const nodeId = params.nodes[0];
        // Brief delay to let the select visual render before navigating
        setTimeout(() => {
          navigate(`/wiki?path=${encodeURIComponent(nodeId)}`);
        }, 120);
      }
    });

    /* ── Hover: 100ms debounce highlight ── */
    const doHighlight = (nodeId: string | number) => {
      if (!networkRef.current) return;
      const connectedNodes = network.getConnectedNodes(nodeId) as (string | number)[];
      const connectedEdges = network.getConnectedEdges(nodeId) as (string | number)[];
      const highlightSet = new Set([nodeId, ...connectedNodes]);

      nodes.forEach((n: any) => {
        const isHighlight = highlightSet.has(n.id);
        const baseColor = TYPE_COLORS[n._pageType || 'entity'] || '#3b82f6';
        nodes.update({
          id: n.id,
          color: {
            ...n.color,
            background: isHighlight ? baseColor : hexToRgba(baseColor, 0.12),
            border: isHighlight ? '#ffffff' : hexToRgba('#ffffff', 0.15),
          },
        });
      });

      const edgeSet = new Set(connectedEdges);
      edges.forEach((e: any) => {
        edges.update({
          id: e.id,
          color: { ...e.color, opacity: edgeSet.has(e.id) ? 0.5 : 0.02 },
        });
      });
    };

    const doRestore = () => {
      nodes.forEach((n: any) => {
        const baseColor = TYPE_COLORS[n._pageType || 'entity'] || '#3b82f6';
        nodes.update({
          id: n.id,
          color: {
            ...n.color,
            background: baseColor,
            border: '#ffffff',
          },
        });
      });
      edges.forEach((e: any) => {
        edges.update({ id: e.id, color: { ...e.color, opacity: 0.3 } });
      });
    };

    network.on('hoverNode', (params) => {
      if (!params.node) return;

      // Clear blur timer (cancel pending restore)
      if (blurTimerRef.current) {
        clearTimeout(blurTimerRef.current);
        blurTimerRef.current = null;
      }

      // Debounce hover to avoid frequent repaints
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = setTimeout(() => {
        doHighlight(params.node!);
      }, 100);
    });

    /* ── Blur: 200ms delay before restore (smooth feel) ── */
    network.on('blurNode', () => {
      if (hoverTimerRef.current) {
        clearTimeout(hoverTimerRef.current);
        hoverTimerRef.current = null;
      }
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
      blurTimerRef.current = setTimeout(() => {
        doRestore();
      }, 200);
    });

    /* ── Idle physics: 2s inactivity → pause ── */
    const container = containerRef.current;

    const resumePhysics = () => {
      const nw = networkRef.current;
      if (!nw) return;
      nw.setOptions({ physics: true });
      // Reset idle timer
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      idleTimerRef.current = setTimeout(() => {
        if (networkRef.current) {
          networkRef.current.setOptions({ physics: false });
        }
      }, 2000);
    };

    container?.addEventListener('mousemove', resumePhysics);
    container?.addEventListener('mousedown', resumePhysics);
    container?.addEventListener('touchstart', resumePhysics);
    container?.addEventListener('wheel', resumePhysics);

    // Start idle timer after stabilization
    network.once('stabilizationIterationsDone', () => {
      idleTimerRef.current = setTimeout(() => {
        if (networkRef.current) {
          networkRef.current.setOptions({ physics: false });
        }
      }, 2000);
    });

    /* ── Cleanup ── */
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      if (physicsTimerRef.current) clearTimeout(physicsTimerRef.current);
      container?.removeEventListener('mousemove', resumePhysics);
      container?.removeEventListener('mousedown', resumePhysics);
      container?.removeEventListener('touchstart', resumePhysics);
      container?.removeEventListener('wheel', resumePhysics);
      network.destroy();
      networkRef.current = null;
      nodesRef.current = null;
      edgesRef.current = null;
    };
  }, [graphData, navigate, large]);

  /* ─── Filter ─── */

  const handleFilter = useCallback(() => {
    if (!networkRef.current || !graphData) return;
    if (!filterText.trim()) {
      networkRef.current.setSelection({ nodes: [] });
      return;
    }
    const matched = graphData.nodes
      .filter(n => (n.label || n.id).toLowerCase().includes(filterText.toLowerCase()))
      .map(n => n.id);
    networkRef.current.selectNodes(matched, false);
    if (matched.length > 0) {
      networkRef.current.focus(matched[0], { scale: 1.5, animation: { duration: 300, easingFunction: 'easeOutQuad' } as any });
    }
  }, [filterText, graphData]);

  const resetView = () => {
    if (networkRef.current) {
      networkRef.current.fit({ animation: { duration: 300, easingFunction: 'easeOutQuad' } as any });
      networkRef.current.setSelection({ nodes: [] });
    }
    setFilterText('');
  };

  const zoomIn = () => {
    if (networkRef.current) {
      const scale = networkRef.current.getScale();
      networkRef.current.moveTo({ scale: scale * 1.3, animation: { duration: 200, easingFunction: 'easeOutQuad' } as any });
    }
  };

  const zoomOut = () => {
    if (networkRef.current) {
      const scale = networkRef.current.getScale();
      networkRef.current.moveTo({ scale: scale * 0.7, animation: { duration: 200, easingFunction: 'easeOutQuad' } as any });
    }
  };

  /* ─── Render ─── */

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* ── Top bar (search + stats only) ── */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-card flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Network className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">
              {loading ? '加载中...' : `${nodeCount} 节点 / ${edgeCount} 连接`}
              {large && <span className="ml-1.5 text-[10px] text-muted-foreground/60">(简化视图)</span>}
            </span>
          </div>
          {/* Search filter */}
          <div className="relative flex items-center">
            <Search className="h-3 w-3 absolute left-2 text-muted-foreground" />
            <Input
              className="h-7 w-44 pl-6 text-xs"
              placeholder="搜索节点..."
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleFilter()}
            />
            {filterText && (
              <X className="h-3 w-3 absolute right-2 text-muted-foreground cursor-pointer hover:text-foreground"
                onClick={() => { setFilterText(''); resetView(); }} />
            )}
          </div>
        </div>
      </div>

      {/* ── Network canvas area ── */}
      <div className="flex-1 relative">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Skeleton className="h-32 w-32 rounded-full mx-auto mb-4" />
              <p className="text-sm text-muted-foreground">加载图谱...</p>
            </div>
          </div>
        ) : error ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Network className="h-10 w-10 mx-auto mb-2 text-destructive opacity-50" />
              <p className="text-sm text-destructive">{error}</p>
              <Button variant="outline" size="sm" className="mt-2" onClick={() => window.location.reload()}>
                重试
              </Button>
            </div>
          </div>
        ) : !graphData || nodeCount === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <Network className="h-10 w-10 mx-auto mb-2 opacity-30" />
              <p className="text-sm">没有可见节点</p>
              <p className="text-xs text-muted-foreground mt-1">导入文档后图谱将自动生成</p>
            </div>
          </div>
        ) : (
          <>
            {/* Network container */}
            <div ref={containerRef} className="w-full h-full overflow-hidden" />

            {/* ── Floating Toolbar (bottom-right) ── */}
            <Card className="absolute bottom-4 right-4 bg-card/85 backdrop-blur-md border border-border/60 rounded-xl shadow-lg z-10">
                <CardContent className="p-1.5 flex items-center gap-0.5">
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={zoomIn} title="放大">
                    <ZoomIn className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={zoomOut} title="缩小">
                    <ZoomOut className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" className="h-8 w-8" onClick={resetView} title="重置视图">
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                  <div className="w-px h-5 bg-border/60 mx-0.5" />
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 px-2 text-xs gap-1"
                    onClick={() => setShowLegend(v => !v)}
                  >
                    {showLegend ? '隐藏图例' : '图例'}
                  </Button>
                </CardContent>
              </Card>

            {/* ── Floating Legend (bottom-left) ── */}
            {showLegend && (
              <Card className="absolute bottom-4 left-4 bg-card/85 backdrop-blur-md border border-border/60 rounded-xl shadow-lg z-10">
                <CardContent className="p-3 text-xs space-y-1.5">
                  <p className="font-medium text-foreground mb-1.5">图例</p>
                  {Object.entries(TYPE_LABELS).map(([key, label]) => (
                    <div key={key} className="flex items-center gap-2">
                      <span
                        className="w-3 h-3 rounded-full inline-block ring-1 ring-white/50"
                        style={{ backgroundColor: TYPE_COLORS[key] }}
                      />
                      <span className="text-muted-foreground">{label}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Hover hint */}
            <div className="absolute top-3 right-3 text-[10px] text-muted-foreground/40 bg-card/60 px-2 py-1 rounded-md border border-border/30">
              滚轮缩放 · 拖拽移动 · 点击跳转
            </div>
          </>
        )}
      </div>
    </div>
  );
}
