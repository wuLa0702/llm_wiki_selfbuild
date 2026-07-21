import { useEffect, useState } from 'react';
import {
  AlertTriangle, CheckCircle, FileWarning, RefreshCw,
  BookOpen, GitBranch, HelpCircle, FileEdit, BrainCircuit,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { showToast } from '@/components/shared/Toast';

interface BrokenLink { source: string; target: string; }
interface Contradiction {
  page_a: string; page_b: string; description: string;
  confidence?: string;
}
interface KnowledgeGap {
  topic: string; description: string; mentioned_in?: string[];
}
interface ShallowPage {
  page: string; reason: string; suggestion?: string;
}
interface LintResult {
  broken_links?: BrokenLink[];
  orphan_pages?: string[];
  index_gaps?: string[];
  contradictions?: Contradiction[];
  knowledge_gaps?: KnowledgeGap[];
  shallow_pages?: ShallowPage[];
  health_score?: number;
  summary?: string;
  cached?: boolean;
}

/** 根据分数返回颜色类 */
function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-600 dark:text-green-400';
  if (score >= 50) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-600 dark:text-red-400';
}
function scoreBorder(score: number): string {
  if (score >= 80) return 'border-l-green-500';
  if (score >= 50) return 'border-l-amber-500';
  return 'border-l-red-500';
}

export default function LintPage() {
  const [result, setResult] = useState<LintResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSemantic, setIsSemantic] = useState(false);

  const runLint = async (semantic = false) => {
    setLoading(true);
    setIsSemantic(semantic);
    try {
      const r = await fetch(`/v1/lint?semantic=${semantic}`);
      const d = await r.json();
      setResult(d);
      showToast('检查完成', 'success');
    } catch { showToast('检查失败', 'error'); }
    setLoading(false);
  };

  useEffect(() => { runLint(false); }, []);

  const score = result?.health_score ?? -1;
  const links = result?.broken_links || [];
  const orphans = result?.orphan_pages || [];
  const gaps = result?.index_gaps || [];
  const contradictions = result?.contradictions || [];
  const knowledgeGaps = result?.knowledge_gaps || [];
  const shallowPages = result?.shallow_pages || [];
  const hasIssues = links.length > 0 || orphans.length > 0 || gaps.length > 0
    || contradictions.length > 0 || knowledgeGaps.length > 0 || shallowPages.length > 0;

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold">Wiki 健康检查</h1>
            <p className="text-sm text-muted-foreground">检测断链、孤立页面等质量问题</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => runLint(false)} disabled={loading}>
              <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
              {loading ? '检查中...' : '静态检查'}
            </Button>
            <Button size="sm" onClick={() => runLint(true)} disabled={loading}>
              <BrainCircuit className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
              {loading ? '检查中...' : '语义检查'}
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Health Score */}
            {score >= 0 && (
              <Card className={`border-l-3 ${scoreBorder(score)}`}>
                <CardContent className="p-4 flex items-center justify-between">
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">健康评分</p>
                    <p className={`text-3xl font-bold ${scoreColor(score)}`}>{score}</p>
                  </div>
                  <div className="text-right text-xs text-muted-foreground">
                    {result?.summary ? (
                      <p className="max-w-xs text-right">{result.summary}</p>
                    ) : null}
                    {result?.cached && (
                      <Badge variant="outline" className="mt-1 text-[10px]">缓存</Badge>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Summary fallback if no score */}
            {score < 0 && result?.summary && (
              <Card>
                <CardContent className="p-4 text-sm">{result.summary}</CardContent>
              </Card>
            )}

            {/* Broken links */}
            {links.length > 0 && (
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="h-4 w-4 text-destructive" />
                    <h2 className="text-sm font-semibold">断链 ({links.length})</h2>
                  </div>
                  <div className="space-y-2">
                    {links.map((link, i) => (
                      <div key={i} className="flex items-start gap-2 p-2 rounded bg-muted/50 text-xs">
                        <span className="text-destructive font-medium max-w-[40%] truncate" title={link.source}>{link.source}</span>
                        <span className="text-muted-foreground shrink-0">→</span>
                        <span className="text-muted-foreground max-w-[40%] truncate" title={link.target}>{link.target}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Orphan pages */}
            {orphans.length > 0 && (
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <FileWarning className="h-4 w-4 text-amber-500" />
                    <h2 className="text-sm font-semibold">孤立页面 ({orphans.length})</h2>
                    <p className="text-xs text-muted-foreground">无入链，未被任何页面引用</p>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {orphans.map(p => (
                      <Badge key={p} variant="outline" className="text-[10px]">{p}</Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Index gaps */}
            {gaps.length > 0 && (
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <BookOpen className="h-4 w-4 text-blue-500" />
                    <h2 className="text-sm font-semibold">Index 缺口 ({gaps.length})</h2>
                    <p className="text-xs text-muted-foreground">存在于 wiki/ 但未在 index.md 列出</p>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {gaps.map(p => (
                      <Badge key={p} variant="outline" className="text-[10px]">{p}</Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Contradictions (semantic) */}
            {contradictions.length > 0 && (
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <GitBranch className="h-4 w-4 text-purple-500" />
                    <h2 className="text-sm font-semibold">内容矛盾 ({contradictions.length})</h2>
                    {isSemantic && <Badge variant="outline" className="text-[10px]">语义</Badge>}
                  </div>
                  <div className="space-y-2">
                    {contradictions.map((c, i) => (
                      <div key={i} className="p-2.5 rounded bg-muted/50 text-xs space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-purple-600 dark:text-purple-400 font-medium">{c.page_a}</span>
                          <span className="text-muted-foreground">↔</span>
                          <span className="text-purple-600 dark:text-purple-400 font-medium">{c.page_b}</span>
                          {c.confidence && (
                            <Badge variant="outline" className={`text-[9px] ${c.confidence === 'high' ? 'border-red-300 text-red-500' : ''}`}>
                              {c.confidence === 'high' ? '高置信' : '低置信'}
                            </Badge>
                          )}
                        </div>
                        <p className="text-muted-foreground">{c.description}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Knowledge gaps (semantic) */}
            {knowledgeGaps.length > 0 && (
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <HelpCircle className="h-4 w-4 text-cyan-500" />
                    <h2 className="text-sm font-semibold">知识缺口 ({knowledgeGaps.length})</h2>
                    {isSemantic && <Badge variant="outline" className="text-[10px]">语义</Badge>}
                  </div>
                  <div className="space-y-2">
                    {knowledgeGaps.map((g, i) => (
                      <div key={i} className="p-2.5 rounded bg-muted/50 text-xs space-y-1">
                        <p className="font-medium text-cyan-700 dark:text-cyan-300">{g.topic}</p>
                        <p className="text-muted-foreground">{g.description}</p>
                        {g.mentioned_in && g.mentioned_in.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className="text-muted-foreground">提及于：</span>
                            {g.mentioned_in.map(m => (
                              <Badge key={m} variant="outline" className="text-[9px]">{m}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Shallow pages (semantic) */}
            {shallowPages.length > 0 && (
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <FileEdit className="h-4 w-4 text-orange-500" />
                    <h2 className="text-sm font-semibold">浅页面 ({shallowPages.length})</h2>
                    {isSemantic && <Badge variant="outline" className="text-[10px]">语义</Badge>}
                  </div>
                  <div className="space-y-2">
                    {shallowPages.map((s, i) => (
                      <div key={i} className="p-2.5 rounded bg-muted/50 text-xs space-y-1">
                        <p className="font-medium text-orange-700 dark:text-orange-300">{s.page}</p>
                        <p className="text-muted-foreground">{s.reason}</p>
                        {s.suggestion && (
                          <p className="text-blue-600 dark:text-blue-400">建议：{s.suggestion}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* All clear */}
            {!hasIssues && (
              <div className="text-center py-12 text-muted-foreground">
                <CheckCircle className="h-10 w-10 mx-auto mb-2 text-green-500" />
                <p className="text-sm">未发现问题</p>
                <p className="text-xs mt-1">知识库状态健康</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
