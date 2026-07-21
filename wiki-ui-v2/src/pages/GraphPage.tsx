import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Network as NetworkIcon, ZoomIn, ZoomOut, RotateCcw, Search, X,
  EyeOff, Filter, Maximize, FolderClosed, FileText, BookOpen, GitBranch,
  Lightbulb, Layers, Palette, ChevronDown, ChevronRight,
} from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Network as VisNetwork } from 'vis-network';
import { DataSet } from 'vis-data';
import EmptyState from '@/components/shared/EmptyState';
import { useTheme } from '@/hooks/useTheme';

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
}

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface FileNode {
  type: 'file' | 'directory';
  size?: number;
  children?: Record<string, FileNode>;
}

interface Community {
  members: string[];
  cohesion: number;
  size: number;
  label?: string;
}

interface CommunitiesResp {
  communities: Record<string, Community>;
}

interface Insight {
  source: string;
  target: string;
  reason: string;
  surprise_score: number;
  connection_type: string;
}

interface KnowledgeGap {
  page: string;
  reason: string;
  gap_type: string;
}

interface InsightsResp {
  surprising_connections: Insight[];
  knowledge_gaps: KnowledgeGap[];
  summary: {
    total_surprising: number;
    total_gaps: number;
    gap_types: Record<string, number>;
  };
}

/* ─── Design tokens ─── */

const TYPE_COLORS: Record<string, string> = {
  entity: '#3b82f6',
  concept: '#8b5cf6',
  source: '#f97316',
  query: '#f59e0b',
  comparison: '#ef4444',
};

const TYPE_LABELS: Record<string, string> = {
  entity: '实体', concept: '概念', source: '来源',
  query: '检索问句', comparison: '综合',
};

// Community color palette (up to 10 distinct colors, cycle if more)
const COMMUNITY_PALETTE = [
  '#3b82f6', '#10b981', '#f59e0b', '#ec4899',
  '#8b5cf6', '#06b6d4', '#f97316', '#84cc16',
  '#ef4444', '#14b8a6',
];

/* ─── Helpers ─── */

function isLargeGraph(n: number): boolean { return n > 40; }

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function countFiles(children: Record<string, FileNode>): number {
  return Object.values(children).reduce(
    (acc, n) => acc + (n.type === 'file' ? 1 : countFiles(n.children || {})), 0
  );
}

function shortName(id: string): string {
  return id.split('/').pop()?.replace(/\.md$/i, '') || id;
}

type ViewMode = 'type' | 'community' | 'insights';

/* ─── Component ─── */

export default function GraphPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<VisNetwork | null>(null);
  const nodesRef = useRef<DataSet<any> | null>(null);
  const edgesRef = useRef<DataSet<any> | null>(null);

  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const blurTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* Graph state */
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [communities, setCommunities] = useState<Record<string, Community> | null>(null);
  const [insights, setInsights] = useState<InsightsResp | null>(null);
  const [filterText, setFilterText] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('type');
  const [showFilter, setShowFilter] = useState(false);
  const [showLegend, setShowLegend] = useState(true);

  /* Filter panel options */
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set());
  const [hiddenCommunities, setHiddenCommunities] = useState<Set<string>>(new Set());
  const [hideOrphans, setHideOrphans] = useState(false);
  const [minDegree, setMinDegree] = useState(0);
  const [maxDegree, setMaxDegree] = useState(100);
  const [nodeScalePct, setNodeScalePct] = useState(100);

  /* File tree state */
  const [wikiTree, setWikiTree] = useState<Record<string, FileNode>>({});
  const [treeLoading, setTreeLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('wiki-sidebar-graph') || '{}'); } catch { return {}; }
  });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  /* ── Derived ── */
  const nodeCount = graphData?.nodes.length || 0;
  const edgeCount = graphData?.edges.length || 0;
  const large = isLargeGraph(nodeCount);
  const labelFontSize = large ? 10 : 12;

  const nodeCommunityMap = useMemo<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    if (!communities) return map;
    Object.entries(communities).forEach(([cid, c]) => {
      c.members.forEach(m => {
        // members look like "concepts/foo.md" — same namespace as /v1/graph node ids (no wiki/ prefix)
        const key = m.startsWith('wiki/') ? m.slice(5) : m;
        map[key] = cid;
      });
    });
    return map;
  }, [communities]);

  const maxNodeDegree = useMemo(() => {
    if (!graphData) return 0;
    return graphData.nodes.reduce((m, n) => Math.max(m, n.degree || 0), 0);
  }, [graphData]);

  // effective max degree slider bound is actual max degree
  useEffect(() => {
    if (maxNodeDegree > 0) setMaxDegree(maxNodeDegree);
  }, [maxNodeDegree]);

  function communityColor(cid: string | undefined): string {
    if (cid === undefined) return isDark ? '#4b5563' : '#9ca3af';
    const idx = parseInt(cid, 10) % COMMUNITY_PALETTE.length;
    return COMMUNITY_PALETTE[idx] || '#9ca3af';
  }

  function communityLabel(cid: string, c?: Community): string {
    if (c?.label) return c.label;
    // Auto-generate a label from top-scoring member (first member's title)
    return `社区 ${cid}`;
  }

  /* ── Canvas palette ── */
  const CANVAS_BG = isDark ? '#0d0d10' : '#fafafa';
  const EDGE_COLOR = isDark ? 'rgba(161,161,170,0.35)' : 'rgba(120,120,130,0.35)';
  const EDGE_DIM = isDark ? 'rgba(161,161,170,0.04)' : 'rgba(120,120,130,0.06)';
  const EDGE_HIGHLIGHT = '#f59e0b'; // for insights surprise edges
  const LABEL_COLOR = isDark ? '#e5e7eb' : '#1f2937';
  const TOOLTIP_BG = isDark ? '#1c1c20' : '#ffffff';
  const TOOLTIP_FG = isDark ? '#e5e7eb' : '#1f2937';
  const FLOATING_BG = isDark ? 'bg-[#1a1a1e]/90' : 'bg-white/90';
  const FLOATING_BORDER = isDark ? 'border-white/10' : 'border-black/10';

  /* ─── Fetch data ─── */
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

        if (!nodes.length) { setGraphData(null); setLoading(false); return; }

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
      .catch(e => { setError(e.message || '无法加载图谱数据'); setLoading(false); });

    fetch('/v1/communities').then(r => r.json()).then((d: CommunitiesResp) => {
      setCommunities(d.communities || {});
    }).catch(() => {});

    fetch('/v1/insights').then(r => r.json()).then((d: InsightsResp) => {
      setInsights(d);
    }).catch(() => {});
  }, []);

  /* ─── File tree ─── */
  useEffect(() => {
    fetch('/v1/file-tree')
      .then(r => r.json())
      .then(d => {
        setWikiTree(d.wiki?.children || {});
        setTreeLoading(false);
      })
      .catch(() => setTreeLoading(false));
  }, []);

  useEffect(() => {
    localStorage.setItem('wiki-sidebar-graph', JSON.stringify(expanded));
  }, [expanded]);

  /* ─── Sync URL ?path= → select node ─── */
  useEffect(() => {
    const path = searchParams.get('path');
    if (!path || !networkRef.current) return;
    // /v1/graph node ids have no "wiki/" prefix (e.g. "concepts/foo.md")
    const nodeId = path.startsWith('wiki/') ? path.slice(5) : path;
    selectAndFocusNode(nodeId, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, graphData]);

  /* ─── Node color by view mode ─── */
  const getNodeColor = useCallback((n: any): string => {
    if (viewMode === 'community') {
      const cid = nodeCommunityMap[n.id];
      return communityColor(cid);
    }
    if (viewMode === 'insights') {
      // Highlight surprising connection endpoints
      return TYPE_COLORS[n._pageType || 'entity'] || TYPE_COLORS.entity;
    }
    return TYPE_COLORS[n._pageType || 'entity'] || TYPE_COLORS.entity;
  }, [viewMode, nodeCommunityMap]);

  /* ─── Select + focus a node ─── */
  const selectAndFocusNode = useCallback((rawNodeId: string, navigateToWiki: boolean) => {
    const nw = networkRef.current;
    const nds = nodesRef.current;
    if (!nw || !nds) return;
    // Normalize: node ids in vis-network have no "wiki/" prefix, but file tree
    // and URL query pass "wiki/concepts/foo.md" — strip the prefix here.
    const nodeId = rawNodeId.startsWith('wiki/') ? rawNodeId.slice(5) : rawNodeId;
    const exists = nds.get(nodeId);
    if (!exists) { setSelectedNodeId(null); return; }

    setSelectedNodeId(nodeId);
    nw.selectNodes([nodeId]);
    nw.focus(nodeId, {
      scale: 1.3,
      animation: { duration: 400, easingFunction: 'easeOutQuad' } as any,
    });

    const updates = nds.get().map((n: any) => ({
      id: n.id,
      font: {
        size: labelFontSize,
        color: n.id === nodeId ? LABEL_COLOR : hexToRgba(LABEL_COLOR, 0.35),
        face: 'Inter, system-ui, -apple-system, sans-serif',
        strokeWidth: 0,
        align: 'right',
        vadjust: 0,
      } as any,
    }));
    nds.update(updates);

    if (navigateToWiki) {
      // /wiki route expects "wiki/..." prefix in the path query param
      setTimeout(() => navigate(`/wiki?path=${encodeURIComponent('wiki/' + nodeId)}`), 150);
    }
  }, [navigate, LABEL_COLOR, labelFontSize]);

  /* ─── Build vis-network ─── */
  useEffect(() => {
    if (!graphData || !containerRef.current || networkRef.current) return;

    const nodes = new DataSet<any>(graphData.nodes.map(n => {
      const deg = n.degree || 0;
      const pt = n.page_type || 'entity';
      const size = Math.max(10, Math.min(38, 10 + deg * 2));
      const color = TYPE_COLORS[pt] || TYPE_COLORS.entity;
      const cid = nodeCommunityMap[n.id];
      return {
        id: n.id,
        label: n.label || shortName(n.id),
        title: `<div style="font-size:12px;padding:6px 8px;line-height:1.5;background:${TOOLTIP_BG};color:${TOOLTIP_FG};border-radius:6px">
          <b style="font-weight:600">${n.label || shortName(n.id)}</b><br/>
          <span style="color:${color}">${TYPE_LABELS[pt] || pt}</span> · 连接 ${deg}
          ${cid !== undefined ? `<br/><span style="opacity:0.7">${communityLabel(cid, communities?.[cid])}</span>` : ''}
        </div>`,
        _pageType: pt,
        _communityId: cid,
        _degree: deg,
        size,
        color: {
          background: color,
          border: color,
          highlight: { background: color, border: '#ffffff' },
          hover: { background: color, border: '#ffffff' },
        },
        borderWidth: 0,
        borderWidthSelected: 3,
        shape: 'dot',
        font: {
          size: labelFontSize,
          color: LABEL_COLOR,
          face: 'Inter, system-ui, -apple-system, sans-serif',
          strokeWidth: 0,
          align: 'right',
          vadjust: 0,
        },
        labelHighlightBold: false,
      };
    }));

    // Build edge set; in insights mode, mark surprising edges
    const surpriseSet = new Set<string>();
    if (viewMode === 'insights' && insights) {
      insights.surprising_connections.forEach(s => {
        const f = s.source.startsWith('wiki/') ? s.source.slice(5) : s.source;
        const t = s.target.startsWith('wiki/') ? s.target.slice(5) : s.target;
        surpriseSet.add([f, t].sort().join('||'));
      });
    }

    const edges = new DataSet<any>(graphData.edges.map((e, i) => {
      // Node ids from /v1/graph have NO wiki/ prefix (e.g. "concepts/foo.md").
      // Keep edge endpoints in that same namespace so edges attach correctly.
      const from = e.from.startsWith('wiki/') ? e.from.slice(5) : e.from;
      const to = e.to.startsWith('wiki/') ? e.to.slice(5) : e.to;
      const edgeKey = [from, to].sort().join('||');
      const isSurprise = surpriseSet.has(edgeKey);
      return {
        id: e.id || `e${i}`,
        from,
        to,
        width: isSurprise ? 2 : (large ? 0.6 : 1),
        color: {
          color: isSurprise ? EDGE_HIGHLIGHT : EDGE_COLOR,
          opacity: isSurprise ? 0.9 : 0.6,
        },
        smooth: false,
        _isSurprise: isSurprise,
      };
    }));

    nodesRef.current = nodes;
    edgesRef.current = edges;

    const options: Record<string, any> = {
      nodes: { scaling: { min: 10, max: 38 } },
      edges: { smooth: false },
      physics: {
        solver: 'barnesHut',
        barnesHut: {
          gravitationalConstant: -3000,
          centralGravity: 0.15,
          springLength: 200,
          springConstant: 0.015,
          damping: 0.92,
        },
        maxVelocity: 12,
        minVelocity: 1,
        stabilization: { iterations: 500, updateInterval: 25 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        navigationButtons: false,
        keyboard: false,
        multiselect: false,
        zoomView: true,
        dragView: true,
      },
      layout: { improvedLayout: true },
    };

    const network = new VisNetwork(containerRef.current, { nodes, edges }, options);
    networkRef.current = network;

    network.once('stabilizationIterationsDone', () => {
      network.setOptions({ physics: false });
      network.fit({ animation: { duration: 300, easingFunction: 'easeOutQuad' } as any });
    });

    network.on('click', (params) => {
      if (params.nodes?.length > 0) {
        selectAndFocusNode(params.nodes[0], true);
      } else {
        setSelectedNodeId(null);
        nodes.update(nodes.get().map((n: any) => ({
          id: n.id,
          font: {
            size: labelFontSize,
            color: LABEL_COLOR,
            face: 'Inter, system-ui, -apple-system, sans-serif',
            strokeWidth: 0,
            align: 'right',
            vadjust: 0,
          },
        } as any)));
      }
    });

    /* Hover highlight */
    const doHighlight = (nodeId: string | number) => {
      try {
        if (!networkRef.current || !nodesRef.current || !edgesRef.current) return;
        const nds = nodesRef.current;
        const edgs = edgesRef.current;
        const nw = networkRef.current;
        const connectedNodes = nw.getConnectedNodes(nodeId) as (string | number)[];
        const connectedEdges = nw.getConnectedEdges(nodeId) as (string | number)[];
        const highlightSet = new Set([nodeId, ...connectedNodes]);
        const edgeSet = new Set(connectedEdges);

        nds.update(nds.get().map((n: any) => {
          if (highlightSet.has(n.id)) {
            return { id: n.id, color: { ...n.color, border: '#ffffff', borderWidth: 2 } };
          }
          const baseColor = getNodeColor(n);
          return {
            id: n.id,
            color: { ...n.color, background: hexToRgba(baseColor, 0.2), border: hexToRgba(baseColor, 0.2), borderWidth: 0 },
          };
        }));

        edgs.update(edgs.get().map((e: any) => ({
          id: e.id,
          color: {
            ...e.color,
            color: edgeSet.has(e.id)
              ? (e._isSurprise ? EDGE_HIGHLIGHT : LABEL_COLOR)
              : EDGE_DIM,
            opacity: edgeSet.has(e.id) ? 0.9 : 0.05,
          },
          width: edgeSet.has(e.id) ? (e._isSurprise ? 2.5 : (large ? 1.2 : 2)) : (large ? 0.6 : 1),
        })));
      } catch (_) { /* silent */ }
    };

    const doRestore = () => {
      try {
        if (!nodesRef.current || !edgesRef.current) return;
        const nds = nodesRef.current;
        const edgs = edgesRef.current;
        const selId = selectedNodeId;
        nds.update(nds.get().map((n: any) => {
          const baseColor = getNodeColor(n);
          const isSelected = n.id === selId;
          return {
            id: n.id,
            color: {
              background: baseColor,
              border: isSelected ? '#ffffff' : baseColor,
              borderWidth: isSelected ? 3 : 0,
              highlight: { background: baseColor, border: '#ffffff' },
              hover: { background: baseColor, border: '#ffffff' },
            },
            font: {
              size: labelFontSize,
              color: isSelected ? LABEL_COLOR : hexToRgba(LABEL_COLOR, selId ? 0.35 : 1),
              face: 'Inter, system-ui, -apple-system, sans-serif',
              strokeWidth: 0,
              align: 'right',
              vadjust: 0,
            } as any,
          };
        }));
        edgs.update(edgs.get().map((e: any) => ({
          id: e.id,
          color: {
            color: e._isSurprise ? EDGE_HIGHLIGHT : EDGE_COLOR,
            opacity: e._isSurprise ? 0.9 : 0.6,
          },
          width: e._isSurprise ? 2 : (large ? 0.6 : 1),
        })));
      } catch (_) { /* silent */ }
    };

    network.on('hoverNode', (params) => {
      if (!params.node) return;
      if (blurTimerRef.current) { clearTimeout(blurTimerRef.current); blurTimerRef.current = null; }
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = setTimeout(() => doHighlight(params.node!), 80);
    });

    network.on('blurNode', () => {
      if (hoverTimerRef.current) { clearTimeout(hoverTimerRef.current); hoverTimerRef.current = null; }
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
      blurTimerRef.current = setTimeout(doRestore, 150);
    });

    /* Idle physics pause */
    const container = containerRef.current;
    const resumePhysics = () => {
      if (!networkRef.current) return;
      networkRef.current.setOptions({ physics: true });
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      idleTimerRef.current = setTimeout(() => networkRef.current?.setOptions({ physics: false }), 2000);
    };
    container?.addEventListener('mousemove', resumePhysics);
    container?.addEventListener('mousedown', resumePhysics);
    container?.addEventListener('touchstart', resumePhysics);
    container?.addEventListener('wheel', resumePhysics);

    network.once('stabilizationIterationsDone', () => {
      idleTimerRef.current = setTimeout(() => network.setOptions({ physics: false }), 2000);
    });

    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
      if (blurTimerRef.current) clearTimeout(blurTimerRef.current);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
      container?.removeEventListener('mousemove', resumePhysics);
      container?.removeEventListener('mousedown', resumePhysics);
      container?.removeEventListener('touchstart', resumePhysics);
      container?.removeEventListener('wheel', resumePhysics);
      network.destroy();
      networkRef.current = null;
      nodesRef.current = null;
      edgesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, large, isDark, viewMode, nodeCommunityMap, insights, labelFontSize]);

  /* ─── Re-color nodes when viewMode changes (without rebuilding network) ─── */
  useEffect(() => {
    if (!nodesRef.current || !edgesRef.current) return;
    const nds = nodesRef.current;
    const edgs = edgesRef.current;
    const selId = selectedNodeId;

    nds.update(nds.get().map((n: any) => {
      const baseColor = getNodeColor(n);
      return {
        id: n.id,
        color: {
          background: baseColor,
          border: n.id === selId ? '#ffffff' : baseColor,
          borderWidth: n.id === selId ? 3 : 0,
          highlight: { background: baseColor, border: '#ffffff' },
          hover: { background: baseColor, border: '#ffffff' },
        },
      };
    }));

    // Recompute surprise edges for insights mode
    if (viewMode === 'insights' && insights) {
      const surpriseSet = new Set<string>();
      insights.surprising_connections.forEach(s => {
        // normalize to no-prefix namespace (same as edge from/to)
        const f = s.source.startsWith('wiki/') ? s.source.slice(5) : s.source;
        const t = s.target.startsWith('wiki/') ? s.target.slice(5) : s.target;
        surpriseSet.add([f, t].sort().join('||'));
      });
      edgs.update(edgs.get().map((e: any) => {
        const key = [e.from, e.to].sort().join('||');
        const isSurprise = surpriseSet.has(key);
        return {
          id: e.id,
          _isSurprise: isSurprise,
          color: { color: isSurprise ? EDGE_HIGHLIGHT : EDGE_COLOR, opacity: isSurprise ? 0.9 : 0.6 },
          width: isSurprise ? 2 : (large ? 0.6 : 1),
        };
      }));
    } else {
      edgs.update(edgs.get().map((e: any) => ({
        id: e.id,
        _isSurprise: false,
        color: { color: EDGE_COLOR, opacity: 0.6 },
        width: large ? 0.6 : 1,
      })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode, nodeCommunityMap, insights, isDark]);

  /* ─── Combined filter (type/community/orphan/degree) ─── */
  useEffect(() => {
    if (!nodesRef.current || !edgesRef.current || !graphData) return;
    const nds = nodesRef.current;
    const edgs = edgesRef.current;
    const allNodes = nds.get();

    // Build a quick lookup of each node's community id
    const communityOf: Record<string, string | undefined> = {};
    allNodes.forEach((n: any) => { communityOf[n.id] = n._communityId; });

    nds.update(allNodes.map((n: any) => {
      const pt = n._pageType || 'entity';
      const cid = n._communityId;
      const deg = n._degree || 0;
      let hidden = false;

      // Type filter
      if (viewMode === 'type' && hiddenTypes.has(pt)) hidden = true;
      // Community filter
      if (viewMode === 'community' && cid !== undefined && hiddenCommunities.has(cid)) hidden = true;
      if (viewMode === 'community' && cid === undefined) hidden = true; // nodes without community
      // Orphan filter
      if (hideOrphans && deg === 0) hidden = true;
      // Degree range
      if (deg < minDegree || deg > maxDegree) hidden = true;

      return { id: n.id, hidden };
    }));

    edgs.update(edgs.get().map((e: any) => {
      const fromNode = allNodes.find((n: any) => n.id === e.from);
      const toNode = allNodes.find((n: any) => n.id === e.to);
      const hiddenFrom = fromNode?.hidden ||
        (viewMode === 'type' && hiddenTypes.has(fromNode?._pageType || 'entity')) ||
        (viewMode === 'community' && fromNode?._communityId !== undefined && hiddenCommunities.has(fromNode._communityId)) ||
        (viewMode === 'community' && fromNode?._communityId === undefined) ||
        (hideOrphans && (fromNode?._degree || 0) === 0) ||
        ((fromNode?._degree || 0) < minDegree) || ((fromNode?._degree || 0) > maxDegree);
      const hiddenTo = toNode?.hidden ||
        (viewMode === 'type' && hiddenTypes.has(toNode?._pageType || 'entity')) ||
        (viewMode === 'community' && toNode?._communityId !== undefined && hiddenCommunities.has(toNode._communityId)) ||
        (viewMode === 'community' && toNode?._communityId === undefined) ||
        (hideOrphans && (toNode?._degree || 0) === 0) ||
        ((toNode?._degree || 0) < minDegree) || ((toNode?._degree || 0) > maxDegree);
      return { id: e.id, hidden: hiddenFrom || hiddenTo };
    }));
  }, [hiddenTypes, hiddenCommunities, hideOrphans, minDegree, maxDegree, viewMode, graphData]);

  /* ─── Apply node scale ─── */
  useEffect(() => {
    if (!nodesRef.current) return;
    const scale = nodeScalePct / 100;
    nodesRef.current.update(nodesRef.current.get().map((n: any) => {
      const deg = n._degree || 0;
      const newSize = Math.max(6, Math.min(38, (10 + deg * 2)) * scale);
      return { id: n.id, size: newSize };
    }));
  }, [nodeScalePct]);

  /* ─── Search (debounced) ─── */
  useEffect(() => {
    if (!filterText.trim()) return;
    const t = setTimeout(() => {
      if (!networkRef.current || !graphData) return;
      const matched = graphData.nodes
        .filter(n => (n.label || shortName(n.id)).toLowerCase().includes(filterText.toLowerCase()))
        .map(n => n.id);
      networkRef.current.selectNodes(matched, false);
      if (matched.length > 0) {
        networkRef.current.focus(matched[0], {
          scale: 1.5,
          animation: { duration: 300, easingFunction: 'easeOutQuad' } as any,
        });
      }
    }, 300);
    return () => clearTimeout(t);
  }, [filterText, graphData]);

  /* ─── Tree handlers ─── */
  const toggleExpand = (path: string) => setExpanded(prev => ({ ...prev, [path]: !prev[path] }));

  const handleTreeSelect = (path: string) => {
    const segments = path.split('/').slice(0, -1);
    const toExpand: Record<string, boolean> = {};
    let prefix = '';
    for (const seg of segments) {
      prefix = prefix ? `${prefix}/${seg}` : seg;
      toExpand[prefix] = true;
    }
    setExpanded(prev => ({ ...prev, ...toExpand }));
    selectAndFocusNode(path, false);
  };

  const renderTree = (children: Record<string, FileNode>, prefix = '', depth = 0): React.ReactNode => {
    const entries = Object.entries(children);
    if (!entries.length) return <></>;
    const indent = depth * 14;
    return (
      <ul className="list-none p-0 m-0">
        {entries.map(([name, node]) => {
          const fullPath = prefix ? `${prefix}/${name}` : name;
          if (node.type === 'directory') {
            const isOpen = expanded[fullPath];
            return (
              <li key={fullPath}>
                <div
                  className="flex items-center gap-2 px-2 py-1.5 cursor-pointer text-xs rounded hover:bg-accent/50 transition-colors duration-100"
                  style={{ paddingLeft: `${indent + 8}px` }}
                  onClick={() => toggleExpand(fullPath)}
                >
                  <span className={`text-[0.5rem] transition-transform shrink-0 ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                  <div className="flex items-center justify-center w-5 h-5 rounded-md bg-secondary/50 shrink-0">
                    <FolderClosed className="h-3 w-3 text-muted-foreground" />
                  </div>
                  <span className="truncate flex-1">{name}</span>
                  <span className="text-muted-foreground text-[10px]">{countFiles(node.children || {})}</span>
                </div>
                {isOpen && node.children && renderTree(node.children, fullPath, depth + 1)}
              </li>
            );
          }
          const wikiPath = `wiki/${fullPath}`;
          const isActive = selectedNodeId === fullPath; // selectedNodeId has no wiki/ prefix, fullPath neither
          return (
            <li key={fullPath}>
              <div
                className={`flex items-center gap-2 px-2 py-1.5 cursor-pointer text-xs rounded transition-colors duration-100 ${
                  isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
                }`}
                style={{ paddingLeft: `${indent + 32}px` }}
                onClick={() => handleTreeSelect(wikiPath)}
              >
                <div className="flex items-center justify-center w-5 h-5 rounded-md bg-muted/50 shrink-0">
                  <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                </div>
                <span className="truncate">{name}</span>
              </div>
            </li>
          );
        })}
      </ul>
    );
  };

  /* ─── View controls ─── */
  const resetView = () => {
    networkRef.current?.fit({ animation: { duration: 300, easingFunction: 'easeOutQuad' } as any });
    networkRef.current?.setSelection({ nodes: [] });
    setFilterText('');
    setSelectedNodeId(null);
    nodesRef.current?.update(nodesRef.current.get().map((n: any) => ({
      id: n.id,
      font: {
        size: labelFontSize,
        color: LABEL_COLOR,
        face: 'Inter, system-ui, -apple-system, sans-serif',
        strokeWidth: 0,
        align: 'right',
        vadjust: 0,
      } as any,
    })));
  };
  const zoomIn = () => {
    if (!networkRef.current) return;
    networkRef.current.moveTo({
      scale: networkRef.current.getScale() * 1.3,
      animation: { duration: 200, easingFunction: 'easeOutQuad' } as any,
    });
  };
  const zoomOut = () => {
    if (!networkRef.current) return;
    networkRef.current.moveTo({
      scale: networkRef.current.getScale() * 0.7,
      animation: { duration: 200, easingFunction: 'easeOutQuad' } as any,
    });
  };

  const resetFilters = () => {
    setHiddenTypes(new Set());
    setHiddenCommunities(new Set());
    setHideOrphans(false);
    setMinDegree(0);
    setMaxDegree(maxNodeDegree);
    setNodeScalePct(100);
  };

  const hiddenCount = useMemo(() => {
    if (!graphData) return 0;
    return graphData.nodes.filter(n => {
      const pt = n.page_type || 'entity';
      const cid = nodeCommunityMap[n.id];
      const deg = n.degree || 0;
      if (viewMode === 'type' && hiddenTypes.has(pt)) return true;
      if (viewMode === 'community' && (cid === undefined || hiddenCommunities.has(cid))) return true;
      if (hideOrphans && deg === 0) return true;
      if (deg < minDegree || deg > maxDegree) return true;
      return false;
    }).length;
  }, [graphData, viewMode, hiddenTypes, hiddenCommunities, hideOrphans, minDegree, maxDegree, nodeCommunityMap]);

  const visibleCount = nodeCount - hiddenCount;

  /* ─── Render ─── */
  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* ── Middle: File tree ── */}
      <div className="w-72 flex-shrink-0 border-r border-border bg-card flex flex-col min-h-0 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
          <BookOpen className="h-4 w-4" />
          <span className="text-xs font-medium">知识库</span>
        </div>
        <div className="flex-1 overflow-y-scroll py-1">
          {treeLoading ? (
            <div className="space-y-1 p-3">
              {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-5 w-full" />)}
            </div>
          ) : Object.keys(wikiTree).length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-8">
              <BookOpen className="h-6 w-6 mx-auto mb-1 opacity-30" />
              知识库还没有内容
            </div>
          ) : renderTree(wikiTree, '')}
        </div>
      </div>

      {/* ── Right: Graph canvas ── */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0 relative overflow-hidden" style={{ background: CANVAS_BG }}>
        {/* Top floating toolbar */}
        {!loading && !error && graphData && (
          <div className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-4 py-2.5 pointer-events-none">
            <div className="flex items-center gap-2 pointer-events-auto">
              <div className="flex items-center gap-1.5">
                <GitBranch className="h-4 w-4" style={{ color: LABEL_COLOR }} />
                <span className="text-sm font-semibold" style={{ color: LABEL_COLOR }}>知识关系图</span>
              </div>
              <div className="flex items-center gap-1.5 ml-2">
                <Badge variant="outline" className={`text-[10px] h-5 ${isDark ? 'border-white/15 text-gray-300 bg-white/5' : 'border-black/10 text-gray-700 bg-black/5'}`}>
                  {visibleCount}/{nodeCount} 页面
                </Badge>
                <Badge variant="outline" className={`text-[10px] h-5 ${isDark ? 'border-white/15 text-gray-300 bg-white/5' : 'border-black/10 text-gray-700 bg-black/5'}`}>
                  {edgeCount} 链接
                </Badge>
                {hiddenCount > 0 && (
                  <Badge className="text-[10px] h-5 bg-amber-500/20 text-amber-400 border-amber-500/30 hover:bg-amber-500/20">
                    {hiddenCount} 已隐藏
                  </Badge>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2 pointer-events-auto">
              {/* Search */}
              <div className="relative flex items-center">
                <Search className="h-3 w-3 absolute left-2 pointer-events-none" style={{ color: isDark ? '#9ca3af' : '#6b7280' }} />
                <Input
                  className={`h-7 w-40 pl-7 pr-6 text-xs ${isDark ? 'bg-white/5 border-white/10 text-gray-200 placeholder:text-gray-500' : 'bg-black/5 border-black/10 text-gray-800 placeholder:text-gray-500'}`}
                  placeholder="搜索节点..."
                  value={filterText}
                  onChange={e => setFilterText(e.target.value)}
                />
                {filterText && (
                  <X className="h-3 w-3 absolute right-2 cursor-pointer" style={{ color: isDark ? '#9ca3af' : '#6b7280' }} onClick={() => setFilterText('')} />
                )}
              </div>

              {/* Filter toggle */}
              <Button
                variant={showFilter ? 'secondary' : 'ghost'}
                size="sm"
                className={`h-7 px-2 text-xs gap-1 ${isDark ? 'text-gray-300' : 'text-gray-700'}`}
                onClick={() => setShowFilter(v => !v)}
              >
                <Filter className="h-3 w-3" /> 过滤器
              </Button>

              <div className={`flex items-center gap-0.5 rounded-md p-0.5 ${isDark ? 'bg-white/5' : 'bg-black/5'}`}>
                {([
                  { key: 'type', label: '类型', icon: Palette },
                  { key: 'community', label: '社区', icon: Layers },
                  { key: 'insights', label: '洞察', icon: Lightbulb },
                ] as { key: ViewMode; label: string; icon: any }[]).map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    onClick={() => setViewMode(key)}
                    className={`flex items-center gap-1 px-2 h-6 rounded text-[11px] font-medium transition-colors ${
                      viewMode === key
                        ? (isDark ? 'bg-white/10 text-white shadow-sm' : 'bg-white text-gray-900 shadow-sm')
                        : (isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-600 hover:text-gray-900')
                    }`}
                  >
                    <Icon className="h-3 w-3" />
                    {label}
                    {key === 'insights' && insights && (
                      <span className="ml-0.5 text-[9px] bg-amber-500/30 text-amber-300 rounded-full px-1">
                        {insights.surprising_connections.length}
                      </span>
                    )}
                  </button>
                ))}
              </div>

              <Button
                variant="ghost"
                size="icon"
                className={`h-7 w-7 ${isDark ? 'text-gray-300 hover:bg-white/10' : 'text-gray-700 hover:bg-black/5'}`}
                onClick={resetView}
                title="重置视图"
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}

        {/* Canvas content */}
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <Skeleton className="h-32 w-32 rounded-full mx-auto mb-4" />
              <p className="text-sm" style={{ color: isDark ? '#9ca3af' : '#6b7280' }}>加载图谱...</p>
            </div>
          </div>
        ) : error ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <NetworkIcon className="h-10 w-10 mx-auto mb-2 text-destructive opacity-50" />
              <p className="text-sm text-destructive">{error}</p>
              <Button variant="outline" size="sm" className="mt-2" onClick={() => window.location.reload()}>重试</Button>
            </div>
          </div>
        ) : !graphData || nodeCount === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <EmptyState icon={NetworkIcon} title="知识图谱为空" desc="导入文档后图谱将自动生成" />
          </div>
        ) : (
          <>
            {/* Network container */}
            <div ref={containerRef} className="w-full h-full" />

            {/* ── Filter panel (top-left floating) ── */}
            {showFilter && (
              <div className={`absolute top-12 left-4 z-20 w-60 rounded-xl backdrop-blur-md shadow-lg border ${FLOATING_BG} ${FLOATING_BORDER} p-3 text-xs`}>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold flex items-center gap-1" style={{ color: LABEL_COLOR }}>
                    <Filter className="h-3 w-3" /> 关系图过滤器
                  </span>
                  <button
                    className={`${isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-800'}`}
                    onClick={resetFilters}
                    title="重置"
                  >
                    <RotateCcw className="h-3 w-3" />
                  </button>
                </div>

                {/* Quick toggles */}
                <div className="space-y-1.5 mb-3 pb-2 border-b" style={{ borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)' }}>
                  <label className="flex items-center gap-2 cursor-pointer" style={{ color: LABEL_COLOR }}>
                    <input
                      type="checkbox"
                      checked={!hideOrphans}
                      onChange={e => setHideOrphans(!e.target.checked)}
                      className="accent-blue-500"
                    />
                    隐藏孤点
                  </label>
                </div>

                {/* Degree filters */}
                <div className="space-y-2 mb-3 pb-2 border-b" style={{ borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)' }}>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span style={{ color: isDark ? '#9ca3af' : '#6b7280' }}>最小链接数</span>
                      <span className="text-[10px]" style={{ color: LABEL_COLOR }}>{minDegree}</span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={maxNodeDegree}
                      value={minDegree}
                      onChange={e => setMinDegree(parseInt(e.target.value))}
                      className="w-full h-1 accent-blue-500"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span style={{ color: isDark ? '#9ca3af' : '#6b7280' }}>最大链接数</span>
                      <span className="text-[10px]" style={{ color: LABEL_COLOR }}>{maxDegree}</span>
                    </div>
                    <input
                      type="range"
                      min={0}
                      max={maxNodeDegree}
                      value={maxDegree}
                      onChange={e => setMaxDegree(parseInt(e.target.value))}
                      className="w-full h-1 accent-blue-500"
                    />
                  </div>
                </div>

                {/* Display */}
                <div className="space-y-2 mb-3 pb-2 border-b" style={{ borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)' }}>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span style={{ color: isDark ? '#9ca3af' : '#6b7280' }}>节点大小</span>
                      <span className="text-[10px]" style={{ color: LABEL_COLOR }}>{nodeScalePct}%</span>
                    </div>
                    <input
                      type="range"
                      min={30}
                      max={200}
                      value={nodeScalePct}
                      onChange={e => setNodeScalePct(parseInt(e.target.value))}
                      className="w-full h-1 accent-blue-500"
                    />
                  </div>
                </div>

                {/* Type/Community checklist (depends on viewMode) */}
                <div>
                  <div className="mb-1.5" style={{ color: isDark ? '#9ca3af' : '#6b7280' }}>
                    {viewMode === 'community' ? '社区' : '节点类型'}
                  </div>
                  <div className="space-y-1 max-h-40 overflow-y-auto">
                    {viewMode === 'type' && Object.entries(TYPE_LABELS).map(([key, label]) => {
                      const count = graphData.nodes.filter(n => (n.page_type || 'entity') === key).length;
                      if (count === 0) return null;
                      const checked = !hiddenTypes.has(key);
                      return (
                        <label key={key} className="flex items-center gap-2 cursor-pointer rounded px-1 py-0.5" style={{ color: LABEL_COLOR }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              setHiddenTypes(prev => {
                                const next = new Set(prev);
                                if (checked) next.add(key); else next.delete(key);
                                return next;
                              });
                            }}
                            className="accent-blue-500"
                          />
                          <span className="w-2.5 h-2.5 rounded-full inline-block shrink-0" style={{ backgroundColor: TYPE_COLORS[key] }} />
                          <span className="flex-1 text-[11px]">{label}</span>
                          <span className="text-[10px] opacity-50">{count}</span>
                        </label>
                      );
                    })}
                    {viewMode === 'community' && communities && Object.entries(communities).map(([cid, c]) => {
                      const checked = !hiddenCommunities.has(cid);
                      return (
                        <label key={cid} className="flex items-center gap-2 cursor-pointer rounded px-1 py-0.5" style={{ color: LABEL_COLOR }}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => {
                              setHiddenCommunities(prev => {
                                const next = new Set(prev);
                                if (checked) next.add(cid); else next.delete(cid);
                                return next;
                              });
                            }}
                            className="accent-blue-500"
                          />
                          <span className="w-2.5 h-2.5 rounded-full inline-block shrink-0" style={{ backgroundColor: communityColor(cid) }} />
                          <span className="flex-1 text-[11px] truncate" title={`${c.size} 成员 · 内聚度 ${c.cohesion.toFixed(2)}`}>
                            {communityLabel(cid, c)}
                          </span>
                          <span className="text-[10px] opacity-50">{c.size}</span>
                        </label>
                      );
                    })}
                    {viewMode === 'insights' && (
                      <div className="text-[10px] opacity-60 py-2 text-center" style={{ color: LABEL_COLOR }}>
                        洞察模式下，惊奇连接以
                        <span className="inline-block w-2 h-2 rounded-full mx-1" style={{ backgroundColor: EDGE_HIGHLIGHT }} />
                        高亮显示
                      </div>
                    )}
                  </div>
                </div>

                <div className="mt-3 pt-2 text-[10px] opacity-60 text-center border-t" style={{ color: LABEL_COLOR, borderColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)' }}>
                  显示 {visibleCount} 个页面和 {edgeCount} 条链接。
                </div>
              </div>
            )}

            {/* ── Vertical zoom controls (right side) ── */}
            <div className={`absolute right-3 top-12 flex flex-col gap-1 z-10 p-1 rounded-xl backdrop-blur-md shadow-lg ${FLOATING_BG} border ${FLOATING_BORDER}`}>
              <Button variant="ghost" size="icon" className={`h-8 w-8 rounded-lg ${isDark ? 'text-gray-300 hover:bg-white/10' : 'text-gray-700 hover:bg-black/5'}`} onClick={zoomIn} title="放大">
                <ZoomIn className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className={`h-8 w-8 rounded-lg ${isDark ? 'text-gray-300 hover:bg-white/10' : 'text-gray-700 hover:bg-black/5'}`} onClick={zoomOut} title="缩小">
                <ZoomOut className="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" className={`h-8 w-8 rounded-lg ${isDark ? 'text-gray-300 hover:bg-white/10' : 'text-gray-700 hover:bg-black/5'}`} onClick={resetView} title="适应视图">
                <Maximize className="h-4 w-4" />
              </Button>
            </div>

            {/* ── Bottom-left legend / info card ── */}
            {!showFilter && showLegend && (
              <div className={`absolute bottom-4 left-4 z-10 rounded-xl backdrop-blur-md shadow-lg border ${FLOATING_BG} ${FLOATING_BORDER} px-3 py-2.5 min-w-[160px] max-w-[260px]`}>
                {/* Clickable header — collapses legend */}
                <div
                  className="flex items-center justify-between mb-1.5 cursor-pointer"
                  onClick={() => setShowLegend(false)}
                >
                  <span className="text-[11px] font-semibold flex items-center gap-1" style={{ color: LABEL_COLOR }}>
                    {viewMode === 'type' && <><Palette className="h-3 w-3" /> 节点类型</>}
                    {viewMode === 'community' && <><Layers className="h-3 w-3" /> 社区</>}
                    {viewMode === 'insights' && <><Lightbulb className="h-3 w-3" /> 洞察</>}
                  </span>
                  <ChevronDown className="h-3 w-3 opacity-50 cursor-pointer hover:opacity-100 transition-opacity" style={{ color: LABEL_COLOR }} />
                </div>
                <div className="space-y-1 max-h-[40vh] overflow-y-auto">
                  {viewMode === 'type' && Object.entries(TYPE_LABELS).map(([key, label]) => {
                    const count = graphData.nodes.filter(n => (n.page_type || 'entity') === key).length;
                    if (count === 0) return null;
                    const hidden = hiddenTypes.has(key);
                    return (
                      <div
                        key={key}
                        className={`flex items-center gap-2 cursor-pointer rounded px-1.5 py-0.5 transition-colors ${hidden ? 'opacity-40' : ''} ${isDark ? 'hover:bg-white/5' : 'hover:bg-black/5'}`}
                        onClick={() => setHiddenTypes(prev => {
                          const next = new Set(prev);
                          if (next.has(key)) next.delete(key); else next.add(key);
                          return next;
                        })}
                      >
                        <span className="w-2.5 h-2.5 rounded-full inline-block shrink-0" style={{ backgroundColor: TYPE_COLORS[key] }} />
                        <span className="text-[11px] flex-1" style={{ color: LABEL_COLOR }}>{label}</span>
                        <span className="text-[10px] opacity-50" style={{ color: LABEL_COLOR }}>{count}</span>
                        {hidden ? <EyeOff className="h-3 w-3 opacity-50" style={{ color: LABEL_COLOR }} /> : null}
                      </div>
                    );
                  })}
                  {viewMode === 'community' && communities && Object.entries(communities).map(([cid, c]) => {
                    const hidden = hiddenCommunities.has(cid);
                    return (
                      <div
                        key={cid}
                        className={`flex items-center gap-2 cursor-pointer rounded px-1.5 py-0.5 transition-colors ${hidden ? 'opacity-40' : ''} ${isDark ? 'hover:bg-white/5' : 'hover:bg-black/5'}`}
                        onClick={() => setHiddenCommunities(prev => {
                          const next = new Set(prev);
                          if (next.has(cid)) next.delete(cid); else next.add(cid);
                          return next;
                        })}
                        title={`${c.size} 成员 · 内聚度 ${c.cohesion.toFixed(2)}`}
                      >
                        <span className="w-2.5 h-2.5 rounded-full inline-block shrink-0" style={{ backgroundColor: communityColor(cid) }} />
                        <span className="text-[11px] flex-1 truncate" style={{ color: LABEL_COLOR }}>{communityLabel(cid, c)}</span>
                        <span className="text-[10px] opacity-50" style={{ color: LABEL_COLOR }}>{c.size}</span>
                        {hidden ? <EyeOff className="h-3 w-3 opacity-50" style={{ color: LABEL_COLOR }} /> : null}
                      </div>
                    );
                  })}
                  {viewMode === 'insights' && insights && (
                    <>
                      <div className="text-[10px] mb-1 flex items-center gap-1.5" style={{ color: isDark ? '#9ca3af' : '#6b7280' }}>
                        <span className="inline-block w-3 h-0.5" style={{ backgroundColor: EDGE_HIGHLIGHT }} />
                        惊奇连接 ({insights.surprising_connections.length})
                      </div>
                      <div className="text-[10px] mb-1 flex items-center gap-1.5" style={{ color: isDark ? '#9ca3af' : '#6b7280' }}>
                        <span className="inline-block w-3 h-3 rounded-full opacity-40" style={{ backgroundColor: LABEL_COLOR }} />
                        知识孤岛 ({insights.summary.total_gaps})
                      </div>
                      {insights.surprising_connections.slice(0, 5).map((s, i) => (
                        <div key={i} className="text-[10px] px-1 py-0.5 rounded flex items-center gap-1" style={{ color: LABEL_COLOR }}>
                          <span className="truncate opacity-80">{shortName(s.source)}</span>
                          <span className="opacity-40">↔</span>
                          <span className="truncate opacity-80">{shortName(s.target)}</span>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
            )}

            {/* ── Collapsed legend stub — click to re-open ── */}
            {!showFilter && !showLegend && (
              <div
                className={`absolute bottom-4 left-4 z-10 rounded-xl backdrop-blur-md shadow-lg border ${FLOATING_BG} ${FLOATING_BORDER} px-2.5 py-2 cursor-pointer hover:brightness-110 transition-all`}
                onClick={() => setShowLegend(true)}
                title="展开图例"
              >
                <ChevronRight className="h-3 w-3" style={{ color: LABEL_COLOR }} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
