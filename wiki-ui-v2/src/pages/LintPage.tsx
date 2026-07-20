import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle, FileWarning, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { showToast } from '@/components/shared/Toast';

interface BrokenLink { source: string; target: string; }
interface LintResult {
  broken_links?: BrokenLink[];
  orphan_pages?: string[];
  summary?: string;
}

export default function LintPage() {
  const [result, setResult] = useState<LintResult | null>(null);
  const [loading, setLoading] = useState(true);

  const runLint = async (semantic = false) => {
    setLoading(true);
    try {
      const r = await fetch(`/v1/lint?semantic=${semantic}`);
      const d = await r.json();
      setResult(d);
      showToast('检查完成', 'success');
    } catch { showToast('检查失败', 'error'); }
    setLoading(false);
  };

  useEffect(() => { runLint(false); }, []);

  const links = result?.broken_links || [];
  const orphans = result?.orphan_pages || [];

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
              {loading ? '检查中...' : '检查'}
            </Button>
            <Button size="sm" onClick={() => runLint(true)} disabled={loading}>
              🧠 语义检查
            </Button>
          </div>
        </div>

        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <div className="space-y-4">
            {/* Summary */}
            {result?.summary && (
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
                        <span className="text-destructive font-medium">{link.source}</span>
                        <span className="text-muted-foreground">→</span>
                        <span className="text-muted-foreground">{link.target}</span>
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
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {orphans.map(p => (
                      <Badge key={p} variant="outline" className="text-[10px]">{p}</Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* All clear */}
            {links.length === 0 && orphans.length === 0 && (
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
